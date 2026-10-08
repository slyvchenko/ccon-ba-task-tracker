"""SQLite task state and validated snapshot/context access."""
import hashlib
import json
import sqlite3
import threading
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from app_config import CONTEXT_LIMIT, LIMIT, STATUSES, utc_now as now
from schema import text_field, validate_analysis, validate_draft

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
