#!/usr/bin/env python3
"""Build one deduplicated command-line distribution from audited component packages."""
from pathlib import Path
import argparse
import gzip
import json
import os
import shutil
import subprocess
import tarfile

from prepare_release import ROOT, sanitize, sha

SCRIPTS = ['rive_tool.py', 'compare_png.py', 'measure_ue_lite.py']
TARGETS = {'rive': 'RiveRhiLite', 'umg': 'RiveUmgHost', 'verse': 'RiveRhiLite+RiveVerseWorker', 'widget': 'RiveUmgBlueprintWorker'}


def files(root):
    return [{'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'toolkit-manifest.json'
            and not set(path.relative_to(root).parts) & {'Saved', '__pycache__', '.rive-tool', 'workspaces', 'runs'}]


def verify(root, manifest):
    for item in manifest['files']:
        path = root/item['path']
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise RuntimeError(f'Package file changed: {path}')


def replace_file(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Break this path's hardlink before updating a CLI or metadata file.
    if dest.exists():
        dest.unlink()
    shutil.copyfile(source, dest)
    with dest.open('rb') as stream:
        executable = stream.read(4) == b'\x7fELF'
    dest.chmod(0o755 if executable or dest.suffix == '.sh' or dest.name == 'rive-tool' else 0o644)


def refresh_cli(out):
    for name in SCRIPTS:
        replace_file(ROOT/'scripts'/name, out/'scripts'/name)
    for name in ['rive-tool', 'rive-tool.ps1']:
        replace_file(ROOT/'prototype/runtime'/name, out/name)
    replace_file(ROOT/'scripts/widget_bp.py', out/'components/widget/scripts/widget_bp.py')
    for name in TARGETS:
        folder = out/'components'/name
        manifest_path = folder/'package-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        manifest['files'] = [item for item in files(folder) if item['path'] != 'package-manifest.json']
        for key in ['payload_bytes_excluding_manifest', 'raw_bytes']:
            if key in manifest:
                manifest[key] = sum(item['bytes'] for item in manifest['files'])
        manifest_path.unlink()
        manifest_path.write_text(json.dumps(sanitize(manifest), indent=2)+'\n', encoding='utf-8')
    readme = ROOT/'prototype/cli-toolkit.md'
    if readme.is_file():
        replace_file(readme, out/'README.md')


def write_manifest(out, provenance):
    entries = files(out)
    unique = {item['sha256']: item['bytes'] for item in entries}
    inodes = {}
    for item in entries:
        path = out/item['path']
        stat = path.stat()
        inodes[(stat.st_dev, stat.st_ino)] = stat.st_size
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip())
    manifest = {'format': 1, 'platform': 'linux-x86_64', 'entrypoint': './rive-tool', 'components': list(TARGETS),
        'source_commit': revision, 'source_dirty_at_packaging': dirty, 'component_provenance': provenance,
        'files': entries, 'logical_file_bytes_excluding_manifest': sum(item['bytes'] for item in entries),
        'unique_content_bytes_excluding_manifest': sum(unique.values()), 'staged_unique_inode_bytes_excluding_manifest': sum(inodes.values()),
        'duplicate_content_bytes': sum(item['bytes'] for item in entries)-sum(unique.values()),
        'host_prerequisites': ['Linux x86_64 standard system libraries', 'Python 3.11+', 'Bash', 'GNU time', 'Mesa llvmpipe Vulkan ICD'],
        'execution': 'One distribution and one CLI; separate monolithic native workers, started per operation',
        'native_macos_available': False, 'native_windows_all_tools_available': False, 'windows_frontend': 'WSL Ubuntu wrapper',
        'uefn_validated': False, 'runtime_validation': 'Recorded separately; staging is not runtime acceptance'}
    (out/'toolkit-manifest.json').write_text(json.dumps(sanitize(manifest), indent=2)+'\n', encoding='utf-8')
    return manifest


def make_archive(out, manifest):
    archive = out.parent/(out.name+'.tar.gz')
    if archive.exists():
        raise RuntimeError('Archive exists; choose a fresh package name or preserve the old archive first')
    seen, hardlinks = {}, 0
    entries = {item['path']: item for item in manifest['files']}
    paths = {out/item['path'] for item in manifest['files']} | {out/'toolkit-manifest.json'}
    for path in list(paths):
        paths.update(parent for parent in path.parents if parent.is_relative_to(out))
    for name in TARGETS:
        paths.add(out/'components'/name/'Engine/Shaders')
    with archive.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT, dereference=True) as tar:
            for path in sorted(paths):
                relative = path.relative_to(out).as_posix()
                name = str(Path(out.name)/path.relative_to(out))
                info = tar.gettarinfo(str(path), name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                info.mode = 0o755 if path.is_dir() else 0o644
                if not path.is_file():
                    tar.addfile(info)
                    continue
                with path.open('rb') as stream:
                    executable = stream.read(4) == b'\x7fELF'
                    info.mode = 0o755 if executable or path.suffix == '.sh' or path.name == 'rive-tool' else 0o644
                    digest = entries[relative]['sha256'] if relative in entries else sha(path)
                    key = (digest, info.mode)
                    if key in seen:
                        info.type, info.linkname, info.size = tarfile.LNKTYPE, seen[key], 0
                        tar.addfile(info)
                        hardlinks += 1
                    else:
                        seen[key] = name
                        stream.seek(0)
                        tar.addfile(info, stream)
    return {'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive), 'hardlink_entries': hardlinks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--refresh-cli', action='store_true', help='Verify existing immutable payloads, then refresh CLI/docs/metadata')
    parser.add_argument('--archive-existing', action='store_true', help='Verify and archive an existing staged toolkit')
    defaults = {'rive': 'release3-linux-rive', 'umg': 'release3-linux-umg', 'verse': 'release3-linux-verse', 'widget': 'widget-animation-01'}
    for name in TARGETS:
        parser.add_argument('--'+name+'-package', type=Path, default=ROOT/'package'/defaults[name])
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'package') or out == ROOT/'package':
        parser.error('Keep the combined package in this independent prototype/package')
    if args.refresh_cli or args.archive_existing:
        manifest = json.loads((out/'toolkit-manifest.json').read_text())
        verify(out, manifest)
        if args.refresh_cli:
            refresh_cli(out)
            manifest = write_manifest(out, manifest['component_provenance'])
    else:
        if out.exists():
            parser.error('Use a fresh package directory')
        out.mkdir(parents=True)
        seen, provenance = {}, {}
        for name, target in TARGETS.items():
            source = getattr(args, name+'_package').resolve()
            data = json.loads((source/'package-manifest.json').read_text(encoding='utf-8-sig'))
            if data.get('target') != target:
                raise RuntimeError(f'Wrong {name} package target')
            verify(source, data)
            dest = out/'components'/name
            for item in data['files']:
                relative = Path(item['path'])
                if relative.is_absolute() or '..' in relative.parts or not (source/relative).resolve().is_relative_to(source):
                    raise RuntimeError('Manifest path escapes its component')
                path = dest/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                key = item['sha256']
                if key in seen:
                    try:
                        os.link(seen[key], path)
                    except OSError:
                        replace_file(source/relative, path)
                else:
                    replace_file(source/relative, path)
                    seen[key] = path
            (dest/'Engine/Shaders').mkdir(parents=True, exist_ok=True)
            (dest/'package-manifest.json').write_text(json.dumps(sanitize(data), indent=2)+'\n', encoding='utf-8')
            provenance[name] = {'target': target, 'source_package_manifest_sha256': sha(source/'package-manifest.json'),
                                'source_package': sanitize(str(source))}
            print(json.dumps({'component': name, 'status': 'staged'}), flush=True)
        for source, folder in [(ROOT/'fixtures/widget-blueprint', 'widget'), (ROOT/'fixtures/verse', 'verse')]:
            for path in source.iterdir():
                if path.is_file():
                    replace_file(path, out/'examples'/folder/path.name)
        for name, fixture in [('bankcard.riv', 'bankcard.riv'), ('rocket.riv', 'rocket.riv')]:
            replace_file(ROOT/'fixtures'/fixture, out/'examples'/name)
        refresh_cli(out)
        manifest = write_manifest(out, provenance)
    result = {'status': 'staged', 'file_count': len(manifest['files']),
        'logical_file_bytes': manifest['logical_file_bytes_excluding_manifest'],
        'unique_content_bytes': manifest['unique_content_bytes_excluding_manifest'], 'duplicate_content_bytes': manifest['duplicate_content_bytes']}
    if not args.stage_only:
        result['archive'] = make_archive(out, manifest)
    (out.parent/(out.name+'.metrics.json')).write_text(json.dumps(sanitize(result), indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
