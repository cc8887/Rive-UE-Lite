#!/usr/bin/env python3
"""Reject LFS pointers, missing Rive libraries, and ELF/wrong-architecture archives."""
import argparse
import json
from pathlib import Path
import subprocess

LIBRARIES = ('liblibwebp.a', 'liblibpng.a', 'liblibjpeg.a', 'libminiaudio.a',
             'librive_sheenbidi.a', 'librive_harfbuzz.a', 'librive_decoders.a',
             'librive_pls_renderer.a', 'librive_yoga.a', 'librive.a')


def validate(folder, arch):
    if not folder.is_dir():
        raise RuntimeError('Missing native directory: '+str(folder))
    expected = 'arm64' if arch == 'arm64' else 'x86_64'
    for name in LIBRARIES:
        archive = folder/name
        if not archive.is_file() or archive.stat().st_size < 256:
            raise RuntimeError('Missing archive or LFS pointer: '+str(archive))
        result = subprocess.run(['xcrun', 'lipo', '-archs', str(archive)], capture_output=True, text=True, check=True)
        if expected not in result.stdout.split():
            raise RuntimeError('Wrong native archive architecture: '+str(archive)+' '+result.stdout)
    return {'architecture': arch, 'libraries': list(LIBRARIES), 'status': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=['arm64', 'x64'], required=True)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.folder, args.arch), indent=2))
