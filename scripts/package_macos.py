#!/usr/bin/env python3
"""Stage an audited Mac Rive-only receipt; never package SDKs or cooker tools."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'Linux', 'Win64', 'Engine', 'Renderer', 'UMG', 'Slate', 'SlateCore',
             'SlateDebug', 'VerseCompiler', 'Solaris', 'RiveVerseWorker', 'RiveUeShaderCooker'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_shader(path):
    manifest = json.loads(Path(str(path)+'.manifest.json').read_text())
    if (manifest.get('complete') is not True or manifest.get('kind') != 'ue_engine_canonical'
            or manifest.get('target_platform') != 'Mac' or manifest.get('shader_platform') != 'METAL_SM5'
            or manifest.get('target_has_editor_only_data') is not False
            or manifest.get('type_filter') != '' or manifest.get('loads_lite_archive') is not False
            or manifest.get('failed_jobs') != 0 or manifest.get('submitted_jobs', 0) <= 0
            or manifest.get('succeeded_jobs') != manifest.get('submitted_jobs')
            or manifest.get('archive_bytes') != path.stat().st_size):
        raise RuntimeError('Require a complete non-editor Mac METAL_SM5 native cooker archive')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=['arm64', 'x64'], default='arm64')
    parser.add_argument('--receipt', type=Path, default=ROOT/'Binaries/Mac/RiveRhiLite.target')
    parser.add_argument('--shader-archive', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, default=ROOT/'fixtures/bankcard.riv')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('Package on Mac so architecture and dynamic dependencies can be inspected')
    boundary = json.loads((ROOT/f'artifacts/macos/boundary-{args.arch}.json').read_text())
    if boundary.get('status') != 'passed' or boundary['receipt_sha256'] != sha(args.receipt):
        raise RuntimeError('Run audit_macos_boundary.py for the actual receipt first')
    receipt = json.loads(args.receipt.read_text())
    if receipt.get('TargetName') != 'RiveRhiLite' or receipt.get('Platform') != 'Mac':
        raise RuntimeError('Only the Mac Rive-only receipt may be packaged')
    validate_shader(args.shader_archive)
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('Use a fresh package directory; existing packages are never deleted')
    engine = (ROOT/'engine/Engine').resolve()
    pending = []
    executable_source = None
    for item in receipt.get('BuildProducts', []) + receipt.get('RuntimeDependencies', []):
        if item.get('Type') in ['SymbolFile', 'MapFile', 'DebugNonUFS']:
            continue
        src = Path(item['Path'].replace('$(EngineDir)', str(engine)).replace('$(ProjectDir)', str(ROOT))).resolve()
        if not src.is_file():
            raise RuntimeError('Unresolved receipt dependency: '+str(src))
        if src.is_relative_to(engine):
            relative = src.relative_to(engine)
            dest = Path('Engine')/relative
        else:
            relative = src.relative_to(ROOT)
            dest = relative
        if FORBIDDEN.intersection(relative.parts) or src.suffix in ['.so', '.exe', '.dll', '.a', '.lib']:
            raise RuntimeError('Heavy or foreign-platform payload: '+str(src))
        if item.get('Type') == 'Executable':
            if executable_source is not None:
                raise RuntimeError('Unexpected second executable in Lite receipt')
            executable_source = src
            if sha(src) != boundary['executable_sha256']:
                raise RuntimeError('Binary changed after boundary audit')
            dest = Path('Engine/Binaries/Mac/RiveRhiLite')
        pending.append((src, dest))
    if executable_source is None:
        raise RuntimeError('Missing runtime executable')
    for config_dir in ['', 'Apple', 'Mac']:
        for src in (engine/'Config'/config_dir).glob('*.ini'):
            pending.append((src, Path('Engine/Config')/config_dir/src.name))
    for src in (ROOT/'Config').rglob('*.ini'):
        pending.append((src, src.relative_to(ROOT)))
    pending += [(args.shader_archive, Path('shaders/global.bin')),
                (Path(str(args.shader_archive)+'.manifest.json'), Path('shaders/global.bin.manifest.json')),
                (args.fixture, Path('fixtures/input.riv')),
                (ROOT/'prototype/runtime/render_macos.sh', Path('render.sh'))]
    output.mkdir(parents=True)
    for src, dest in pending:
        target = output/dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    (output/'Engine/Shaders').mkdir(parents=True, exist_ok=True)
    binary = output/'Engine/Binaries/Mac/RiveRhiLite'
    binary.chmod(0o755)
    (output/'render.sh').chmod(0o755)
    # Record load commands. A development path must never be a release dependency.
    load_commands = subprocess.check_output(['xcrun', 'otool', '-L', str(binary)], text=True)
    external = []
    for line in load_commands.splitlines()[1:]:
        library = line.strip().split(' (', 1)[0]
        if library.startswith('/') and not library.startswith(('/usr/lib/', '/System/Library/')):
            external.append(library)
    files = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(output.rglob('*')) if p.is_file()]
    report = {'status': 'incomplete' if external else 'staged_runtime_unverified',
              'target': 'RiveRhiLite', 'platform': 'Mac', 'architecture': args.arch,
              'capabilities': {'rive': True, 'umg': False, 'verse': False},
              'boundary_report_sha256': sha(ROOT/f'artifacts/macos/boundary-{args.arch}.json'),
              'receipt_sha256': sha(args.receipt), 'files': files, 'otool': load_commands,
              'external_development_libraries': external,
              'payload_bytes_excluding_manifest': sum(f['bytes'] for f in files),
              'metal_screenshot_validated': False, 'signed_and_notarized': False}
    (output/'package-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['files', 'otool']}, indent=2))
    return 1 if external else 0


if __name__ == '__main__':
    raise SystemExit(main())
