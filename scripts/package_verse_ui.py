#!/usr/bin/env python3
"""Stage Rive plus an optional VerseVM worker; exclude the build toolchain."""
from pathlib import Path
import argparse
import json
import shutil

from compare_png import sha256
from measure_ue_lite import inspect_package

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rive-package', type=Path, default=ROOT/'package/ui-rive-01')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report-dir', type=Path, required=True)
    a = p.parse_args()
    output, evidence = a.output.resolve(), a.report_dir.resolve()
    if not output.is_relative_to(ROOT/'package'):
        p.error('Output must be inside this prototype/package')
    if output.exists() or evidence.exists():
        p.error('Use fresh package and evidence directories')
    receipt = json.loads((ROOT/'Binaries/Linux/RiveVerseWorker.target').read_text())
    assert receipt['TargetName'] == 'RiveVerseWorker'
    base_manifest = json.loads((a.rive_package/'package-manifest.json').read_text())
    if base_manifest.get('target') != 'RiveRhiLite' or base_manifest.get('capabilities') != {'rive': True, 'umg': False}:
        p.error('This minimal bridge/package is qualified for the Rive-only renderer')
    shutil.copytree(a.rive_package.resolve(), output)
    (output/'package-manifest.json').unlink()
    evidence.mkdir(parents=True)
    worker = output/'worker'
    def stage(src, relative):
        destination = worker/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, destination)
    stage(ROOT/'Binaries/Linux/RiveVerseWorker', Path('Binaries/Linux/RiveVerseWorker'))
    stage(ROOT/'RiveRhiLite.uproject', Path('RiveRhiLite.uproject'))
    # Preserve the relative engine/VNI directory layout encoded by UBT/UHT.
    shutil.copytree(output/'Engine/Config', worker/'engine/Engine/Config')
    paths = ['engine/Engine/Plugins/Solaris/Source/VerseNative/Verse',
             'engine/Engine/Plugins/Solaris/Source/VersePredicts/Verse',
             'engine/Engine/Plugins/Verse/Verse/Source/Verse/Verse',
             'Source/RiveVerseWorker/Verse']
    for path in paths:
        for src in (ROOT/path).rglob('*'):
            if src.is_file() and src.suffix in ['.verse', '.vmodule']:
                stage(src, src.relative_to(ROOT))
    shutil.copytree(ROOT/'fixtures/verse', output/'fixtures/verse')
    for name in ['run_verse_ui.py', 'compare_png.py', 'measure_ue_lite.py']:
        (output/'scripts').mkdir(exist_ok=True)
        shutil.copy2(ROOT/'scripts'/name, output/'scripts'/name)
    (output/'verse-ui.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
PACKAGE_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$PACKAGE_ROOT/scripts/run_verse_ui.py" --worker "$PACKAGE_ROOT/worker/Binaries/Linux/RiveVerseWorker" --package "$PACKAGE_ROOT" "$@"
''')
    (output/'verse-ui.sh').chmod(0o755)
    files = [{'path': str(f.relative_to(output)), 'bytes': f.stat().st_size, 'sha256': sha256(f)}
        for f in sorted(output.rglob('*')) if f.is_file()]
    manifest = {'target': 'RiveRhiLite+RiveVerseWorker', 'capabilities': {'rive': True, 'umg': False, 'verse_vm': True},
        'transport': 'batch UI command bridge; worker restart per edit', 'files': files,
        'source_receipt_sha256': sha256(ROOT/'Binaries/Linux/RiveVerseWorker.target')}
    (output/'package-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    report = inspect_package(output, worker/'Binaries/Linux/RiveVerseWorker', evidence/'deploy-package.tar.gz')
    report['rive_base_package'] = str(a.rive_package.resolve())
    report['base_logical_bytes'] = sum(f.stat().st_size for f in a.rive_package.rglob('*') if f.is_file())
    report['added_logical_bytes'] = report['logical_file_bytes'] - report['base_logical_bytes']
    report['worker_files_bytes'] = sum(f.stat().st_size for f in worker.rglob('*') if f.is_file())
    report['runtime_requirements'] = 'Linux system libraries, Python3 and CPU Vulkan/Mesa from the base image; SDK/EpicClang/VNI generator/debug symbols excluded'
    (evidence/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ['status', 'logical_file_bytes', 'executable_bytes', 'added_logical_bytes', 'archive']}))

if __name__ == '__main__':
    main()
