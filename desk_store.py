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
from task_history import init as init_history, append as history_append, view_state, history_page

class SaveConflict(ValueError):
    """Task was changed by another editor; no private content in error."""
    def __init__(self, revision):
        super().__init__("Task edited elsewhere. Review the saved version before retry.")
        self.current_revision = revision


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
              CREATE TABLE IF NOT EXISTS state_revision (
                id INTEGER PRIMARY KEY CHECK (id = 1), revision INTEGER NOT NULL);
              INSERT OR IGNORE INTO state_revision(id,revision) VALUES(1,0);
              CREATE TABLE IF NOT EXISTS imports (
                hash TEXT PRIMARY KEY, imported_at TEXT NOT NULL, generated_at TEXT NOT NULL,
                count INTEGER NOT NULL);
            ''')
            init_history(c)
            # Preserve earlier supported local SQLite schemas on upgrade.
            if 'active' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
            if 'modified_at' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN modified_at TEXT')
            if 'position' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
            if 'email_draft' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN email_draft TEXT DEFAULT NULL')
            if 'manual_revision' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute('ALTER TABLE tasks ADD COLUMN manual_revision INTEGER NOT NULL DEFAULT 0')
            if 'manual_effort' not in [r[1] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute("ALTER TABLE tasks ADD COLUMN manual_effort TEXT NOT NULL DEFAULT 'UNKNOWN'")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        # Explicitly keep SQLite's strongest ordinary rollback-journal commit
        # synchronization even when a caller changed connection defaults.
        # Hardware power-loss durability still needs device-level validation.
        c.execute('PRAGMA synchronous=FULL')
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
                prior = {row['key']: row for row in c.execute('SELECT * FROM tasks')}
                c.execute('UPDATE tasks SET active=0')
                for position, task in enumerate(doc['tasks']):
                    c.execute('''INSERT INTO tasks(key,snapshot,imported_at,position) VALUES(?,?,?,?)
                      ON CONFLICT(key) DO UPDATE SET snapshot=excluded.snapshot,
                      imported_at=excluded.imported_at, position=excluded.position, active=1''',
                      (task['key'], json.dumps(task, ensure_ascii=False), stamp, position))
                    persisted = c.execute('SELECT * FROM tasks WHERE key=?', (task['key'],)).fetchone()
                    draft = json.loads(persisted['email_draft']) if persisted['email_draft'] else None
                    history_append(c, task['key'], view_state(task,
                        persisted['manual_status'], persisted['note'], draft, True), 'IMPORT')
                for previous_key, row in prior.items():
                    if previous_key not in keys and row['active']:
                        old = json.loads(row['snapshot'])
                        draft = json.loads(row['email_draft']) if row['email_draft'] else None
                        history_append(c, previous_key, view_state(
                            old, row['manual_status'], row['note'], draft, False), 'IMPORT')
                c.execute('INSERT INTO imports VALUES(?,?,?,?)', (digest, stamp, generated, len(keys)))
                c.execute('UPDATE state_revision SET revision=revision+1 WHERE id=1')
            self.error = ''
            return {'message': f'Imported {len(keys)} tasks. Manual status and notes preserved.'}
        except (ValueError, OSError) as e:
            self.error = 'Import failed: ' + str(e)
            raise ValueError(self.error)

    def _view_on_connection(self, c, revision=None):
        rows = c.execute('SELECT * FROM tasks ORDER BY active DESC, position, key').fetchall()
        latest = c.execute('SELECT * FROM imports ORDER BY imported_at DESC LIMIT 1').fetchone()
        tasks = []
        for row in rows:
            task = json.loads(row['snapshot'])
            task.update(manualStatus=row['manual_status'], note=row['note'], active=bool(row['active']),
                        importedAt=row['imported_at'], modifiedAt=row['modified_at'],
                        savedEmailDraft=json.loads(row['email_draft']) if row['email_draft'] else None,
                        manualRevision=row['manual_revision'],
                        manualEffort=row['manual_effort'])
            tasks.append(task)
        if revision is None:
            revision = c.execute('SELECT revision FROM state_revision WHERE id=1').fetchone()[0]
        return {'tasks': tasks, 'latest': dict(latest) if latest else None,
                'error': self.error, 'revision': revision}

    def view(self):
        # Keep the object-based API independent of cache mutation by clients.
        with self.lock, self.connect() as c:
            # sqlite3's context manager does not BEGIN for SELECT. Without an
            # explicit read snapshot, tasks and revision can be from two imports.
            c.execute('BEGIN')
            return self._view_on_connection(c)

    def view_json_bytes(self):
        """Fast full HTTP snapshot: cached immutable bytes per committed revision.

        Rechecks SQLite on every call so writes from a second Desk instance
        invalidate the cache. Error changes invalidate without a DB write.
        Never cache mutable dicts or leak a stale pre-transaction response.
        """
        with self.lock, self.connect() as c:
            # Explicit read transaction makes revision + rows an atomic view,
            # including while another app process commits a snapshot.
            c.execute('BEGIN')
            revision = c.execute('SELECT revision FROM state_revision WHERE id=1').fetchone()[0]
            cache_key = (revision, self.error)
            if getattr(self, '_http_cache_key', None) == cache_key:
                return self._http_cache_body
            payload = self._view_on_connection(c, revision)
            encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self._http_cache_key = cache_key
            self._http_cache_body = encoded
            return encoded

    def revision(self):
        """Small poll token. Read one row; never materialize source tasks."""
        with self.lock, self.connect() as c:
            version = c.execute('SELECT revision FROM state_revision WHERE id=1').fetchone()[0]
            return {'revision': version, 'error': self.error}

    def save(self, key, data):
        status, note = data.get('manualStatus'), data.get('note')
        expected = data.get('expectedManualRevision')
        if 'expectedManualRevision' in data and (type(expected) is not int or expected < 0):
            raise ValueError('expectedManualRevision must be a nonnegative integer.')
        if 'requireActiveTask' in data and data['requireActiveTask'] is not True:
            raise ValueError('requireActiveTask must be true when specified.')
        if status not in STATUSES or not isinstance(note, str) or len(note) > 20000:
            raise ValueError('Invalid manual status or note (maximum 20,000 characters).')
        if 'emailDraft' in data and data['emailDraft'] is not None:
            validate_draft(data['emailDraft'])
        if 'manualEffort' in data and data['manualEffort'] not in (
                'UNKNOWN', 'XS', 'S', 'M', 'L', 'XL'):
            raise ValueError('manualEffort must be UNKNOWN, XS, S, M, L or XL.')
        with self.lock, self.connect() as c:
            values = [status, note, now()]
            query = 'UPDATE tasks SET manual_status=?, note=?, modified_at=?, manual_revision=manual_revision+1'
            if 'emailDraft' in data:
                query += ', email_draft=?'
                draft = data['emailDraft']
                values.append(json.dumps({field: draft[field] for field in ('to', 'subject', 'body')}, ensure_ascii=False) if draft is not None else None)
            if 'manualEffort' in data:
                query += ', manual_effort=?'
                values.append(data['manualEffort'])
            query += ' WHERE key=?'
            values.append(key)
            # Atomic compare-and-swap even across independent server processes.
            # Legacy external scripts without a version remain compatible.
            if 'expectedManualRevision' in data:
                query += ' AND manual_revision=?'
                values.append(expected)
            # Undo must never revive a task that left Jira scope between polls.
            # Keep the active condition inside the same atomic CAS update.
            if data.get('requireActiveTask') is True:
                query += ' AND active=1'
            if not c.execute(query, values).rowcount:
                current = c.execute('SELECT manual_revision FROM tasks WHERE key=?', (key,)).fetchone()
                if current is None:
                    raise ValueError('Unknown task.')
                raise SaveConflict(current['manual_revision'])
            row = c.execute('SELECT * FROM tasks WHERE key=?', (key,)).fetchone()
            saved_draft = json.loads(row['email_draft']) if row['email_draft'] else None
            history_append(c, key, view_state(json.loads(row['snapshot']),
                row['manual_status'], row['note'], saved_draft, bool(row['active'])), 'MANUAL')
            c.execute('UPDATE state_revision SET revision=revision+1 WHERE id=1')
            return {'manualRevision': row['manual_revision']}

    def history(self, key, limit=20, offset=0):
        with self.lock, self.connect() as c:
            if not c.execute('SELECT 1 FROM tasks WHERE key=?', (key,)).fetchone():
                raise ValueError('Unknown task.')
            return history_page(c, key, limit, offset)

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
