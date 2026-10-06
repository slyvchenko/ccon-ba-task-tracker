"""CCON BA Desk — local, read-only toward Jira, persistent SQLite workspace."""
import argparse
import hashlib
import json
import re
import sqlite3
import threading
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent
STATUSES = ['AUTO', 'TODO', 'IN PROGRESS', 'WAITING', 'PARKED', 'DONE']
WAITING_ON = ['', 'SUPPLIER', 'REPORTER', 'PO', 'INTERNAL', 'DEPENDENCY', 'OTHER']
LIMIT = 5 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def meaningful_change(previous, current):
    """Conservative signal for reopening attention on locally DONE work."""
    if not previous:
        return False
    if current.get('changedSinceLastReview') in ('NEW', 'CHANGED'):
        return True
    if previous.get('jiraStatus') != current.get('jiraStatus'):
        return True
    if previous.get('latestChange') != current.get('latestChange'):
        return True
    return False


class Desk:
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
                key TEXT PRIMARY KEY,
                snapshot TEXT NOT NULL,
                manual_status TEXT NOT NULL DEFAULT 'AUTO',
                manual_waiting_on TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                review_again INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL,
                modified_at TEXT
              );
              CREATE TABLE IF NOT EXISTS imports (
                hash TEXT PRIMARY KEY,
                imported_at TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                count INTEGER NOT NULL
              );
            ''')
            columns = [r[1] for r in c.execute('PRAGMA table_info(tasks)')]
            if 'position' not in columns:
                c.execute('ALTER TABLE tasks ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
            if 'manual_waiting_on' not in columns:
                c.execute("ALTER TABLE tasks ADD COLUMN manual_waiting_on TEXT NOT NULL DEFAULT ''")
            if 'review_again' not in columns:
                c.execute('ALTER TABLE tasks ADD COLUMN review_again INTEGER NOT NULL DEFAULT 0')
            # Migrate old local workflow values from v1 without losing intent.
            c.execute("UPDATE tasks SET manual_status='WAITING' WHERE manual_status IN ('WAITING INPUT','WAITING DEPENDENCY')")
            c.execute("UPDATE tasks SET manual_status='TODO' WHERE manual_status='NEEDS DECISION'")

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
            string_fields = (
                'summary', 'analysisDepth', 'aiStatus', 'aiPriority', 'waitingOn', 'waitingEvidence',
                'nextAction', 'whyNextAction', 'definitionOfDone', 'readyOutput', 'readyOutputSubject',
                'readyOutputType', 'readyOutputTitle', 'jiraStatus', 'jiraPriority',
                'priority', 'url', 'taskBrief', 'currentSituation', 'surfaceAnalysis',
                'blockingReason', 'actionType', 'contactType', 'contactTarget',
                'contactPurpose', 'changedSinceLastReview', 'changeSummary', 'confidence'
            )
            array_fields = ('facts', 'hypotheses', 'unknowns', 'actionPlan', 'afterNextAction')
            for task in doc['tasks']:
                if not isinstance(task, dict) or not re.fullmatch(r'CCON-\d+', str(task.get('key', ''))):
                    raise ValueError('Every task needs a CCON-number key.')
                if task['key'] in keys:
                    raise ValueError('Duplicate task key: ' + task['key'])
                keys.add(task['key'])
                if not isinstance(task.get('summary'), str) or not task['summary'].strip():
                    raise ValueError('Every task needs a summary.')
                for field in string_fields:
                    if field in task and not isinstance(task[field], str):
                        raise ValueError(field + ' must be text.')
                for field in array_fields:
                    if field in task and (not isinstance(task[field], list) or not all(isinstance(x, str) for x in task[field])):
                        raise ValueError(field + ' must be a list of text values.')
                if 'blocking' in task and not isinstance(task['blocking'], bool):
                    raise ValueError('blocking must be true or false.')
                if 'contactNeeded' in task and not isinstance(task['contactNeeded'], bool):
                    raise ValueError('contactNeeded must be true or false.')
                if 'focusRank' in task and task['focusRank'] is not None and not isinstance(task['focusRank'], int):
                    raise ValueError('focusRank must be an integer or null.')
                if 'latestChange' in task and not isinstance(task['latestChange'], dict):
                    raise ValueError('latestChange must be an object.')

            with self.lock, self.connect() as c:
                if c.execute('SELECT 1 FROM imports WHERE hash=?', (digest,)).fetchone():
                    self.error = ''
                    return {'message': 'Snapshot already imported; manual changes preserved.'}
                latest = c.execute('SELECT generated_at FROM imports ORDER BY imported_at DESC LIMIT 1').fetchone()
                if latest and date < datetime.fromisoformat(latest[0].replace('Z', '+00:00')):
                    raise ValueError('Older snapshot rejected. Use the latest generatedAt timestamp.')

                old_rows = {r['key']: r for r in c.execute('SELECT key,snapshot,manual_status,review_again FROM tasks')}
                stamp = now()
                c.execute('UPDATE tasks SET active=0')
                for position, task in enumerate(doc['tasks']):
                    old = old_rows.get(task['key'])
                    review_again = int(old['review_again']) if old else 0
                    if old and old['manual_status'] == 'DONE':
                        previous = json.loads(old['snapshot'])
                        if meaningful_change(previous, task):
                            review_again = 1
                    c.execute('''
                      INSERT INTO tasks(key,snapshot,review_again,active,position,imported_at)
                      VALUES(?,?,?,1,?,?)
                      ON CONFLICT(key) DO UPDATE SET
                        snapshot=excluded.snapshot,
                        review_again=excluded.review_again,
                        imported_at=excluded.imported_at,
                        position=excluded.position,
                        active=1
                    ''', (task['key'], json.dumps(task, ensure_ascii=False), review_again, position, stamp))
                c.execute('INSERT INTO imports VALUES(?,?,?,?)', (digest, stamp, generated, len(keys)))
            self.error = ''
            return {'message': f'Imported {len(keys)} tasks. Manual workflow state preserved.'}
        except (ValueError, OSError, json.JSONDecodeError) as e:
            self.error = 'Import failed: ' + str(e)
            raise ValueError(self.error)

    def view(self):
        with self.lock, self.connect() as c:
            rows = c.execute('SELECT * FROM tasks ORDER BY active DESC, position, key').fetchall()
            latest = c.execute('SELECT * FROM imports ORDER BY imported_at DESC LIMIT 1').fetchone()
            tasks = []
            for row in rows:
                task = json.loads(row['snapshot'])
                task.update(
                    manualStatus=row['manual_status'],
                    manualWaitingOn=row['manual_waiting_on'],
                    note=row['note'],
                    reviewAgain=bool(row['review_again']),
                    active=bool(row['active']),
                    importedAt=row['imported_at'],
                    modifiedAt=row['modified_at']
                )
                tasks.append(task)
            return {'tasks': tasks, 'latest': dict(latest) if latest else None, 'error': self.error}

    def save(self, key, data):
        status = data.get('manualStatus')
        note = data.get('note')
        waiting_on = data.get('manualWaitingOn', '')
        clear_review = bool(data.get('clearReviewAgain', False))
        if status not in STATUSES:
            raise ValueError('Invalid manual status.')
        if not isinstance(note, str) or len(note) > 20000:
            raise ValueError('Invalid note (maximum 20,000 characters).')
        if waiting_on not in WAITING_ON:
            raise ValueError('Invalid waiting-on value.')
        if status != 'WAITING':
            waiting_on = ''
        with self.lock, self.connect() as c:
            current = c.execute('SELECT review_again FROM tasks WHERE key=?', (key,)).fetchone()
            if not current:
                raise ValueError('Unknown task.')
            review_again = int(current['review_again'])
            if clear_review or status != 'DONE':
                review_again = 0
            c.execute('''UPDATE tasks
                         SET manual_status=?, manual_waiting_on=?, note=?, review_again=?, modified_at=?
                         WHERE key=?''',
                      (status, waiting_on, note, review_again, now(), key))


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
            except (ValueError, OSError, json.JSONDecodeError) as e:
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
    desk = Desk(args.data_dir)
    try:
        desk.import_snapshot()
    except ValueError as e:
        print(e)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(desk))

    stop = threading.Event()

    def watch():
        while not stop.wait(3):
            try:
                desk.import_snapshot()
            except ValueError:
                pass

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
