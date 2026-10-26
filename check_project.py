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
    # The source-controlled backlog must never drift from its audit ledger.
    # Validation contains only requirement text and paths, no private Jira data.
    commands.append([sys.executable, 'backlog_audit.py', '--check'])
    commands += [[node, '--check', str(path)] for path in sorted((ROOT / 'assets').glob('*.mjs'))]
    commands.append([node, '--test', '--test-isolation=none', *[str(path) for path in sorted((ROOT / 'tests').glob('*.test.mjs'))]])
    # Synthetic smoke measurements print p50/p95 on this runner but have no
    # hard wallclock threshold (CI hardware is not the Windows BA laptop).
    commands.append([sys.executable, 'performance_smoke.py',
                     '--sizes', '100', '500', '1000', '--iterations', '5'])
    commands.append([node, 'queue_benchmark.mjs',
                     '--sizes', '100', '500', '1000', '--iterations', '5'])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
