#!/usr/bin/env python3
"""Measure an actual single translation-unit rebuild and relink in one selected flavor."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--with-umg',action='store_true')
    p.add_argument('--verse-worker',action='store_true')
    p.add_argument('--via-ui-build',action='store_true',help='Measure the complete optional Verse build entry, including preparation and the default target check')
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()): p.error('Use a fresh directory')
    out.mkdir(parents=True,exist_ok=True)
    if a.with_umg and a.verse_worker: p.error('Choose one target to measure')
    if a.via_ui_build and not a.verse_worker: p.error('--via-ui-build requires --verse-worker')
    target='RiveVerseWorker' if a.verse_worker else 'RiveUmgHost' if a.with_umg else 'RiveRhiLite'
    source=ROOT/'Source'/target/('Private/VerseCmd.cpp' if a.verse_worker else 'Private/Main.cpp')
    before=source.stat()
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    cmd=['bash',str(ROOT/'scripts/build_ui.sh')]
    if a.verse_worker:
        cmd = ['bash',str(ROOT/'scripts/build_ui.sh'),'--with-verse'] if a.via_ui_build else ['bash',str(ROOT/'scripts/build_linux_cached.sh'),target]
    if a.with_umg: cmd.append('--with-umg')
    cmd+=['-NoMutex','-MaxParallelActions=12',f'-Log={out}/build.log']
    started=time.perf_counter()
    try:
        # Invalidate one TU using its input mtime. Its source bytes stay identical.
        os.utime(source,None)
        with (out/'console.log').open('wb') as log:
            proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
    finally:
        os.utime(source,ns=(before.st_atime_ns,before.st_mtime_ns))
    wall=time.perf_counter()-started
    log=(out/'build.log').read_text(errors='replace')
    actions=re.findall(r'^\[\d+/\d+\] (.+)$',log,re.M)
    compile_actions=[x for x in actions if x.startswith('Compile ')]
    links=[x for x in actions if x.startswith('Link ')]
    ubt=re.findall(r'Total execution time: ([0-9.]+) seconds',log)
    report={'status':'passed' if proc.returncode==0 and len(compile_actions)==1 and len(links)==1 else 'failed',
        'target':target,'command':cmd,'wall_seconds':wall,'ubt_seconds':float(ubt[-1]) if ubt else None,
        'source':str(source),'source_sha256':digest,'source_bytes_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==digest,
        'invalidation':f'touch one {source.name}; content unchanged, original mtime restored after actual compile/link',
        'compile_actions':compile_actions,'link_actions':links,'all_actions':actions,'exit_code':proc.returncode,
        'scope':'one cached Linux Development monolithic translation-unit rebuild, full Link action includes symbol processing; not a cold build'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__': raise SystemExit(main())
