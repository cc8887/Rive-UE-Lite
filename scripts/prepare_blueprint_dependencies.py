#!/usr/bin/env python3
"""Fetch explicitly selected pinned UE payloads into this prototype only."""
from pathlib import Path
import argparse
import concurrent.futures
import fnmatch
import gzip
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--include',action='append',required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--plan',action='store_true')
    a=p.parse_args()
    manifest=ROOT/'engine/Engine/Build/Commit.gitdeps.xml'
    xml=ET.parse(manifest).getroot()
    blobs={n.attrib['Hash']:n.attrib for n in xml.find('Blobs')}
    packs={n.attrib['Hash']:n.attrib for n in xml.find('Packs')}
    selected=[n.attrib for n in xml.find('Files') if any(fnmatch.fnmatchcase(n.attrib['Name'],f) for f in a.include)]
    if not selected: p.error('No manifest file matched the explicit patterns')
    groups={}
    for f in selected: groups.setdefault(blobs[f['Hash']]['PackHash'],[]).append(f)
    def fetch(item):
        ph, files=item
        pending=[f for f in files if not (ROOT/'engine'/f['Name']).is_file() or
            hashlib.sha1((ROOT/'engine'/f['Name']).read_bytes()).hexdigest()!=f['Hash']]
        if pending and not a.plan:
            cache=ROOT/'dependencies/gitdeps-cache'/ph[:2]/ph
            if not cache.is_file():
                data=urllib.request.urlopen(f"{xml.attrib['BaseUrl']}/{packs[ph]['RemotePath']}/{ph}",timeout=120).read()
                cache.parent.mkdir(parents=True,exist_ok=True)
                temp=cache.with_suffix('.incoming-blueprint')
                temp.write_bytes(data);temp.replace(cache)
            raw=gzip.decompress(cache.read_bytes())
            assert hashlib.sha1(raw).hexdigest()==ph,ph
            for f in pending:
                blob=blobs[f['Hash']];start=int(blob['PackOffset']);size=int(blob['Size']);data=raw[start:start+size]
                assert hashlib.sha1(data).hexdigest()==f['Hash'],f['Name']
                dest=ROOT/'engine'/f['Name'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        return [{'path':f['Name'],'sha1':f['Hash'],'bytes':int(blobs[f['Hash']]['Size'])} for f in files]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        entries=[f for group in pool.map(fetch,groups.items()) for f in group]
    result={'status':'plan' if a.plan else 'verified','patterns':a.include,'files':entries,
        'bytes':sum(f['bytes'] for f in entries),'pack_compressed_bytes':sum(int(packs[h]['CompressedSize']) for h in groups),
        'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='files'}))

if __name__=='__main__': main()
