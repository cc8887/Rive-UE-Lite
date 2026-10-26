#!/usr/bin/env python3
"""Compare actual deployed executable/dependency bytes; never inspect compression.

Count manifest-declared deployed files, also showing content/inode deduplication.
Generated workspaces, logs and caches are measured by the runtime benchmark.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def category(path):
    if path == 'toolkit-manifest.json' or path.endswith(('package-manifest.json', '.target')):
        return 'manifests_and_receipts'
    if '/Binaries/' in '/'+path and not '.so' in Path(path).name and Path(path).suffix == '':
        return 'native_executables'
    if '.so' in Path(path).name: return 'native_shared_libraries'
    if '/examples/' in '/'+path: return 'examples'
    if '/shaders/' in '/'+path: return 'precompiled_shaders'
    if '/Engine/Shaders/' in '/'+path: return 'editor_shader_sources'
    if '/Config/' in '/'+path or path.endswith('.uproject'): return 'configuration'
    if '/Content/' in '/'+path: return 'content_and_fonts'
    return 'cli_docs_and_other'


def inventory(root):
    manifest = json.loads((root/'toolkit-manifest.json').read_text())
    entries = {e['path']: e for e in manifest['files']}
    entries['toolkit-manifest.json'] = {'path':'toolkit-manifest.json', 'bytes':(root/'toolkit-manifest.json').stat().st_size,
                                       'sha256':sha(root/'toolkit-manifest.json')}
    result = {}
    for name, entry in entries.items():
        path = root/name
        stat = path.stat()
        assert stat.st_size == entry['bytes'], path
        assert sha(path) == entry['sha256'], path
        result[name] = {'bytes':stat.st_size, 'sha256':entry['sha256'], 'category':category(name),
                        'device':stat.st_dev, 'inode':stat.st_ino, 'allocated_bytes':stat.st_blocks*512}
    return result


def totals(items):
    entries = list(items.values())
    unique = {e['sha256']:e['bytes'] for e in entries}
    inodes = {(e['device'],e['inode']):(e['bytes'],e['allocated_bytes']) for e in entries}
    return {'files':len(entries), 'logical_file_bytes':sum(e['bytes'] for e in entries),
            'content_deduplicated_bytes':sum(unique.values()),
            'inode_deduplicated_bytes':sum(e[0] for e in inodes.values()),
            'allocated_bytes':sum(e[1] for e in inodes.values())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args(); out=a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh output directory')
    out.mkdir(parents=True)
    roots={'before':a.before.resolve(),'after':a.after.resolve()}
    inventories={name:inventory(path) for name,path in roots.items()}
    old,new=inventories['before'],inventories['after']
    names=sorted(set(old)|set(new))
    changes=[]
    for name in names:
        before,after=old.get(name),new.get(name)
        if before and after and before['sha256']==after['sha256']: continue
        changes.append({'path':name, 'kind':'added' if before is None else 'removed' if after is None else 'changed',
                        'category':(after or before)['category'], 'before_bytes':before['bytes'] if before else 0,
                        'after_bytes':after['bytes'] if after else 0,
                        'delta_bytes':(after['bytes'] if after else 0)-(before['bytes'] if before else 0)})
    groups={}
    for label in sorted({entry['category'] for inv in inventories.values() for entry in inv.values()}):
        groups[label]={when:totals({k:v for k,v in inv.items() if v['category']==label}) for when,inv in inventories.items()}
        groups[label]['logical_delta_bytes']=groups[label]['after']['logical_file_bytes']-groups[label]['before']['logical_file_bytes']
    components={}
    for component in ['rive','umg','verse','widget']:
        prefix=f'components/{component}/'
        components[component]={when:totals({k:v for k,v in inv.items() if k.startswith(prefix)}) for when,inv in inventories.items()}
        components[component]['logical_delta_bytes']=components[component]['after']['logical_file_bytes']-components[component]['before']['logical_file_bytes']
    elf_reports={}
    worker_rel='components/widget/Engine/Binaries/Linux/RiveUmgBlueprintWorker'
    for when,root in roots.items():
        worker=root/worker_rel
        readelf=subprocess.run(['readelf','-d',str(worker)],capture_output=True,text=True,check=True)
        (out/(when+'-elf-dynamic.txt')).write_text(readelf.stdout)
        import re
        needed=re.findall(r'\(NEEDED\).*?\[(.*?)\]',readelf.stdout)
        elf_reports[when]={'executable':worker_rel,'bytes':worker.stat().st_size,'needed':needed,'sha256':sha(worker)}
    totals_by_version={name:totals(inv) for name,inv in inventories.items()}
    report={'status':'passed','metric':'Actual uncompressed deployment files; no archive/compression measurement',
            'roots':{k:str(v) for k,v in roots.items()},'totals':totals_by_version,'categories':groups,'components':components,
            'changes':changes,'native_elf':elf_reports,
            'direct_needed_added':sorted(set(elf_reports['after']['needed'])-set(elf_reports['before']['needed'])),
            'notes':['Content deduplication is counted globally; group totals are not additive under cross-group sharing.',
                     'Allocated bytes use actual ext4 inode block allocation and hardlinks, and depend on filesystem block sizes.',
                     'Python, Mesa, libc and other system dependencies are host prerequisites and are audited separately in process maps.',
                     'The unchanged CLI/frontend modules reuse their previous deployment snapshots; only the Widget worker and CLI support changed.']}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'totals':totals_by_version,
                      'native_changes':[e for e in changes if e['category'] in ['native_executables','native_shared_libraries']]},indent=2))


if __name__=='__main__': main()
