"""CCON BA Desk — Python standard library only. Local, single-user prototype."""
import argparse
import hashlib
import json
import math
import re
import sqlite3
import socket
import threading
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent
STATUSES = ['AUTO', 'IN PROGRESS', 'WAITING INPUT', 'WAITING DEPENDENCY', 'NEEDS DECISION', 'DONE']
LIMIT = 5 * 1024 * 1024
CONTEXT_LIMIT = 50 * 1024 * 1024
VERSION = '2.0.0'
SIGNALS = ('READY', 'WRITE', 'WAIT', 'DECIDE', 'REVIEW', 'DONE')

class LocalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can otherwise allow two different app versions on one port.
    allow_reuse_address = False
    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def text_field(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{label} must be text (maximum {maximum:,} characters).')

def validate_draft(draft, label='emailDraft'):
    if not isinstance(draft, dict):
        raise ValueError(label + ' must be an object.')
    for field, maximum in (('to', 2000), ('subject', 2000), ('body', 50000)):
        if field not in draft:
            raise ValueError(label + '.' + field + ' is required.')
        text_field(draft[field], label + '.' + field, maximum)
    if any(char in draft[field] for field in ('to', 'subject') for char in ('\r', '\n')):
        raise ValueError(label + ' recipient and subject must be single-line text.')

def validate_analysis(analysis):
    if not isinstance(analysis, dict):
        raise ValueError('analysis must be an object.')
    if 'signal' in analysis and analysis['signal'] not in SIGNALS:
        raise ValueError('analysis.signal must be READY, WRITE, WAIT, DECIDE, REVIEW or DONE.')
    for field, maximum in (('reasonUk', 20000), ('nextActionUk', 10000),
                           ('waitingOnUk', 2000), ('standardDescription', 30000)):
        if field in analysis:
            text_field(analysis[field], 'analysis.' + field, maximum)
    for field in ('waitingRequired', 'needsEmail'):
        if field in analysis and analysis[field] is not None and not isinstance(analysis[field], bool):
            raise ValueError('analysis.' + field + ' must be true, false or null.')
    if 'stale' in analysis and not isinstance(analysis['stale'], bool):
        raise ValueError('analysis.stale must be true or false.')
    if 'queueScore' in analysis:
        score = analysis['queueScore']
        if isinstance(score, bool) or not isinstance(score, (int, float)) or abs(score) > 1000000 or not math.isfinite(score):
            raise ValueError('analysis.queueScore must be a finite number between -1000000 and 1000000.')
    if 'missingInfo' in analysis:
        missing = analysis['missingInfo']
        if not isinstance(missing, list) or len(missing) > 100:
            raise ValueError('analysis.missingInfo must be an array of at most 100 items.')
        for item in missing:
            text_field(item, 'analysis.missingInfo item', 3000)
    if 'evidence' in analysis:
        evidence = analysis['evidence']
        if not isinstance(evidence, list) or len(evidence) > 100:
            raise ValueError('analysis.evidence must be an array of at most 100 objects.')
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError('analysis.evidence items must be objects.')
            text_field(item.get('text'), 'analysis.evidence.text', 4000)
            text_field(item.get('url'), 'analysis.evidence.url', 2000)
            if item['url'] and urlparse(item['url']).scheme not in ('http', 'https'):
                raise ValueError('analysis.evidence.url must be an HTTP or HTTPS URL.')
    if 'emailDraft' in analysis and analysis['emailDraft'] is not None:
        validate_draft(analysis['emailDraft'], 'analysis.emailDraft')

def now():
    return datetime.now(timezone.utc).isoformat()

class Desk:
    validate_analysis = staticmethod(validate_analysis)

    def __init__(self, root):
        self.root = Path(root)
        self.inbox = self.root / 'inbox'
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'ba_state.db'
        self.lock = threading.RLock()
        self.error = ''
        with self.connect() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS tasks (
                key TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                manual_status TEXT NOT NULL DEFAULT 'AUTO', note TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL,
                modified_at TEXT);
              CREATE TABLE IF NOT EXISTS imports (
                hash TEXT PRIMARY KEY, imported_at TEXT NOT NULL, generated_at TEXT NOT NULL,
                count INTEGER NOT NULL);
            ''')
            if 'position' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
            if 'email_draft' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN email_draft TEXT DEFAULT NULL')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def import_snapshot(self):
        path = self.inbox / 'CCON_BA_Snapshot.json'
        if not path.exists():
            return {'message': 'No snapshot yet. Save CCON_BA_Snapshot.json in inbox.'}
        try:
            if path.stat().st_size > LIMIT:
                raise ValueError('Snapshot must be smaller than 5 MB.')
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            doc = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(doc, dict) or not isinstance(doc.get('tasks'), list):
                raise ValueError('Expected an object with a tasks array. See examples/snapshot.json.')
            generated = doc.get('generatedAt')
            if not isinstance(generated, str):
                raise ValueError('generatedAt must be an ISO timestamp with timezone.')
            try:
                date = datetime.fromisoformat(generated.replace('Z', '+00:00'))
                if date.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise ValueError('generatedAt must be an ISO timestamp with timezone.')
            keys = set()
            for task in doc['tasks']:
                if not isinstance(task, dict) or not re.fullmatch(r'CCON-\d+', str(task.get('key', ''))):
                    raise ValueError('Every task needs a CCON-number key.')
                if task['key'] in keys:
                    raise ValueError('Duplicate task key: ' + task['key'])
                keys.add(task['key'])
                for field in ('summary', 'aiStatus', 'waitingOn', 'statusReason', 'nextAction', 'readyOutput', 'jiraStatus', 'priority', 'url'):
                    if field in task:
                        text_field(task[field], field, 100000)
                if not task.get('summary', '').strip():
                    raise ValueError('Every task needs a summary.')
                if 'blocking' in task and not isinstance(task['blocking'], bool):
                    raise ValueError('blocking must be true or false.')
                if 'analysis' in task:
                    validate_analysis(task['analysis'])
            with self.lock, self.connect() as c:
                if c.execute('SELECT 1 FROM imports WHERE hash=?', (digest,)).fetchone():
                    self.error = ''
                    return {'message': 'Snapshot already imported; manual changes preserved.'}
                latest = c.execute('SELECT generated_at FROM imports ORDER BY imported_at DESC LIMIT 1').fetchone()
                if latest and date < datetime.fromisoformat(latest[0].replace('Z', '+00:00')):
                    raise ValueError('Older snapshot rejected. Use the latest generatedAt timestamp.')
                stamp = now()
                c.execute('UPDATE tasks SET active=0')
                for position, task in enumerate(doc['tasks']):
                    c.execute('''INSERT INTO tasks(key,snapshot,imported_at,position) VALUES(?,?,?,?)
                      ON CONFLICT(key) DO UPDATE SET snapshot=excluded.snapshot,
                      imported_at=excluded.imported_at, position=excluded.position, active=1''',
                      (task['key'], json.dumps(task, ensure_ascii=False), stamp, position))
                c.execute('INSERT INTO imports VALUES(?,?,?,?)', (digest, stamp, generated, len(keys)))
            self.error = ''
            return {'message': f'Imported {len(keys)} tasks. Manual status and notes preserved.'}
        except (ValueError, OSError) as e:
            self.error = 'Import failed: ' + str(e)
            raise ValueError(self.error)

    def view(self):
        with self.lock, self.connect() as c:
            rows = c.execute('SELECT * FROM tasks ORDER BY active DESC, position, key').fetchall()
            latest = c.execute('SELECT * FROM imports ORDER BY imported_at DESC LIMIT 1').fetchone()
            tasks = []
            for row in rows:
                task = json.loads(row['snapshot'])
                task.update(manualStatus=row['manual_status'], note=row['note'], active=bool(row['active']),
                            importedAt=row['imported_at'], modifiedAt=row['modified_at'],
                            savedEmailDraft=json.loads(row['email_draft']) if row['email_draft'] else None)
                tasks.append(task)
            return {'tasks': tasks, 'latest': dict(latest) if latest else None, 'error': self.error}

    def save(self, key, data):
        status, note = data.get('manualStatus'), data.get('note')
        if status not in STATUSES or not isinstance(note, str) or len(note) > 20000:
            raise ValueError('Invalid manual status or note (maximum 20,000 characters).')
        if 'emailDraft' in data and data['emailDraft'] is not None:
            validate_draft(data['emailDraft'])
        with self.lock, self.connect() as c:
            values = [status, note, now()]
            query = 'UPDATE tasks SET manual_status=?, note=?, modified_at=?'
            if 'emailDraft' in data:
                query += ', email_draft=?'
                draft = data['emailDraft']
                values.append(json.dumps({field: draft[field] for field in ('to', 'subject', 'body')}, ensure_ascii=False) if draft is not None else None)
            query += ' WHERE key=?'
            values.append(key)
            if not c.execute(query, values).rowcount:
                raise ValueError('Unknown task.')

    def context(self, key):
        if not re.fullmatch(r'CCON-\d+', key):
            raise ValueError('Invalid task key.')
        path = self.root / 'data' / 'jira_context.json'
        try:
            if not path.exists():
                return {'key': key, 'contextAvailable': False, 'error': 'Jira context has not been downloaded yet.'}
            if path.stat().st_size > CONTEXT_LIMIT:
                raise ValueError('Jira context file is too large.')
            doc = json.loads(path.read_text(encoding='utf-8-sig'))
            issues = doc.get('issues') if isinstance(doc, dict) else None
            if not isinstance(issues, dict):
                raise ValueError('Jira context format is invalid.')
            issue = issues.get(key)
            if not isinstance(issue, dict):
                return {'key': key, 'contextAvailable': False, 'error': 'No downloaded context for this task.'}
            return {**issue, 'key': key, 'contextAvailable': True}
        except (OSError, ValueError) as error:
            return {'key': key, 'contextAvailable': False, 'error': str(error)}

def handler(desk):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, value, content_type='application/json; charset=utf-8'):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Localhost only.'})
            path = urlparse(self.path).path
            if path == '/':
                return self.send(200, (ROOT / 'dashboard.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/tasks':
                return self.send(200, desk.view())
            if path == '/api/export':
                return self.send(200, desk.view())
            if path == '/api/health':
                return self.send(200, {'app': 'CCON BA Desk', 'version': VERSION})
            if path.startswith('/api/context/'):
                try:
                    return self.send(200, desk.context(unquote(path.split('/')[-1])))
                except ValueError as error:
                    return self.send(400, {'error': str(error)})
            return self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if not self.valid_host() or origin not in (f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'):
                return self.send(403, {'error': 'Local browser requests only.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > LIMIT:
                    raise ValueError('Request too large.')
                data = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(data, dict):
                    raise ValueError('Expected an object.')
                path = urlparse(self.path).path
                if path == '/api/import':
                    return self.send(200, desk.import_snapshot())
                if path.startswith('/api/tasks/'):
                    desk.save(unquote(path.split('/')[-1]), data)
                    return self.send(200, {'message': 'Saved locally.'})
                return self.send(404, {'error': 'Not found.'})
            except (ValueError, OSError) as e:
                return self.send(400, {'error': str(e)})

        def log_message(self, fmt, *args):
            pass
    return Handler

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--data-dir', type=Path, default=ROOT)
    p.add_argument('--open', action='store_true')
    args = p.parse_args()
    url = f'http://localhost:{args.port}'
    try:
        with build_opener(ProxyHandler({})).open(url + '/api/health', timeout=2) as response:
            running = json.load(response)
        if running.get('app') == 'CCON BA Desk':
            print(f'BA Desk already running: {url}', flush=True)
            if args.open:
                webbrowser.open(url)
            return
    except (OSError, ValueError):
        pass
    desk = Desk(args.data_dir)
    try:
        desk.import_snapshot()
    except ValueError as e:
        print(e)
    try:
        server = LocalServer(('127.0.0.1', args.port), handler(desk))
    except OSError:
        print(f'Port {args.port} is occupied. Stop the previous server or use --port 8766.', flush=True)
        return
    def watch():
        while not stop.wait(3):
            try:
                desk.import_snapshot()
            except ValueError:
                pass
    stop = threading.Event()
    threading.Thread(target=watch, daemon=True).start()
    print(f'CCON BA Desk: http://localhost:{args.port}\nData: {desk.db}\nCtrl+C to stop.', flush=True)
    if args.open:
        webbrowser.open(f'http://localhost:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()

if __name__ == '__main__':
    main()

