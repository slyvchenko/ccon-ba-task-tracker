import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler
from zipfile import ZipFile

from app_config import ROOT
from build_release import build_release
from server import LocalServer, STATIC_FILES, handler


class StaticReleaseTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.parent / ('ccr-' + uuid.uuid4().hex[:12])
        self.root.mkdir()

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(self.parent) and target.name.startswith('ccr-')
        shutil.rmtree(target)

    def test_static_assets_have_correct_types_and_private_files_are_not_served(self):
        server = LocalServer(('127.0.0.1', 0), handler(None))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for url, (filename, mime) in STATIC_FILES.items():
                with self.subTest(url=url), opener.open(base + url) as response:
                    self.assertEqual(response.headers['Content-Type'], mime)
                    self.assertEqual(response.read(), (ROOT / filename).read_bytes())
            for url in ('/assets/../ba_state.db', '/assets/server.py', '/server.py', '/.jira-credentials.json', '/data/jira_context.json'):
                with self.subTest(url=url), self.assertRaises(HTTPError) as error:
                    opener.open(base + url)
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_release_includes_all_assets_and_imports_independently_of_workspace(self):
        output = build_release(self.root / 'desk.zip')
        with ZipFile(output) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertIsNone(archive.testzip())
            for filename, _ in STATIC_FILES.values():
                self.assertIn('ccon-ba-desk/' + filename, names)
            self.assertFalse(any('/data/' in name or '/logs/' in name or 'ba_state.db' in name or '.jira-credentials' in name for name in names))
            archive.extractall(self.root)
        environment = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        result = subprocess.run([sys.executable, '-c',
            'import server, desk_store, jira_sync, supplier_logs, log_attachments, apply_analysis; '
            'from pathlib import Path; assert server.ROOT == Path.cwd()'],
            cwd=self.root / 'ccon-ba-desk', env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_manifest_preserves_existing_release(self):
        output = self.root / 'desk.zip'
        output.write_bytes(b'previous release')
        for names in (['missing.py'], ['../outside.py'], ['source.py', 'source.py'], [{}]):
            (self.root / 'release_manifest.json').write_text(json.dumps(names), encoding='utf-8')
            with self.subTest(names=names), self.assertRaises(ValueError):
                build_release(output, self.root)
            self.assertEqual(output.read_bytes(), b'previous release')
