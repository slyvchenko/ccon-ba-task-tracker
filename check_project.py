"""Run the backend, frontend and release regression checks without packages."""
import shutil
import subprocess
import sys

from app_config import ROOT


def main():
    node = shutil.which('node')
    if not node:
        print('Node.js is required for frontend checks; the application itself only needs Python.', file=sys.stderr)
        return 1
    commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']]
    commands += [[node, '--check', str(path)] for path in sorted((ROOT / 'assets').glob('*.mjs'))]
    commands.append([node, '--test', '--test-isolation=none', *[str(path) for path in sorted((ROOT / 'tests').glob('*.test.mjs'))]])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
