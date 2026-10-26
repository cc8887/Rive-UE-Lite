#!/usr/bin/env python3
"""Copy a verified package to the explicitly permitted disposable ext4 staging.

No links to development trees and no deletion/overwrite. Evidence stays in the
prototype. The total permitted staging budget is checked before copying.
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
from compare_png import sha256

ROOT=Path(__file__).resolve().parents[1]
# Resolve the exact permission from this checkout instead of embedding a local
# account identity or silently granting access to a different staging root.
_allowed=re.search(r'under (/home/[^ /]+/\.cache/rive-ue-lite-20261024) only', (ROOT/'AGENTS.md').read_text())
if not _allowed: raise RuntimeError('The explicit ext4 staging permission is missing from AGENTS.md')
CACHE=Path(_allowed.group(1))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--label',required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args(); source=a.package.resolve(); source.relative_to(ROOT/'package')
    if not re.fullmatch('[a-z0-9_-]+',a.label): p.error('Use a simple lowercase label')
    target=CACHE/'widget-animation-20261026'/a.label
    if target.exists(): p.error('Staging destination exists')
    target.resolve().relative_to(CACHE.resolve())
    payload=sum(f.stat().st_size for f in source.rglob('*') if f.is_file())
    used=int(subprocess.check_output(['du','-sb',str(CACHE)],text=True).split()[0])
    if used+payload>8*1024**3: p.error('Would exceed the 8 GiB staging budget')
    manifest=json.loads((source/'package-manifest.json').read_text())
    assert manifest['status']=='staged'
    shutil.copytree(source,target)
    assert all(sha256(target/f['path'])==f['sha256'] for f in manifest['files'])
    report={'status':'verified','source':str(source),'target':str(target),'copied_bytes':payload,
        'staging_total_bytes_before':used,'staging_budget_bytes':8*1024**3,
        'package_manifest_sha256':sha256(target/'package-manifest.json'),
        'reason':'Measure Linux deployment on ext4 without NTFS metadata overhead; package contents unchanged'}
    dest=a.report.resolve();dest.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__': main()
