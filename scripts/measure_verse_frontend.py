#!/usr/bin/env python3
"""Measure matched Core-only vs Verse semantic-frontend workers, not a Verse VM."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import statistics
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();out=a.output_dir.resolve()
    if out.exists() and any(out.iterdir()):p.error('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    affinity=sorted(os.sched_getaffinity(0))[:2];os.sched_setaffinity(0,affinity)
    result={'scope':'matched Core-only and parser/semantic analyzer workers; excludes bytecode generation, VM execution, Verse stdlib and UI bindings',
        'cpu_affinity':affinity,'runs':[],'binaries':{},'status':'incomplete'}
    for flavor,target in [('core','VerseCoreCostProbe'),('frontend','VerseFrontendCostProbe')]:
        exe=ROOT/'Binaries/Linux'/target;data=exe.read_bytes()
        packed=gzip.compress(data,compresslevel=9,mtime=0)
        (out/f'{target}.elf.gz').write_bytes(packed)
        result['binaries'][flavor]={'path':str(exe),'elf_bytes':len(data),'elf_gzip_bytes':len(packed),
            'sha256':hashlib.sha256(data).hexdigest()}
    for index in range(3):
        for case,flavor,functions in [('core','core',1),('one_function','frontend',1),('thousand_functions','frontend',1000)]:
            target='VerseCoreCostProbe' if flavor=='core' else 'VerseFrontendCostProbe'
            dest=out/f'{case}-{index}';dest.mkdir()
            cmd=[str(ROOT/'Binaries/Linux'/target),'-unattended','-stdout',f'-Report={dest}/compiler.json',
                f'-UserDir={dest}/user/',f'-Functions={functions}','-Iterations=10']
            started=time.perf_counter()
            with (dest/'process.log').open('wb') as log:
                run=subprocess.run(['/usr/bin/time','-v','-o',str(dest/'time.txt'),*cmd],cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,timeout=120)
            elapsed=time.perf_counter()-started
            report=json.loads((dest/'compiler.json').read_text())
            assert run.returncode==0 and report['valid']
            assert not report['vm_executed'] and not report['bytecode_generated']
            result['runs'].append({'case':case,'repeat':index,'command':cmd,'exit_code':run.returncode,
                'process_wall_ms':elapsed*1000,'native':report})
    result['delta_elf_bytes']=result['binaries']['frontend']['elf_bytes']-result['binaries']['core']['elf_bytes']
    result['delta_gzip_elf_bytes']=result['binaries']['frontend']['elf_gzip_bytes']-result['binaries']['core']['elf_gzip_bytes']
    result['metrics']={}
    for case in ['core','one_function','thousand_functions']:
        runs=[r for r in result['runs'] if r['case']==case]
        times=[x for r in runs for x in r['native']['semantic_ms']]
        result['metrics'][case]={'process_wall_ms_median':statistics.median(r['process_wall_ms'] for r in runs),
            'native_core_ready_ms_median':statistics.median(r['native']['core_ready_ms'] for r in runs),
            'native_frontend_ready_ms_median':statistics.median(r['native']['frontend_ready_ms'] for r in runs),
            'semantic_ms_median':statistics.median(times) if times else None,
            'semantic_ms_range':[min(times),max(times)] if times else None,
            'initial_frontend_setup_ms':[r['native']['frontend_ready_ms']-r['native']['core_ready_ms'] for r in runs]}
    result['status']='passed'
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'delta_elf_bytes':result['delta_elf_bytes'],
        'delta_gzip_elf_bytes':result['delta_gzip_elf_bytes'],'metrics':result['metrics']},indent=2))

if __name__=='__main__':main()
