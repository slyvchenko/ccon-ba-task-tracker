"""Local HTTP entrypoint; state, validation and mail services are separate modules."""
import argparse
import json
import os
import re
import socket
import sqlite3
import time
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, quote
from urllib.request import build_opener, ProxyHandler

from app_config import ROOT, STATUSES, LIMIT, CONTEXT_LIMIT, VERSION, SIGNALS, utc_now as now
from desk_store import Desk, SaveConflict
from mail_service import open_email_batch
from schema import text_field, validate_draft, validate_analysis
from review_report import render_markdown, validate_report, REPORT_LIMIT
from cloud_security import cloud_configuration, authorized
from pipeline_lock import pipeline_lock
from snapshot_monitor import SnapshotMonitor
from local_backup import create_backup, backup_status

STATIC_FILES = {
    '/': ('dashboard.html', 'text/html; charset=utf-8'),
    '/assets/dashboard.css': ('assets/dashboard.css', 'text/css; charset=utf-8'),
    '/assets/dashboard.mjs': ('assets/dashboard.mjs', 'text/javascript; charset=utf-8'),
    '/assets/task-rules.mjs': ('assets/task-rules.mjs', 'text/javascript; charset=utf-8'),
    '/assets/revision-policy.mjs': ('assets/revision-policy.mjs', 'text/javascript; charset=utf-8'),
    '/assets/manual-edit-policy.mjs': ('assets/manual-edit-policy.mjs', 'text/javascript; charset=utf-8'),
    '/assets/manual-done-undo.mjs': ('assets/manual-done-undo.mjs', 'text/javascript; charset=utf-8'),
    '/assets/draft-recovery.mjs': ('assets/draft-recovery.mjs', 'text/javascript; charset=utf-8'),
    '/assets/fast-handoff.mjs': ('assets/fast-handoff.mjs', 'text/javascript; charset=utf-8'),
    '/assets/handoff-ui-policy.mjs': ('assets/handoff-ui-policy.mjs', 'text/javascript; charset=utf-8'),
    '/assets/progressive-layout.mjs': ('assets/progressive-layout.mjs', 'text/javascript; charset=utf-8'),
    '/assets/visual-clarity.mjs': ('assets/visual-clarity.mjs', 'text/javascript; charset=utf-8'),
    '/assets/focus-navigation.mjs': ('assets/focus-navigation.mjs', 'text/javascript; charset=utf-8'),
    '/assets/effort-planning.mjs': ('assets/effort-planning.mjs', 'text/javascript; charset=utf-8'),
    '/assets/queue-performance.mjs': ('assets/queue-performance.mjs', 'text/javascript; charset=utf-8'),
    '/assets/reconnect-policy.mjs': ('assets/reconnect-policy.mjs', 'text/javascript; charset=utf-8'),
    '/assets/logs.mjs': ('assets/logs.mjs', 'text/javascript; charset=utf-8'),
    '/assets/evidence-ui.mjs': ('assets/evidence-ui.mjs', 'text/javascript; charset=utf-8'),
    '/assets/action-history.mjs': ('assets/action-history.mjs', 'text/javascript; charset=utf-8'),
    '/assets/decisions-ui.mjs': ('assets/decisions-ui.mjs', 'text/javascript; charset=utf-8'),
}

class LocalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can otherwise allow two different app versions on one port.
    allow_reuse_address = False
    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def handler(desk, cloud=None):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, value, content_type='application/json; charset=utf-8', filename=None):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'")
            if filename:
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(filename, safe=''))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            if cloud:
                return authorized(self.headers, cloud, self.command)
            return self.headers.get('Host') in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Access denied.'})
            path = urlparse(self.path).path
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                return self.send(200, (ROOT / filename).read_bytes(), content_type)
            if path == '/api/tasks/revision':
                return self.send(200, desk.revision())
            if path == '/api/tasks':
                return self.send(200, desk.view_json_bytes())
            if path == '/api/action-plan':
                from ba_actions import all_actions
                return self.send(200, all_actions(desk.root, desk.view()['tasks']))
            if re.fullmatch(r'/api/actions/CCON-\d+', path):
                from ba_actions import display_actions
                key = path.rsplit('/', 1)[-1]
                try:
                    return self.send(200, display_actions(desk.root, key))
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if re.fullmatch(r'/api/history/CCON-\d+', path):
                from urllib.parse import parse_qs
                key = path.rsplit('/', 1)[-1]
                try:
                    qs = parse_qs(urlparse(self.path).query)
                    limit = int(qs.get('limit', ['20'])[0])
                    offset = int(qs.get('offset', ['0'])[0])
                    return self.send(200, desk.history(key, limit, offset))
                except (ValueError, OSError, TypeError) as error:
                    return self.send(400, {'error': str(error)})
            if re.fullmatch(r'/api/approved/CCON-\d+', path):
                from approved_draft import describe
                key = path.rsplit('/', 1)[-1]
                try:
                    return self.send(200, describe(desk.root, key))
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if re.fullmatch(r'/api/questions/CCON-\d+', path):
                from question_candidates import questions_with_candidates
                key = path.rsplit('/', 1)[-1]
                try:
                    return self.send(200, questions_with_candidates(desk.root, key))
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if re.fullmatch(r'/api/decisions/CCON-\d+', path):
                from ba_questions import task_in_scope
                from ba_decisions import read_decisions
                key = path.rsplit('/', 1)[-1]
                try:
                    task_in_scope(desk.root, key)
                    return self.send(200, read_decisions(desk.root, key))
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if re.fullmatch(r'/api/evidence/CCON-\d+', path):
                from model_analysis import evidence_for_issue
                key = path.rsplit('/', 1)[-1]
                try:
                    from ba_questions import task_in_scope
                    task_in_scope(desk.root, key)
                    reports, version = evidence_for_issue(desk.root, key)
                    from storage import read_json
                    source = desk.root / 'data/investigations' / (key + '.json')
                    investigation = None
                    if source.is_file() and not source.is_symlink() and source.stat().st_size < 4 * 1024 * 1024:
                        candidate = read_json(source, {})
                        if isinstance(candidate, dict) and candidate.get('issueKey') == key:
                            investigation = {
                                field: candidate.get(field) for field in (
                                    'causality', 'supplier', 'sampling', 'scope', 'coverage',
                                    'analyzedCases', 'availableUniqueFlows',
                                    'requestedErrorCode', 'groups', 'hypotheses', 'questionsUk')
                            }
                    from evidence_health import health_for_issue
                    health = health_for_issue(desk.root, key)
                    return self.send(200, {'key': key, 'version': version,
                                           'reports': reports, 'investigation': investigation,
                                           'health': health})
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if path == '/api/export':
                return self.send(200, desk.view())
            if path == '/api/health':
                receipt = desk.root / 'data/last_daily_success.json'
                try:
                    run = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
                except (OSError, ValueError, TypeError):
                    run = None
                attempt_file = desk.root / 'data/last_daily_attempt.json'
                try:
                    attempt = json.loads(attempt_file.read_text(encoding='utf-8')) if attempt_file.exists() else None
                except (OSError, ValueError, TypeError):
                    attempt = None
                return self.send(200, {'app': 'CCON BA Desk', 'version': VERSION,
                                       'cloud': bool(cloud), 'lastSuccessfulDailyRun': run,
                                       'lastDailyAttempt': attempt,
                                       'localBackup': None if cloud else {
                                           **backup_status(desk.root),
                                           'backupCheckFailed': bool(getattr(desk, 'backup_failure', False))},
                                       'snapshotWatcher': getattr(desk, 'watcher_status',
                                                                 {'state': 'STARTING'})})
            if path in ('/api/daily-report', '/api/daily-report.md'):
                source = desk.root / 'data' / 'daily_review_report.json'
                if not source.exists():
                    if path.endswith('.md'):
                        return self.send(200, 'Щоденний звіт ще не сформовано.'.encode('utf-8'),
                                         'text/plain; charset=utf-8')
                    return self.send(200, {'available': False, 'message': 'No completed review yet.'})
                try:
                    if source.stat().st_size > REPORT_LIMIT:
                        raise ValueError('Daily report is too large.')
                    report = json.loads(source.read_text(encoding='utf-8-sig'))
                    validate_report(report)
                    latest = desk.view().get('latest')
                    if (latest and latest.get('generated_at') != report['generatedAt']):
                        # A newer Jira sync may already have been imported by
                        # the server watcher; never present an old report as
                        # the current task state.
                        return self.send(409, {'error': 'Daily report is stale relative to imported snapshot.'})
                    if path.endswith('.md'):
                        return self.send(200, render_markdown(report).encode('utf-8'),
                                         'text/markdown; charset=utf-8')
                    return self.send(200, report)
                except (OSError, ValueError, KeyError, TypeError):
                    return self.send(400, {'error': 'Daily report is invalid.'})
            if path == '/api/logs' or path.startswith('/api/logs/'):
                from log_attachments import log_catalog, download_archive
                try:
                    parts = [unquote(part) for part in path.split('/')]
                    if path == '/api/logs':
                        return self.send(200, log_catalog(desk))
                    if len(parts) == 4:
                        return self.send(200, log_catalog(desk, parts[3]))
                    if len(parts) == 6 and parts[5] == 'download':
                        filename, content = download_archive(desk, parts[3], parts[4])
                        return self.send(200, content, 'application/zip', filename)
                except (ValueError, OSError, KeyError, TypeError) as error:
                    return self.send(400, {'error': str(error)})
                return self.send(404, {'error': 'Not found.'})
            if path.startswith('/api/context/'):
                try:
                    return self.send(200, desk.context(unquote(path.split('/')[-1])))
                except ValueError as error:
                    return self.send(400, {'error': str(error)})
            return self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if not self.valid_host() or (not cloud and origin not in
                    (f'http://localhost:{self.server.server_port}',
                     f'http://127.0.0.1:{self.server.server_port}')):
                return self.send(403, {'error': 'Access denied.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > LIMIT:
                    raise ValueError('Request too large.')
                data = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(data, dict):
                    raise ValueError('Expected an object.')
                path = urlparse(self.path).path
                if cloud and (path == '/api/import' or path == '/api/email/open-batch' or
                              re.fullmatch(r'/api/logs/CCON-\d+/folder', path)):
                    return self.send(403, {'error': 'Windows-local workflow disabled in cloud.'})
                if re.fullmatch(r'/api/logs/CCON-\d+/folder', path):
                    from log_attachments import open_task_folder
                    return self.send(200, open_task_folder(desk, path.split('/')[3]))
                if path == '/api/email/open-batch':
                    return self.send(200, open_email_batch(data.get('items')))
                if path == '/api/import':
                    return self.send(200, desk.import_snapshot())
                if re.fullmatch(r'/api/decisions/CCON-\d+', path):
                    from ba_decisions import apply_decision
                    key = path.rsplit('/', 1)[-1]
                    result = apply_decision(desk.root, key,
                                            action=data.get('action'),
                                            identifier=data.get('id'),
                                            text=data.get('text', ''),
                                            source_url=data.get('sourceUrl', ''),
                                            impact=data.get('impact', ''),
                                            reason=data.get('reason', ''))
                    return self.send(200, result)
                if re.fullmatch(r'/api/actions/CCON-\d+', path):
                    from ba_actions import edit_action
                    key = path.rsplit('/', 1)[-1]
                    return self.send(200, edit_action(
                        desk.root, key, action=data.get('action', 'add'),
                        identifier=data.get('id'),
                        description=data.get('description', ''),
                        owner=data.get('owner', ''), due_date=data.get('dueDate', ''),
                        next_review_date=data.get('nextReviewDate', ''),
                        status=data.get('status', 'OPEN'),
                        waiting_on=data.get('waitingOn', ''), source='MANUAL'))
                if re.fullmatch(r'/api/approved/CCON-\d+', path):
                    from approved_draft import approve
                    key = path.rsplit('/', 1)[-1]
                    return self.send(200, approve(desk.root, key))
                if re.fullmatch(r'/api/questions/CCON-\d+/Q-[a-f0-9]{14}', path):
                    from ba_questions import update_question
                    parts = path.split('/')
                    answer = update_question(desk.root, parts[3], parts[4],
                                             status=data.get('status'),
                                             owner=data.get('owner', ''),
                                             answer=data.get('answer', ''),
                                             evidence_url=data.get('evidenceUrl', ''))
                    return self.send(200, {'question': answer})
                if re.fullmatch(r'/api/tasks/CCON-\d+', path):
                    result = desk.save(unquote(path.rsplit('/', 1)[-1]), data)
                    return self.send(200, {'message': 'Saved locally.', **result})
                return self.send(404, {'error': 'Not found.'})
            except SaveConflict as e:
                return self.send(409, {'error': str(e), 'code': 'TASK_REVISION_CONFLICT',
                                       'currentManualRevision': e.current_revision})
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
    p.add_argument('--cloud', action='store_true', help='Trusted reverse-proxy mode; internal Docker networking only.')
    args = p.parse_args()
    cloud = cloud_configuration() if args.cloud else None
    if not args.cloud and os.environ.get('CCON_CLOUD_MODE') == '1':
        raise ValueError("Refusing unauthenticated local-mode server when cloud mode is enabled.")
    url = f'http://localhost:{args.port}'
    try:
        if args.cloud:
            raise OSError('Cloud reverse proxy health checks must be authenticated.')
        with build_opener(ProxyHandler({})).open(url + '/api/health', timeout=2) as response:
            running = json.load(response)
        if running.get('app') == 'CCON BA Desk':
            print(f'BA Desk already running: {url}', flush=True)
            if args.open:
                webbrowser.open(url)
            return
    except (OSError, ValueError):
        pass
    try:
        # The same process lock is held throughout serve_forever and acquired
        # by offline recovery. An operator cannot replace the live database.
        with pipeline_lock(Path(args.data_dir) / ".local-server"):
            return serve_locked(args, cloud, url)
    except (OSError, ValueError, sqlite3.Error) as error:
        print("BA Desk startup/recovery check failed: " + str(error), flush=True)
        return 1


def serve_locked(args, cloud, url):
    # Before schema migration/import: safeguard the EXISTING user database.
    # Older SQLite schema versions are valid backups, and remain recoverable.
    if not cloud:
        create_backup(args.data_dir)
    desk = Desk(args.data_dir)
    try:
        desk.import_snapshot()
    except ValueError as error:
        print("Import warning: " + str(error), flush=True)
    if not cloud:
        # New installation: first post-import backup (no previous DB existed).
        create_backup(args.data_dir)
    monitor = SnapshotMonitor(desk)
    desk.watcher_status = monitor.status
    try:
        server = LocalServer(('0.0.0.0' if cloud else '127.0.0.1', args.port),
                             handler(desk, cloud))
    except OSError:
        print(f'Port {args.port} is occupied. Stop the previous server or use --port 8766.', flush=True)
        return 1
    stop = threading.Event()

    def watch():
        last_backup_check = 0.0
        while not stop.wait(3):
            try:
                monitor.check()
            except Exception:
                # The watcher must survive a broken source directory or
                # permission change, but expose a generic diagnostic.
                monitor.status["state"] = "FAILED"
                monitor.status["failures"] += 1
            if not cloud and time.monotonic() - last_backup_check >= 300:
                last_backup_check = time.monotonic()
                try:
                    create_backup(args.data_dir)
                    desk.backup_failure = False
                except (ValueError, OSError, sqlite3.Error):
                    desk.backup_failure = True
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    print(f'CCON BA Desk: {cloud["origin"] if cloud else url}\nData: {desk.db}\nCtrl+C to stop.', flush=True)
    if args.open and not cloud:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        watcher.join(timeout=5)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
