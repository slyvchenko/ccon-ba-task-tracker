"""Non-blocking cross-process lock for one local sync/analysis pipeline."""
import os
import time
from contextlib import contextmanager
from pathlib import Path

def replace_file(source, target):
    """Windows readers/indexers can briefly prevent an atomic rename."""
    for attempt in range(6):
        try:
            Path(source).replace(target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.1 * (attempt + 1))


@contextmanager
def pipeline_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Keep the file after release: deleting it could let a third process lock a
    # different file while an existing handle still owns the original lock.
    with (root / '.pipeline.lock').open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another Jira sync or analysis import is running. '
                             'Wait for it to finish, then try again.') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
