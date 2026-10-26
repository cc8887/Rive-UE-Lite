#!/usr/bin/env python3
"""Materialize exact pinned Slate runtime payloads, never modifying another UE checkout."""
from pathlib import Path
import concurrent.futures
import gzip
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main():
    manifest = ROOT / 'engine/Engine/Build/Commit.gitdeps.xml'
    xml = ET.parse(manifest).getroot()
    blobs = {n.attrib['Hash']: n.attrib for n in xml.find('Blobs')}
    packs = {n.attrib['Hash']: n.attrib for n in xml.find('Packs')}
    selected = [n.attrib for n in xml.find('Files') if
        (n.attrib['Name'].startswith('Engine/Content/Slate/') and Path(n.attrib['Name']).suffix.lower() in ('.ttf','.png','.svg','.tps'))
        or n.attrib['Name'] == 'Engine/Binaries/ThirdParty/libsndfile/Linux/libsndfile.so.1']
    groups = {}
    for f in selected:
        groups.setdefault(blobs[f['Hash']]['PackHash'], []).append(f)
    def materialize(item):
        ph, files = item
        pack = packs[ph]
        cache = ROOT / 'dependencies/gitdeps-cache' / ph[:2] / ph
        pending = [f for f in files if not (ROOT/'engine'/f['Name']).is_file()
            or hashlib.sha1((ROOT/'engine'/f['Name']).read_bytes()).hexdigest() != f['Hash']]
        if pending:
            if not cache.is_file():
                url = f"{xml.attrib['BaseUrl']}/{pack['RemotePath']}/{ph}"
                data = urllib.request.urlopen(url, timeout=120).read()
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            content = gzip.decompress(cache.read_bytes())
            if hashlib.sha1(content).hexdigest() != ph:
                raise RuntimeError(f'Pack integrity mismatch: {ph}')
            for f in pending:
                b = blobs[f['Hash']]
                start, size = int(b['PackOffset']), int(b['Size'])
                data = content[start:start+size]
                if hashlib.sha1(data).hexdigest() != f['Hash']:
                    raise RuntimeError(f"Blob integrity mismatch: {f['Name']}")
                dest = ROOT / 'engine' / f['Name']
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        return [{'path':f['Name'], 'sha1':f['Hash'], 'bytes':int(blobs[f['Hash']]['Size'])} for f in files]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        entries = [f for batch in pool.map(materialize, groups.items()) for f in batch]
    dest = ROOT/'artifacts/umg-optional/content.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'status':'verified', 'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'files':entries, 'bytes':sum(f['bytes'] for f in entries)},indent=2)+'\n')
    print(json.dumps({'files':len(entries),'bytes':sum(f['bytes'] for f in entries),'report':str(dest)}))

if __name__ == '__main__':
    main()
