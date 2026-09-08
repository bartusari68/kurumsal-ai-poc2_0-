"""Stage the complete comparison repo with a consistent live SQLite snapshot.

Run only after verification: python scripts/stage_phase_snapshot.py --phase 12
This stages files; it does not commit, push, reset, or rewrite the live database.
"""
import argparse
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    result = subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', *args], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8', check=True)
    if 'could not open directory' in result.stderr or 'Permission denied' in result.stderr:
        raise RuntimeError('Some comparison files are inaccessible; fix read access before publishing.\n' + result.stderr)
    return result.stdout.strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', type=int, required=True)
    args = parser.parse_args()
    if args.phase < 1: parser.error('phase must be positive')
    snapshot = ROOT / 'backups' / f'github-faz{args.phase}.db'
    with sqlite3.connect('file:' + (ROOT / 'data/app.db').as_posix() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(snapshot) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database snapshot integrity check failed')
    git('add', '--all')
    tracked = git('ls-files', '-z').split('\0')
    excluded = [name for name in tracked if any(part in ('.venv','venv') for part in Path(name).parts)
        or (Path(name).name.startswith('.env') and Path(name).name != '.env.example')]
    if excluded:
        raise RuntimeError('Environment files are staged; correct the index before publishing: ' + ', '.join(excluded))
    blob = git('hash-object', '-w', str(snapshot))
    git('update-index', '--cacheinfo', '100644,' + blob + ',data/app.db')
    print(f'Phase {args.phase}: complete comparison snapshot staged; live database unchanged.')
    print('Database snapshot:', snapshot.relative_to(ROOT).as_posix(), 'blob:', blob)
    print(git('diff', '--cached', '--shortstat'))

if __name__ == '__main__':
    main()
