import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from storage import read_json, write_json


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.parent / ('ccj-' + uuid.uuid4().hex[:12])
        self.root.mkdir()

    def tearDown(self):
        target = self.root.resolve()
        assert target.is_relative_to(self.parent) and target.name.startswith('ccj-')
        shutil.rmtree(target)

    def test_failed_atomic_replace_keeps_previous_document_and_removes_temporary(self):
        target = self.root / 'state.json'
        write_json(target, {'state': 'previous'})
        with patch('storage.replace_file', side_effect=OSError('busy')), self.assertRaises(OSError):
            write_json(target, {'state': 'next'})
        self.assertEqual(read_json(target), {'state': 'previous'})
        self.assertEqual(list(self.root.glob('*.pending')), [])

    def test_limit_is_measured_in_utf8_bytes_before_replacing_existing_document(self):
        target = self.root / 'state.json'
        write_json(target, {'state': 'previous'})
        with self.assertRaises(ValueError):
            write_json(target, {'state': 'Український текст'}, limit=20)
        self.assertEqual(read_json(target), {'state': 'previous'})
