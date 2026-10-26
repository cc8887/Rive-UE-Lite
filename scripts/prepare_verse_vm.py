#!/usr/bin/env python3
"""Materialize pinned optional Verse sources/tools inside the prototype only."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '62d7c1a7125b52b10ee1b714838f515f3563f795'
PATHS = ['Engine/Plugins/Solaris', 'Engine/Plugins/VerseVM',
         'Engine/Plugins/VerseInterface', 'Engine/Plugins/Verse',
         'Engine/Plugins/Experimental/PlatformCrypto',
         'Engine/Plugins/Experimental/LocalizableMessage']

def main():
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
    alternate = Path('/mnt/g/Github/UnrealEngine/.git/objects')
    if alternate.is_dir():
        env['GIT_ALTERNATE_OBJECT_DIRECTORIES'] = str(alternate)
    git = ['git', '-c', f'safe.directory={ROOT / "engine"}', '-C', str(ROOT/'engine')]
    head = subprocess.check_output([*git, 'rev-parse', 'HEAD'], env=env, text=True).strip()
    if head != COMMIT:
        raise RuntimeError(f'Verse integration is pinned to {COMMIT}, found {head}')
    payload = subprocess.check_output([*git, 'archive', COMMIT, *PATHS], env=env)
    files = []
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for entry in archive:
            if not entry.isfile():
                continue
            destination = (ROOT/'engine'/entry.name).resolve()
            if not destination.is_relative_to((ROOT/'engine').resolve()):
                raise RuntimeError(entry.name)
            data = archive.extractfile(entry).read()
            # Never overwrite an existing developer edit.
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            files.append({'path': entry.name, 'source_sha256': hashlib.sha256(data).hexdigest(),
                          'local_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
    evidence = ROOT/'artifacts/verse-vm'
    evidence.mkdir(parents=True, exist_ok=True)
    subprocess.run(['python3', str(ROOT/'scripts/prepare_blueprint_dependencies.py'),
        '--include', 'Engine/Binaries/Linux/EpicClang/20/bin/x64/*',
        '--include', 'Engine/Binaries/Linux/EpicClang/20/lib/*',
        '--include', 'Engine/Binaries/Linux/VerseCompilerCmd',
        '--include', 'Engine/Source/Runtime/AutoRTFM/*',
        '--include', 'Engine/Plugins/Solaris/*',
        '--include', 'Engine/Plugins/Verse/*',
        '--include', 'Engine/Plugins/VerseVM/*',
        '--report', str(evidence/'compiler-dependencies.json')], check=True)
    manifest = ET.parse(ROOT/'engine/Engine/Build/Commit.gitdeps.xml').getroot()
    for element in manifest.find('Files'):
        path = ROOT/'engine'/element.attrib['Name']
        if element.attrib.get('IsExecutable') == 'true' and path.is_file() and (
            '/EpicClang/20/' in path.as_posix() or path.name == 'VerseCompilerCmd'):
            path.chmod(path.stat().st_mode | 0o111)
    (evidence/'source-provenance.json').write_text(json.dumps({'commit': head, 'roots': PATHS, 'files': files}, indent=2)+'\n')
    cache = Path(os.environ.get('RIVE_LITE_CACHE_ROOT', '/home/yuchencui/.cache/rive-ue-lite-20261024'))
    runtime = cache/'engine-source/Runtime'
    if runtime.is_dir():
        shutil.copytree(ROOT/'engine/Engine/Source/Runtime/AutoRTFM', runtime/'AutoRTFM', dirs_exist_ok=True)
    print(f'Verse optional sources verified: {len(files)} files at {head}')

if __name__ == '__main__':
    main()
