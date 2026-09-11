"""Stage explicitly reviewed source files, per the user's Faz 13 publishing scope.

Run after tests and data preservation checks. This does not commit or push.
Example: python scripts/stage_phase_snapshot.py --phase 13 --paths app/portfolio.py
"""
import argparse
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
GENERATED_PARTS={'tmp','backups','__pycache__','.pytest_cache','.venv','venv','node_modules'}
GENERATED_SUFFIXES={'.pyc','.pyo','.db','.sqlite','.sqlite3','.log'}

def git(*args):
    return subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}',*args],cwd=ROOT,
        capture_output=True,text=True,encoding='utf-8',check=True).stdout.strip()

def allowed(name):
    p=Path(name)
    return not (set(p.parts)&GENERATED_PARTS or p.suffix.lower() in GENERATED_SUFFIXES or
                (p.name.startswith('.env') and p.name!='.env.example') or p.parts[0]=='data')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',type=int,required=True)
    parser.add_argument('--paths',nargs='+',required=True,help='Explicit reviewed file paths, not directories')
    args=parser.parse_args()
    if args.phase<1:parser.error('phase must be positive')
    paths=[]
    for name in args.paths:
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file():parser.error('Use an existing individual workspace file: '+name)
        relative=p.relative_to(ROOT).as_posix()
        if not allowed(relative):parser.error('Generated/environment/data file excluded: '+relative)
        paths.append(relative)
    staged=[p for p in git('diff','--cached','--name-only','-z').split('\0') if p]
    if any(not allowed(p) for p in staged):parser.error('The existing index contains excluded artifacts; review it before staging.')
    git('add','--',*paths)
    print(f'Phase {args.phase}: {len(paths)} reviewed source files staged; live data and historical artifacts untouched.')
    print(git('diff','--cached','--shortstat'))

if __name__=='__main__':main()
