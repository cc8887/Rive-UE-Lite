#!/usr/bin/env python3
"""Stage an isolated source Widget Blueprint worker, without build SDK/tools.

Includes the native receipt, configuration, available Slate/fonts, and native
shader sources required by Editor shader hashing even with precompiled shaders.
Linux CPU Vulkan and standard OS libraries remain explicit host prerequisites.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', type=Path, default=ROOT/'Binaries/Linux/RiveUmgBlueprintWorker')
    p.add_argument('--receipt', type=Path, default=ROOT/'Binaries/Linux/RiveUmgBlueprintWorker.target')
    p.add_argument('--shader-archive', type=Path, default=ROOT/'artifacts/umg-blueprint/shaders-host/global.bin')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--strip', default='strip', help='Strip unneeded ELF symbols in staged copies only')
    p.add_argument('--content-dir', type=Path, help='Optional source .uasset examples, copied into Content/')
    a = p.parse_args()
    out = a.output.resolve(); out.relative_to(ROOT)
    if out.exists(): p.error('Use a fresh package directory')
    receipt = json.loads(a.receipt.read_text())
    if receipt['TargetName'] != 'RiveUmgBlueprintWorker': p.error('Unexpected native receipt')
    engine = ROOT/'engine/Engine'; out.mkdir(parents=True)
    files = {}; missing = []; excluded = []

    def stage(src, rel):
        rel = Path(rel); target = out/rel
        if not src.is_file(): missing.append(str(src)); return
        if rel.as_posix() in files: return
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, target)
        with target.open('rb') as data: is_elf = data.read(4) == b'\x7fELF'
        if is_elf: subprocess.run([a.strip, '--strip-unneeded', str(target)], check=True)
        files[rel.as_posix()] = {'path': rel.as_posix(), 'bytes': target.stat().st_size, 'sha256': sha256(target)}

    for item in receipt.get('BuildProducts', []) + receipt.get('RuntimeDependencies', []):
        if item.get('Type') in ['SymbolFile', 'MapFile', 'DebugNonUFS']: continue
        src = Path(item['Path'].replace('$(EngineDir)', str(engine)).replace('$(ProjectDir)', str(ROOT)))
        if src.suffix in ['.debug', '.sym', '.map']: continue
        if src.name == 'EpicWebHelper':
            excluded.append({'path': item['Path'], 'reason': 'CEF disabled by this target; no browser functionality; scoped native execution validates its absence'})
            continue
        if item.get('Type') == 'Executable':
            stage(a.worker.resolve(), 'Engine/Binaries/Linux/RiveUmgBlueprintWorker'); continue
        try: rel = Path('Engine')/src.relative_to(engine)
        except ValueError: rel = src.relative_to(ROOT)
        stage(src, rel)
    for folder in ['Config', 'Content/Slate', 'Content/SlateDebug', 'Content/EngineFonts', 'Shaders']:
        for src in sorted((engine/folder).rglob('*')):
            if src.is_file(): stage(src, Path('Engine')/src.relative_to(engine))
    for src in sorted((ROOT/'Config').rglob('*.ini')): stage(src, src.relative_to(ROOT))
    stage(ROOT/'RiveRhiLite.uproject', 'RiveRhiLite.uproject')
    stage(ROOT/'scripts/widget_bp.py', 'scripts/widget_bp.py')
    stage(ROOT/'scripts/measure_no_gpu.sh', 'scripts/measure_no_gpu.sh')
    stage(a.shader_archive.resolve(), 'shaders/global.bin')
    stage(a.receipt.resolve(), 'worker.target')
    for src in sorted((ROOT/'fixtures/widget-blueprint').iterdir()):
        if src.is_file() and src.suffix in ['.json', '.png', '.jpg']: stage(src, Path('examples')/src.name)
    if a.content_dir:
        for src in sorted(a.content_dir.resolve().rglob('*.uasset')):
            stage(src, Path('Content')/src.relative_to(a.content_dir.resolve()))
    library_dirs = sorted({str(Path(rel).parent) for rel in files if '.so' in Path(rel).name})
    # Keep the same native invocation surface for baseline and animation builds.
    launcher = out/'worker.sh'
    launcher.write_text('''#!/usr/bin/env bash
set -euo pipefail
WORKER_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
export VK_ICD_FILENAMES="${VK_ICD_FILENAMES:-/usr/share/vulkan/icd.d/lvp_icd.json}"
export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
export LD_LIBRARY_PATH="'''+':'.join('$WORKER_ROOT/'+rel for rel in library_dirs)+'''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$WORKER_ROOT/Engine/Binaries/Linux/RiveUmgBlueprintWorker" -unattended -stdout -NoSplash -NoCrashDialog \
    "-ProjectDir=$WORKER_ROOT/" "$@"
''', newline='\n')
    launcher.chmod(0o755)
    files['worker.sh'] = {'path': 'worker.sh', 'bytes': launcher.stat().st_size, 'sha256': sha256(launcher)}
    # DT_NEEDED is supplemented by the actual portable execution gate.
    elf = out/'Engine/Binaries/Linux/RiveUmgBlueprintWorker'
    ldd = subprocess.run(['ldd', str(elf)], text=True, capture_output=True,
        env=dict(os.environ, LD_LIBRARY_PATH=':'.join(str(out/d) for d in library_dirs)))
    report = {'status': 'staged' if not missing and 'not found' not in ldd.stdout else 'incomplete',
        'target': receipt['TargetName'], 'scope': 'source WidgetBlueprint Editor worker; not default Rive or UMG runtime host',
        'worker_source_sha256': sha256(a.worker.resolve()), 'receipt_sha256': sha256(a.receipt.resolve()),
        'missing': missing, 'excluded_optional_runtime_dependencies': excluded, 'stripped_staged_elf': True,
        'library_dirs': library_dirs, 'payload_bytes_excluding_manifest': sum(f['bytes'] for f in files.values()),
        'files': list(files.values()), 'ldd': ldd.stdout + ldd.stderr,
        'host_prerequisites': ['Linux x86_64 libc/standard OS dependencies shown by ldd', 'Mesa llvmpipe Vulkan ICD',
                               'Python 3.10+ for the optional CLI; Bash for worker.sh'],
        'engine_source_required': False, 'shader_sources_for_native_editor_hashing_included': True,
        'portable_execution_validated': False}
    (out/'package-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    # Deterministic header/path/order so compressed deltas are interpretable.
    archive = out.with_suffix('.tar.gz')
    with archive.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for src in sorted(out.rglob('*')):
                if not src.is_file(): continue
                info = tar.gettarinfo(str(src), 'widget-worker/'+src.relative_to(out).as_posix())
                info.uid = info.gid = info.mtime = 0; info.uname = info.gname = ''
                with src.open('rb') as data: tar.addfile(info, data)
    summary = {'status': report['status'], 'package': str(out), 'file_count': len(files),
        'payload_bytes': report['payload_bytes_excluding_manifest'],
        'logical_bytes': sum(x.stat().st_size for x in out.rglob('*') if x.is_file()),
        'tar_gz_bytes': archive.stat().st_size, 'tar_gz_sha256': sha256(archive),
        'worker_bytes': elf.stat().st_size, 'worker_sha256': sha256(elf), 'missing_count': len(missing)}
    (out.parent/(out.name+'.metrics.json')).write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    return int(report['status'] != 'staged')


if __name__ == '__main__': raise SystemExit(main())
