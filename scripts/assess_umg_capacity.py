#!/usr/bin/env python3
"""Measure existing binaries and matched-content archives, without building UMG.

These archives are capacity samples, not runnable or validated UMG packages.
Slate fonts, Slate shaders and project UI assets are deliberately not invented.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--gzip-level', type=int, choices=range(1, 10), default=9)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('use a fresh assessment directory')
    output.mkdir(parents=True, exist_ok=True)
    package = root / 'package/playback-02'
    package_manifest = package / 'package-manifest.json'
    manifest = json.loads(package_manifest.read_text())
    lite = package / 'Engine/Binaries/Linux/RiveRhiLite'
    reference = root / 'Binaries/Linux/RiveUeReference'
    old_files = {row['path']: row for row in manifest['files']}
    for name, entry in old_files.items():
        file = package / name
        if file.stat().st_size != entry['bytes'] or sha256(file) != entry['sha256']:
            raise RuntimeError(f'package input changed: {file}')
    # Exclude the old launcher and manifest rather than shipping misleading ones.
    resources = [(package / name, name) for name in sorted(old_files)
                 if name not in ('Engine/Binaries/Linux/RiveRhiLite', 'render.sh')]
    receipt = json.loads((root / 'Binaries/Linux/RiveUeReference.target').read_text())
    extras, missing = [], []
    engine = root / 'engine/Engine'
    for entry in receipt.get('RuntimeDependencies', []):
        source = Path(entry['Path'].replace('$(ProjectDir)', str(root)).replace('$(EngineDir)', str(engine)))
        try:
            name = 'Engine/' + source.relative_to(engine).as_posix()
        except ValueError:
            name = source.relative_to(root).as_posix()
        if name in old_files:
            continue
        if source.is_file():
            extras.append((source, name))
        else:
            missing.append(str(source))
    marker = json.dumps({'deployable': False, 'umg_rendered': False,
                         'scope': 'matched-content size sample only; no Slate UI shader/font cook or UMG execution'}, indent=2).encode()
    samples = {}
    for name, executable, additions in (('lite', lite, []), ('engine_umg_linked_reference', reference, extras)):
        files = [*resources, (executable, 'Engine/Binaries/Linux/' + executable.name), *additions]
        target = output / (name + '.capacity-only.tar.gz')
        before = {str(path): sha256(path) for path, _ in files}
        started = time.perf_counter()
        with tarfile.open(target, 'w:gz', compresslevel=args.gzip_level) as archive:
            for source, arcname in files:
                archive.add(source, arcname=arcname, recursive=False)
            header = tarfile.TarInfo('ASSESSMENT_ONLY.json')
            header.size = len(marker)
            archive.addfile(header, io.BytesIO(marker))
        after = {str(path): sha256(path) for path, _ in files}
        if before != after:
            raise RuntimeError('capacity sample input changed while compressing')
        samples[name] = {'deployable': False, 'umg_rendered': False,
                         'logical_bytes': sum(path.stat().st_size for path, _ in files) + len(marker),
                         'executable_bytes': executable.stat().st_size, 'executable_sha256': sha256(executable),
                         'gzip_bytes': target.stat().st_size, 'gzip_sha256': sha256(target),
                         'archive': str(target), 'file_count': len(files) + 1,
                         'compression_wall_seconds': time.perf_counter() - started,
                         'extra_receipt_files': [{'path': str(path), 'archive_path': arcname,
                                                  'bytes': path.stat().st_size, 'sha256': sha256(path)}
                                                 for path, arcname in additions]}
    report = {'status': 'measured_capacity_only', 'scope': 'existing ELF and controlled matched resources; not a built/rendered UMG prototype',
              'source_package_manifest_sha256': sha256(package_manifest),
              'samples': samples, 'reference_receipt_missing_files': missing,
              'not_included': ['normal Slate global shaders', 'UI material shaders', 'Slate fonts/styles not staged in the reference target',
                               'Widget Blueprint assets', 'UMGEditor/UnrealEd/Designer', 'external system library/CPU Vulkan driver closure'],
              'actual_cpp_build_executed': False, 'actual_umg_capture_executed': False}
    report['gzip_level'] = args.gzip_level
    report['elf_growth_bytes'] = reference.stat().st_size - lite.stat().st_size
    report['elf_growth_ratio'] = reference.stat().st_size / lite.stat().st_size
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
