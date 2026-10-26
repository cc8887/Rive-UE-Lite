#!/usr/bin/env python3
"""Archive manifest-declared packages; runtime qualification is a separate gate."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize(value):
    if isinstance(value, str):
        value = value.replace(str(ROOT), '${PROTOTYPE_ROOT}').replace(ROOT.as_posix(), '${PROTOTYPE_ROOT}')
        value = value.replace('/mnt/f/Github/Rive-UE-Lite', '${PROTOTYPE_ROOT}')
        value = re.sub(r'/home/[^/\s]+/\.cache/rive-ue-lite-20261024', '${BUILD_CACHE}', value)
        value = re.sub(r'/mnt/[a-z]/Users/[^/\s]+', '${USER_HOME}', value)
        return re.sub(r'[A-Za-z]:[\\/]Users[\\/][^\\/\s]+', '${USER_HOME}', value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def inventory(stage):
    return [{'path': path.relative_to(stage).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(stage.rglob('*')) if path.is_file()]


def stage_package(source, stage):
    manifest = json.loads((source / 'package-manifest.json').read_text(encoding='utf-8-sig'))
    stage.mkdir(parents=True)
    seen = set()
    for item in manifest['files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() in seen:
            raise RuntimeError(f'Invalid or duplicate package path: {relative}')
        seen.add(relative.as_posix())
        src = (source / relative).resolve()
        if not src.is_relative_to(source) or not src.is_file():
            raise RuntimeError(f'Missing/escaping package file: {relative}')
        if src.stat().st_size != item['bytes'] or sha(src) != item['sha256']:
            raise RuntimeError(f'Package changed: {relative}')
        dest = stage / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        with dest.open('rb') as stream:
            executable = stream.read(4) == b'\x7fELF'
        dest.chmod(0o755 if executable or dest.suffix == '.sh' else 0o644)
        # Remove local build paths from informational JSON, then rebind its hash.
        if dest.suffix in ['.json', '.target']:
            try:
                value = json.loads(dest.read_text(encoding='utf-8-sig'))
            except (ValueError, UnicodeError):
                continue
            cleaned = sanitize(value)
            if cleaned != value:
                dest.write_text(json.dumps(cleaned, indent=2) + '\n', encoding='utf-8')
    (stage / 'Engine/Shaders').mkdir(parents=True, exist_ok=True)
    manifest = sanitize(manifest)
    manifest['files'] = inventory(stage)
    for key in ['raw_bytes', 'payload_bytes_excluding_manifest']:
        if key in manifest:
            manifest[key] = sum(item['bytes'] for item in manifest['files'])
    (stage / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


def archive(stage, destination, windows):
    paths = [stage, *sorted(stage.rglob('*'))]
    if windows:
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in paths:
                relative = Path(stage.name) / path.relative_to(stage)
                info = zipfile.ZipInfo(relative.as_posix() + ('/' if path.is_dir() else ''), (2026, 1, 1, 0, 0, 0))
                info.external_attr = (0o40755 if path.is_dir() else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                stream.writestr(info, b'' if path.is_dir() else path.read_bytes())
    else:
        with destination.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as stream:
                for path in paths:
                    info = stream.gettarinfo(str(path), str(Path(stage.name) / path.relative_to(stage)))
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ''
                    info.mode = 0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644
                    if path.is_file():
                        with path.open('rb') as payload:
                            stream.addfile(info, payload)
                    else:
                        stream.addfile(info)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--package', nargs=3, action='append', metavar=('PLATFORM', 'FLAVOR', 'DIRECTORY'), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v[\w.-]+', args.tag):
        parser.error('Invalid release tag')
    output = ROOT / 'artifacts/release' / args.tag
    if output.exists():
        parser.error('Use a fresh release directory/tag')
    output.mkdir(parents=True)
    assets = output / 'assets'
    assets.mkdir()
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    result = {'tag': args.tag, 'source_commit': revision, 'status': 'pending_archive_runtime_validation', 'assets': []}
    for platform, flavor, folder in args.package:
        if platform not in ['linux-x86_64', 'windows-x86_64', 'macos-arm64', 'macos-x86_64'] or not re.fullmatch(r'[a-z0-9-]+', flavor):
            parser.error('Unsupported platform/flavor')
        source = Path(folder).resolve()
        if not source.is_relative_to(ROOT):
            parser.error('Package must stay inside this independent prototype')
        name = f'Rive-UE-Lite-{args.tag}-{platform}-{flavor}'
        stage = ROOT / 'package/release-staged' / args.tag / name
        if stage.exists():
            parser.error(f'Staging directory exists: {stage}')
        stage_package(source, stage)
        if platform.startswith('windows'):
            command = '.\\render.ps1 -Output C:\\absolute\\output.png'
            prerequisites = 'Windows x64 and a Vulkan graphics driver. The launcher disables extra async-compute queues.'
        elif platform.startswith('macos'):
            command = 'bash render.sh fixtures/bankcard.riv /absolute/output.png'
            prerequisites = 'macOS 15 or newer, a compatible architecture and a Metal-capable device; see native dependency validation.'
        elif flavor == 'widget-authoring':
            command = 'python3 scripts/widget_bp.py --help'
            prerequisites = 'Linux x86_64, Bash, Python 3, standard system libraries and Mesa llvmpipe Vulkan ICD.'
        else:
            command = 'bash verse-ui.sh --output-dir /absolute/new-output' if flavor == 'verse' else 'bash render.sh fixtures/input.riv /absolute/output.png'
            prerequisites = 'Linux x86_64, Bash, standard system libraries and Mesa llvmpipe Vulkan ICD; Verse also needs Python 3 and GNU time.'
        (stage / 'RELEASE-README.md').write_text(
            f'# Rive UE Lite {args.tag}: {platform} / {flavor}\n\nSource commit: {revision}.\n\n'
            f'From the extracted directory:\n\n```\n{command}\n```\n\n{prerequisites}\n\n'
            'This is an offscreen prototype. UEFN integration and a complete Unreal Editor are not qualified.\n'
            'The default Rive package excludes UMG and the optional Verse/Widget authoring workers.\n'
            'See the release validation JSON for actual tested scope and platform limitations.\n', encoding='utf-8')
        files = inventory(stage)
        (stage / 'release-manifest.json').write_text(json.dumps({'source_commit': revision, 'tag': args.tag,
            'platform': platform, 'flavor': flavor, 'files': files}, indent=2) + '\n', encoding='utf-8')
        destination = assets / (name + ('.zip' if platform.startswith('windows') else '.tar.gz'))
        archive(stage, destination, platform.startswith('windows'))
        item = {'platform': platform, 'flavor': flavor, 'source_commit': revision, 'file': destination.name, 'bytes': destination.stat().st_size,
                'sha256': sha(destination), 'payload_bytes': sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())}
        result['assets'].append(item)
        print(json.dumps(item), flush=True)
    (output / 'release-status.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (assets / 'SHA256SUMS').write_text(''.join(f'{item["sha256"]}  {item["file"]}\n' for item in result['assets']), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'assets': len(result['assets']), 'source_commit': revision}))


if __name__ == '__main__':
    main()
