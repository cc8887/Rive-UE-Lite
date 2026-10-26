#!/usr/bin/env python3
"""Create/read/edit real source Widget Blueprints through the native UE worker.

Windows calls forward to the isolated Ubuntu worker in WSL. Output and edits
stay in the explicit workspace (this prototype by default). Import copies assets.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT
DEFAULT_SHADER_ARCHIVE = (ROOT/'shaders/global.bin' if (ROOT/'shaders/global.bin').is_file()
                          else ROOT/'artifacts/umg-blueprint/shaders-host/global.bin')
ENGINE_COMMIT = '62d7c1a7125b52b10ee1b714838f515f3563f795'
CAPABILITIES = {
    'backend': 'native UWidgetBlueprint / WidgetTree / Kismet compiler / SavePackage',
    'commands': ['create', 'read', 'import', 'patch', 'preview', 'export', 'animation list', 'animation create', 'animation patch'],
    'animation_properties': ['opacity', 'render_translation', 'render_scale', 'render_angle'],
    'animation_interpolation': ['constant', 'linear'],
    'native_animation_playback': True,
    'animation_unknown_tracks': 'read-only, preserved; preview refuses unsupported tracks',
    'create_widget_types': ['CanvasPanel', 'Border', 'Button', 'TextBlock'],
    'patch_properties': ['text', 'font_size', 'color', 'padding', 'position', 'size', 'alignment',
                         'enabled', 'is_variable', 'visibility', 'opacity'],
    'read_existing_source_blueprint': True,
    'reads_graph_nodes_and_pins': True,
    'edits_graph_nodes_or_links': False,
    'structural_tree_edits_on_existing_asset': False,
    'uefn_validated': False,
    'qualified_platform': 'Linux CPU Vulkan; Windows frontend uses WSL Ubuntu',
    'worker_in_default_rive_build': False,
}

def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def inside(path):
    path = Path(path).expanduser().resolve()
    if not path.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f'Write paths must stay in the selected workspace: {path}. Use import for an external source asset.')
    if any(path.is_relative_to(ROOT/name) for name in ['engine', 'vendor', 'Engine']):
        raise ValueError('Use an isolated job Content directory, not engine/vendor')
    return path

def wsl_path(value):
    path = str(Path(value).expanduser().resolve()).replace('\\', '/')
    if not re.match(r'^[A-Za-z]:/', path):
        raise ValueError(f'WSL forwarding requires a local drive path: {path}')
    return '/mnt/'+path[0].lower()+path[2:]

def forward_windows(args):
    forwarded = list(sys.argv[1:])
    path_options = {'--workspace-root', '--content-dir', '--report-dir', '--input', '--spec', '--patch', '--output', '--shader-archive', '--playback-script'}
    for index, item in enumerate(forwarded):
        if item in path_options and index+1 < len(forwarded):
            forwarded[index+1] = wsl_path(forwarded[index+1])
        elif '=' in item and item.split('=', 1)[0] in path_options:
            key, value = item.split('=', 1); forwarded[index] = key+'='+wsl_path(value)
    return subprocess.call(['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--cd', wsl_path(ROOT), '--',
        'bash', wsl_path(ROOT/'scripts/measure_no_gpu.sh'), '--', 'python3', '-B',
        wsl_path(Path(__file__)), *forwarded])

def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace-root', type=Path, default=ROOT, help='Explicit isolated write root; defaults to this prototype/package')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('capabilities', help='List supported operations and limitations without starting UE')
    commands = [(name, sub.add_parser(name)) for name in ['create', 'read', 'inspect', 'import', 'patch', 'preview', 'export']]
    animation = sub.add_parser('animation', help='Read/create/edit native UWidgetAnimation objects embedded in the source Blueprint')
    actions = animation.add_subparsers(dest='animation_command', required=True)
    commands += [('animation-'+name, actions.add_parser(name)) for name in ['list', 'create', 'patch']]
    for name, cmd in commands:
        cmd.add_argument('--content-dir', type=Path, required=True, help='Isolated Content mount; write paths stay under this prototype')
        cmd.add_argument('--asset', required=True, help='Original long package name, e.g. /Game/UI/WBP_Card')
        cmd.add_argument('--report-dir', type=Path, help='Fresh job/evidence directory; generated automatically when omitted')
        if name in ['create', 'animation-create']: cmd.add_argument('--spec', type=Path, required=True)
        if name == 'import': cmd.add_argument('--input', type=Path, required=True, help='Existing source .uasset copied before native loading')
        if name in ['patch', 'animation-patch', 'animation-create']:
            if name != 'animation-create': cmd.add_argument('--patch', type=Path, required=True)
            cmd.add_argument('--expected-sha256', help='Reject a stale edit before starting the native worker')
        if name in ['preview', 'export']: cmd.add_argument('--output', type=Path, required=True)
        if name == 'preview':
            cmd.add_argument('--shader-archive', type=Path, default=DEFAULT_SHADER_ARCHIVE)
            cmd.add_argument('--width', type=int, default=640)
            cmd.add_argument('--height', type=int, default=400)
            cmd.add_argument('--animation', help='Native source animation name, without the compiled _INST suffix')
            cmd.add_argument('--time', type=float, default=0, help='Seconds sampled by native PlayAnimation; default 0')
            cmd.add_argument('--playback-script', type=Path, help='Native play/tick/seek/pause/resume/reverse/stop operations')
    args = p.parse_args()
    if args.command == 'animation': args.command = 'animation-'+args.animation_command
    return args

def main():
    global WORKSPACE_ROOT
    args = parse_args()
    WORKSPACE_ROOT = args.workspace_root.expanduser().resolve()
    if args.command == 'capabilities':
        print(json.dumps(CAPABILITIES, indent=2)); return 0
    if platform.system() == 'Windows': return forward_windows(args)
    if platform.system() != 'Linux': raise ValueError('The authoring worker is currently qualified on Linux/WSL only')
    # Preserve the source experiment's namespace/drop-privilege workflow. The
    # deployed Program workers also run without mount privileges, including in
    # root containers; they force and verify CPU Vulkan independently below.
    if os.geteuid() == 0 and (ROOT/'AGENTS.md').is_file() and os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1':
        return subprocess.call(['bash', str(ROOT/'scripts/measure_no_gpu.sh'), '--',
            'python3', '-B', str(Path(__file__).resolve()), *sys.argv[1:]])
    # Ordinary server users may preview without namespace privileges. The ICD
    # is forced below and the selected CPU adapter is checked after capture.
    # Formal no-GPU acceptance still runs in the GPU-hiding namespace wrapper.
    if not re.fullmatch(r'/Game/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*', args.asset):
        raise ValueError('Use an ASCII /Game/... package name without extension/object suffix')
    content = inside(args.content_dir)
    asset = content/(args.asset.removeprefix('/Game/')+'.uasset')
    if not asset.is_relative_to(content): raise ValueError('Asset escaped the Content mount')
    report_dir = inside(args.report_dir) if args.report_dir else WORKSPACE_ROOT/'artifacts/widget-blueprint-jobs'/(
        datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    if report_dir.exists(): raise ValueError('Use a fresh report directory')
    report_dir.mkdir(parents=True)
    report = {'status': 'incomplete', 'command': args.command, 'asset': args.asset, 'file': str(asset),
        'engine_commit': ENGINE_COMMIT, 'report_dir': str(report_dir), 'capabilities': CAPABILITIES}
    metadata_file = report_dir/'asset.json'
    backup = None
    try:
        worker = ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'
        if not worker.is_file(): worker = ROOT/'Engine/Binaries/Linux/RiveUmgBlueprintWorker'
        if not worker.is_file(): raise ValueError('Build first: sudo bash scripts/build_ui.sh --with-widget-blueprint')
        if args.command in ['create', 'import']:
            if asset.exists(): raise ValueError('Creation/import refuses an existing asset; use patch for edits')
            content.mkdir(parents=True, exist_ok=True)
        elif not asset.is_file(): raise ValueError(f'Source asset does not exist: {asset}; use import to copy an existing .uasset')
        if args.command == 'import':
            source = args.input.expanduser().resolve()
            if source.suffix.lower() != '.uasset' or source.stem != asset.stem:
                raise ValueError('Import keeps the original object name; --asset leaf must match the .uasset filename')
            asset.parent.mkdir(parents=True, exist_ok=True)
            report['import_source'] = {'path': str(source), 'sha256': sha256(source)}
            shutil.copy2(source, asset)
            for suffix in ['.uexp', '.ubulk']:
                if source.with_suffix(suffix).is_file(): shutil.copy2(source.with_suffix(suffix), asset.with_suffix(suffix))
        before = sha256(asset) if asset.exists() else None
        report['sha256_before'] = before
        if args.command in ['patch', 'animation-create', 'animation-patch']:
            if args.expected_sha256 and args.expected_sha256.lower() != before:
                raise ValueError('Asset changed since read; stale patch rejected')
            backup = report_dir/'backup'/asset.name
            backup.parent.mkdir(); shutil.copy2(asset, backup)
            report['backup'] = str(backup)
            for suffix in ['.uexp', '.ubulk']:
                if asset.with_suffix(suffix).is_file():
                    raise ValueError('Patch qualification covers a single source .uasset; sidecar packages require separate validation')
        if args.command in ['preview', 'export']:
            output = inside(args.output)
            if output.exists(): raise ValueError('Output exists; choose a new output file')
            output.parent.mkdir(parents=True, exist_ok=True)
        mode = {'create': 'create', 'patch': 'patch', 'preview': 'render',
                'animation-create': 'animation-create', 'animation-patch': 'animation-patch'}.get(args.command, 'inspect')
        command = [str(worker), '-unattended', '-stdout', '-NoSplash', '-NoCrashDialog',
            f'-ProjectDir={ROOT}/', f'-ContentDir={content}', f'-Asset={args.asset}', f'-Mode={mode}',
            f'-Metadata={metadata_file}', f'-UserDir={report_dir}/user/', f'-abslog={report_dir}/ue.log']
        if args.command in ['create', 'animation-create']: command += [f'-Spec={args.spec.resolve()}']
        if args.command in ['patch', 'animation-patch']: command += [f'-Patch={args.patch.resolve()}']
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LC_ALL='C', LANG='C')
        package_manifest = ROOT/'package-manifest.json'
        if package_manifest.is_file():
            package = json.loads(package_manifest.read_text())
            library_dirs = [str(ROOT/rel) for rel in package.get('library_dirs', [])]
            env['LD_LIBRARY_PATH'] = ':'.join(library_dirs + ([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
        if args.command == 'preview':
            if args.playback_script and not args.animation: raise ValueError('--playback-script requires --animation')
            archive = args.shader_archive.resolve()
            if not archive.is_file(): raise ValueError('Native LinuxEditor Slate archive missing; see Source/RiveUmgBlueprintWorker/README.md')
            icd = Path(env['RIVE_LITE_ICD']) if env.get('RIVE_LITE_ICD') else next(iter(sorted(Path('/usr/share/vulkan/icd.d').glob('*lvp*.json'))), None)
            if not icd or not icd.is_file(): raise ValueError('Mesa CPU Vulkan ICD missing; install Mesa or set RIVE_LITE_ICD')
            env.update(VK_ICD_FILENAMES=str(icd), VK_DRIVER_FILES=str(icd))
            command += ['-vulkan', '-sm5', '-AllowCPUDevices', '-AllowCommandletRendering', '-RenderOffscreen',
                '-norhithread', f'-ShaderArchive={archive}', f'-Output={output}', f'-Width={args.width}', f'-Height={args.height}']
            if args.animation:
                command += [f'-Animation={args.animation}', f'-AnimationTime={args.time}']
                if args.playback_script: command += [f'-PlaybackScript={args.playback_script.resolve()}']
        report['native_command'] = command
        report['worker_sha256'] = sha256(worker)
        started = time.monotonic()
        with (report_dir/'worker.log').open('wb') as log:
            process = subprocess.Popen(['/usr/bin/time', '-v', '-o', str(report_dir/'time.txt'), '--', *command],
                cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.wait(timeout=120 if mode != 'render' else 240)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError('Native operation timed out; worker process group terminated')
        report['wall_seconds'] = time.monotonic()-started
        report['exit_code'] = process.returncode
        log = (report_dir/'worker.log').read_text(errors='replace')
        if process.returncode or 'UMG_BP_COMPLETE' not in log or re.search(r'Ensure condition failed:|Fatal error:|Log\w+: Error:', log):
            raise RuntimeError(f'Native {mode} failed; inspect {report_dir}/worker.log')
        metadata = json.loads(metadata_file.read_text(encoding='utf-8-sig'))
        if not metadata.get('source_blueprint') or metadata.get('cooked'):
            raise RuntimeError('Expected a real uncooked WidgetBlueprint source asset')
        report['metadata'] = metadata
        after = sha256(asset)
        report['sha256_after'] = after
        if args.command in ['read', 'inspect', 'import', 'preview', 'export', 'animation-list'] and before != after:
            raise RuntimeError('Readonly operation changed the source asset')
        if args.command == 'preview':
            if metadata['using_null_rhi'] or not re.search(r'llvmpipe|lavapipe', metadata['adapter'], re.I):
                raise RuntimeError('Preview did not use real CPU Vulkan')
            report['output'] = {'path': str(output), 'sha256': sha256(output)}
        if args.command == 'export':
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(asset, 'Content/'+asset.relative_to(content).as_posix())
                archive.writestr('engine-pin.txt', ENGINE_COMMIT+'\n')
            report['output'] = {'path': str(output), 'sha256': sha256(output)}
        if args.command == 'import':
            report['import_source']['unchanged'] = sha256(Path(report['import_source']['path'])) == report['import_source']['sha256']
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = str(error)
        if backup and backup.is_file() and (not asset.is_file() or sha256(asset) != sha256(backup)):
            temp = asset.with_suffix('.restore.tmp'); shutil.copy2(backup, temp); temp.replace(asset)
            report['restored_backup'] = True
    (report_dir/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        raise SystemExit(2)
