"""Atomic JSON storage and path boundaries shared by Jira and log processing."""
import hashlib
import json
import os
import uuid
from pathlib import Path

from pipeline_lock import replace_file


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write_json(path, value, limit=None):
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    if limit is not None and len(raw) > limit:
        raise ValueError('Compact snapshot exceeds 5 MB; no import performed.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        # Regular files inherit the folder ACL on Windows.
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def inside(parent, relative):
    path = (parent / relative).resolve()
    if not path.is_relative_to(parent.resolve()):
        raise ValueError('Invalid stored log path.')
    return path
