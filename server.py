"""Local HTTP entrypoint; state, validation and mail services are separate modules."""
import argparse
import json
import os
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, quote
from urllib.request import build_opener, ProxyHandler

from app_config import ROOT, STATUSES, LIMIT, CONTEXT_LIMIT, VERSION, SIGNALS, utc_now as now
from desk_store import Desk
from mail_service import open_email_batch
from schema import text_field, validate_draft, validate_analysis

STATIC_FILES = {
    '/': ('dashboard.html', 'text/html; charset=utf-8'),
    '/assets/dashboard.css': ('assets/dashboard.css', 'text/css; charset=utf-8'),
    '/assets/dashboard.mjs': ('assets/dashboard.mjs', 'text/javascript; charset=utf-8'),
    '/assets/task-rules.mjs': ('assets/task-rules.mjs', 'text/javascript; charset=utf-8'),
    '/assets/logs.mjs': ('assets/logs.mjs', 'text/javascript; charset=utf-8'),
}

class LocalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can otherwise allow two different app versions on one port.
    allow_reuse_address = False
    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def handler(desk):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, value, content_type='application/json; charset=utf-8', filename=None):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(filename, safe=''))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Localhost only.'})
            path = urlparse(self.path).path
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                return self.send(200, (ROOT / filename).read_bytes(), content_type)
            if path == '/api/tasks':
                return self.send(200, desk.view())
            if path == '/api/export':
                return self.send(200, desk.view())
            if path == '/api/health':
                return self.send(200, {'app': 'CCON BA Desk', 'version': VERSION})
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
                if re.fullmatch(r'/api/logs/CCON-\d+/folder', path):
                    from log_attachments import open_task_folder
                    return self.send(200, open_task_folder(desk, path.split('/')[3]))
                if path == '/api/email/open-batch':
                    return self.send(200, open_email_batch(data.get('items')))
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
