"""Apply/check the pinned Windows prototype patches, preserving unrelated edits."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PIN='62d7c1a7125b52b10ee1b714838f515f3563f795'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    p.add_argument('--with-tools',action='store_true')
    p.add_argument('--fetch-dependencies',action='store_true',help='Fetch pinned Windows binaries into this engine only')
    a=p.parse_args()
    engine=ROOT/'engine'
    def git(*args,env=None,input=None):
        return subprocess.run(['git','-C',str(engine),*args],capture_output=True,text=True,encoding='utf-8',env=env,input=input)
    if git('rev-parse','HEAD').stdout.strip()!=PIN: raise RuntimeError('Unexpected engine revision')
    numbers={1,2,3,4,5,6,7,9} if a.with_tools else {1,2}
    patches=[p for p in sorted((ROOT/'prototype/patches').glob('*.patch')) if int(p.name[:4]) in numbers]
    paths=sorted({name for p in patches for name in re.findall(r'^\+\+\+ b/(.+)$',p.read_text(encoding='utf-8'),re.M)})
    output=ROOT/'artifacts/windows'; output.mkdir(parents=True,exist_ok=True)
    changes=[]
    with tempfile.TemporaryDirectory(prefix='patch-index-',dir=output) as temp:
        env={**os.environ,'GIT_INDEX_FILE':str(Path(temp)/'index')}
        result=git('read-tree','--empty',env=env)
        if result.returncode: raise RuntimeError(result.stderr)
        # Populate only patch paths, not the entire UE source index on every build.
        entries=git('ls-tree','-r','-z','HEAD','--',*paths)
        if entries.returncode: raise RuntimeError(entries.stderr)
        result=git('update-index','-z','--index-info',env=env,input=entries.stdout)
        if result.returncode: raise RuntimeError(result.stderr)
        for patch in patches:
            result=git('apply','--cached',str(patch),env=env)
            if result.returncode: raise RuntimeError(result.stderr)
        for name in paths:
            path=(engine/name).resolve()
            if not path.is_relative_to(engine.resolve()): raise RuntimeError('Patch escapes independent engine')
            base=git('show','HEAD:'+name); desired=git('show',':'+name,env=env)
            if desired.returncode: raise RuntimeError(desired.stderr)
            current=path.read_text(encoding='utf-8') if path.exists() else None
            if current==desired.stdout: continue
            if current!=(base.stdout if base.returncode==0 else None): raise RuntimeError('Preserving conflicting source: '+name)
            changes.append((path,desired.stdout))
        if a.check and changes: raise RuntimeError('Required patches have not been applied')
        for path,text in changes:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding='utf-8',newline='\n')
    print('Windows patches verified: '+', '.join(p.name for p in patches))
    if a.fetch_dependencies:
        profiles=json.loads((ROOT/'scripts/windows-dependencies.json').read_text())
        patterns=profiles['runtime']+(profiles['tools'] if a.with_tools else [])
        args=[sys.executable,str(ROOT/'scripts/prepare_blueprint_dependencies.py')]
        for pattern in sorted(set(patterns)): args+=['--include',pattern]
        subprocess.run(args+['--report',str(output/'dependencies.json')],check=True)
        uba=engine/'Engine/Binaries/Win64/UnrealBuildAccelerator/x64/UbaHost.dll'
        dest=engine/'Engine/Binaries/DotNET/UnrealBuildTool/runtimes/win-x64/native/UbaHost.dll'
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or dest.read_bytes()!=uba.read_bytes(): shutil.copy2(uba,dest)

if __name__=='__main__': main()
