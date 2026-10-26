#!/usr/bin/env python3
"""One JSON CLI for the combined Linux Rive/UMG/Verse/Widget toolkit."""
from pathlib import Path
import argparse
import contextlib
from collections import deque
import datetime
import hashlib
import hmac
import json
import math
import os
import platform
import re
import secrets
import shlex
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import uuid

from compare_png import read_png, sha256
from measure_ue_lite import run_once

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 1
ERROR_LOG = re.compile(r'Ensure condition failed:|Fatal error:|Assertion failed:|Log\w+: Error:')
VERSE_TESTS = {'event_resume', 'event_no_sticky_replay', 'suspended', 'race_cancel_defer_no_late_resume', 'failure_rollback', 'all'}
CATALOG = {
    'init': 'Create a workspace and copy editable examples without overwriting existing files.',
    'start': 'Start the local coordinator; UE workers start only when an operation needs them.',
    'status': 'Show coordinator identity, active job and completed job count.',
    'stop': 'Stop an idle coordinator. A busy coordinator returns exit 75.',
    'capabilities': 'Describe available components, commands and validation boundaries as JSON.',
    'doctor': 'Check runtime files, CPU Vulkan ICD and required host programs; --verify hashes the bundle.',
    'render': 'Render a .riv through --ui rive|umg, with optional playback scenario JSON.',
    'widget': 'capabilities/create/read/import/patch/preview/export; animation list/create/patch. Default Content is workspace/Content.',
    'verse run': 'Compile and run a source file defining Main(Args:[]string, Env:[string]string)<suspends>:void.',
    'verse test': 'Run the supplied native VM event, suspension/cancellation and rollback tests.',
    'verse ui': 'Run the shared controller and bridge its Pressed command into Rive or the native UMG/Rive host.',
    'jobs': 'List persisted job results, or show one result by --id; --logs includes bounded native log tails.',
}


class ToolError(Exception):
    def __init__(self, code, message, exit_code=2):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError('invalid_arguments', message)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def save(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    if private:
        temp.chmod(0o600)
    temp.replace(path)


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def icd_path():
    supplied = os.environ.get('RIVE_LITE_ICD')
    return Path(supplied).resolve() if supplied else next(iter(sorted(Path('/usr/share/vulkan/icd.d').glob('*lvp*.json'))), None)


def workspace(path, toolkit):
    path = path.expanduser().resolve()
    protected = [toolkit/name for name in ['components', 'scripts', 'engine', 'vendor', 'dependencies', 'Engine', 'Binaries']]
    if path == toolkit or any(path.is_relative_to(folder) or folder.is_relative_to(path) for folder in protected):
        raise ToolError('protected_workspace', 'Choose a separate workspace, such as ./workspaces/demo')
    for name in ['Content', 'runs', '.rive-tool']:
        (path/name).mkdir(parents=True, exist_ok=True)
    return path


def path_in_workspace(value, ws):
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else ws/path).resolve()
    if not path.is_relative_to(ws) or path.is_relative_to(ws/'.rive-tool'):
        raise ToolError('outside_workspace', 'Output and edits must stay inside the selected workspace')
    return path


def input_path(value, ws):
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else ws/path).resolve()
    if not path.is_file():
        raise ToolError('missing_input', f'Input file does not exist: {path}')
    return path


def components(toolkit):
    return {name: toolkit/'components'/name for name in ['rive', 'umg', 'verse', 'widget']}


def capabilities(toolkit):
    paths = components(toolkit)
    executables = {'rive': 'Engine/Binaries/Linux/RiveRhiLite', 'umg': 'Engine/Binaries/Linux/RiveUmgHost',
                   'verse': 'worker/Binaries/Linux/RiveVerseWorker', 'widget': 'Engine/Binaries/Linux/RiveUmgBlueprintWorker'}
    return {'protocol': PROTOCOL, 'commands': CATALOG,
        'components': {name: {'available': (paths[name]/relative).is_file(), 'executable': str(paths[name]/relative)} for name, relative in executables.items()},
        'output': 'One JSON object on stdout; native diagnostics and full reports are saved per job.',
        'execution': 'Persistent local coordinator; serialized operations; separate native worker processes per operation.',
        'relative_paths': 'Paths inside commands are relative to --workspace; input files may also use absolute paths.',
        'widget': {'read_existing': True, 'write_properties': True, 'read_graphs': True, 'edit_graphs': False,
                   'animation_properties': ['opacity', 'render_translation', 'render_scale', 'render_angle'],
                   'animation_interpolation': ['constant', 'linear']},
        'examples': ['examples/widget/card.json', 'examples/widget/card.patch.json', 'examples/widget/intro.animation.json',
                     'examples/widget/intro.animation.patch.json', 'examples/verse/hello.verse', 'examples/verse/ui_controller.verse'],
        'verse_ui_bridge': 'Standalone sample controller -> Pressed bool -> Rive state machine, optionally embedded in UMG.',
        'qualified_platform': 'Linux x86_64 CPU Vulkan; Windows launcher uses WSL Ubuntu',
        'uefn_validated': False, 'native_macos_available': False}


def doctor(toolkit, verify=False):
    caps = capabilities(toolkit)
    icd = icd_path()
    checks = {'linux_host': sys.platform.startswith('linux'), 'python_3_11': sys.version_info >= (3, 11),
              'x86_64_host': platform.machine().lower() in ['x86_64', 'amd64'],
              'all_components': all(item['available'] for item in caps['components'].values()),
              'cpu_vulkan_icd': bool(icd and icd.is_file()), 'bash': bool(shutil.which('bash')),
              'gnu_time': Path('/usr/bin/time').is_file()}
    mismatches = []
    if verify:
        manifest = toolkit/'toolkit-manifest.json'
        if not manifest.is_file():
            mismatches.append('toolkit-manifest.json missing')
        else:
            for item in load(manifest)['files']:
                path = toolkit/item['path']
                if not path.is_file() or path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
                    mismatches.append(item['path'])
        checks['manifest_hashes'] = not mismatches
    return {'ready': all(checks.values()), 'checks': checks, 'icd': str(icd) if icd else None,
            'mismatches': mismatches, 'capabilities': caps}


def initialize(toolkit, ws):
    examples = toolkit/'examples'
    copied = []
    if examples.is_dir():
        for src in sorted(examples.rglob('*')):
            if not src.is_file():
                continue
            dst = ws/'examples'/src.relative_to(examples)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                copied.append(str(dst.relative_to(ws)))
    return {'workspace': str(ws), 'copied': copied, 'content_dir': str(ws/'Content')}


def child_env(job=None):
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS=os.environ.get('LP_NUM_THREADS', '2'))
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    if job:
        env['MESA_SHADER_CACHE_DIR'] = str(job/'mesa-cache')
    return env


def invoke(command, job, name, timeout=300):
    log, timing = job/(name+'.log'), job/(name+'.time.txt')
    started = time.perf_counter()
    with log.open('wb') as stream:
        proc = subprocess.Popen(['/usr/bin/time', '-v', '-o', str(timing), '--', *map(str, command)],
            cwd='/tmp', env=child_env(job), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise ToolError('worker_timeout', f'Worker exceeded {timeout}s; inspect {log}', 1)
    text = log.read_text(encoding='utf-8', errors='replace')
    rss = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', timing.read_text(errors='replace'))
    metrics = {'wall_ms': (time.perf_counter()-started)*1000, 'peak_rss_kib': int(rss[1]) if rss else None}
    return proc.returncode, text, {'log': str(log), 'timing': str(timing)}, metrics


def render(toolkit, ws, job, params):
    kind = params.get('ui', 'rive')
    if kind not in ['rive', 'umg']:
        raise ToolError('invalid_ui', 'UI must be rive or umg')
    package = components(toolkit)[kind]
    source = input_path(params.get('input') or str(package/'fixtures/input.riv'), ws)
    output = path_in_workspace(params.get('output') or str(job/'frame.png'), ws)
    if output.exists():
        raise ToolError('output_exists', 'Choose a fresh output PNG')
    width, height = int(params.get('width', 512)), int(params.get('height', 512))
    seconds = float(params.get('seconds', 0))
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or not math.isfinite(seconds) or seconds < 0:
        raise ToolError('invalid_dimensions', 'Width/height must be 1..4096; seconds must be finite and nonnegative')
    output.parent.mkdir(parents=True, exist_ok=True)
    dest = job/'renderer'
    dest.mkdir()
    arguments = [str(package/'render.sh'), str(source), '{output}', f'-Ui={kind}',
                 f'-Width={width}', f'-Height={height}', f'-Seconds={seconds}', f'-PlaybackMetadata={job}/playback.json']
    if params.get('scenario'):
        arguments.append('-Scenario='+str(input_path(params['scenario'], ws)))
    record = run_once(Path('/bin/bash'), arguments, output, 0, dest, child_env(job), 240, Path('/tmp'))
    save(job/'renderer-metrics.json', record)
    text = Path(record['log']).read_text(errors='replace')
    if record['status'] != 'passed' or record['runtime_device']['status'] != 'passed' or ERROR_LOG.search(text):
        raise ToolError('render_failed', f'CPU rendering failed; inspect {record["log"]}', 1)
    if kind == 'rive':
        draw = record['rive_draw']
        valid = draw['status'] == 'passed'
    else:
        lines = [line.split('RIVE_UE_REFERENCE_CAPTURE ', 1)[1] for line in text.splitlines() if 'RIVE_UE_REFERENCE_CAPTURE ' in line]
        fields = dict(token.split('=', 1) for token in shlex.split(lines[-1]) if '=' in token) if lines else {}
        valid = fields.get('render_path') == 'UE_RHI_RDG' and fields.get('umg_composite') == '1' and fields.get('rive_backend') == 'lite_rhi'
        valid = valid and fields.get('path') == str(output) and fields.get('width') == str(width) and fields.get('height') == str(height)
        draw = {'status': 'passed' if valid else 'failed', 'capture': fields, 'scope': 'Native UMG/Rive composite capture marker'}
    if not valid:
        raise ToolError('missing_draw_evidence', 'PNG was not bound to the expected native UI capture marker', 1)
    return {'ui': kind, 'output': {'path': str(output), 'sha256': sha256(output), 'width': width, 'height': height},
        'metrics': {'wall_ms': record['process_wall_seconds']*1000, 'first_png_ms': record['first_png_wall_seconds']*1000,
                    'peak_rss_kib': record['peak_rss_kib']}, 'draw': draw, 'device': record['runtime_device'],
        'artifacts': {'log': record['log'], 'measurement': str(job/'renderer-metrics.json'), 'playback': str(job/'playback.json')}}


def widget(toolkit, ws, job, params):
    argv = list(params.get('argv', []))
    if not argv or argv[0] not in ['create', 'read', 'inspect', 'import', 'patch', 'preview', 'export', 'animation']:
        raise ToolError('invalid_widget_command', CATALOG['widget'])
    path_flags = {'--content-dir', '--input', '--spec', '--patch', '--output', '--playback-script', '--shader-archive'}
    for i, item in enumerate(argv):
        key = item.split('=', 1)[0]
        if key in ['--workspace-root', '--report-dir']:
            raise ToolError('reserved_option', 'The unified CLI manages the workspace and job reports')
        if key in path_flags:
            if '=' not in item and i+1 >= len(argv):
                raise ToolError('invalid_arguments', f'Missing value for {key}')
            value = item.split('=', 1)[1] if '=' in item else argv[i+1] if i+1 < len(argv) else ''
            path = Path(value).expanduser()
            absolute = str((path if path.is_absolute() else ws/path).resolve())
            if '=' in item:
                argv[i] = key+'='+absolute
            else:
                argv[i+1] = absolute
    if not any(item.split('=', 1)[0] == '--content-dir' for item in argv):
        argv += ['--content-dir', str(ws/'Content')]
    native = job/'native'
    command = [sys.executable, '-B', str(components(toolkit)['widget']/'scripts/widget_bp.py'),
               '--workspace-root', str(ws), *argv, '--report-dir', str(native)]
    code, text, artifacts, metrics = invoke(command, job, 'widget', 420)
    report = load(native/'report.json') if (native/'report.json').is_file() else {'error': text[-4000:]}
    if code or report.get('status') != 'passed':
        raise ToolError('widget_failed', str(report.get('error', 'Native Widget command failed'))+f'; report: {native}', 1)
    return {'native': report, 'metrics': metrics, 'artifacts': {**artifacts, 'report': str(native/'report.json')}}


def verse(toolkit, ws, job, params):
    package = components(toolkit)['verse']
    action = params.get('action', 'test')
    if action == 'run':
        source = input_path(params['source'], ws)
        arguments = params.get('args') or []
    else:
        controller = input_path(params['controller'], ws) if params.get('controller') else package/'fixtures/verse/ui_controller.verse'
        source = job/'controller.verse'
        source.write_text(controller.read_text(encoding='utf-8')+'\n'+(package/'fixtures/verse/worker_main.verse').read_text(encoding='utf-8'), encoding='utf-8')
        arguments = [params.get('mode', 'pressed')]
    code, text, artifacts, metrics = invoke([package/'worker/Binaries/Linux/RiveVerseWorker', source, *arguments], job, 'verse')
    markers = re.findall(r'^RIVE_TEST (\w+) PASS$', text, re.M)
    commands = re.findall(r'^RIVE_UI bool Pressed (true|false)$', text, re.M)
    if code or ERROR_LOG.search(text) or (action != 'run' and (not VERSE_TESTS <= set(markers) or len(commands) != 1)):
        raise ToolError('verse_failed', f'Verse compile/execute failed (exit {code}); inspect {artifacts["log"]}', 1)
    result = {'source_sha256': sha256(source), 'tests': markers, 'ui_commands': commands, 'metrics': metrics,
              'phases': re.findall(r'^RIVE_VERSE_PHASE (.*)$', text, re.M), 'artifacts': artifacts,
              'source': str(source), 'uefn_validated': False}
    if action == 'run':
        result['stdout'] = text
    if action == 'ui':
        scenario = job/'scenario.json'
        save(scenario, {'mode': 'state_machine', 'artboard': 'New Artboard', 'state_machine': 'Button', 'fixed_delta': 1/60,
            'target_time': 1.0, 'events': [{'time': 0, 'type': 'bool', 'name': 'Hover', 'value': True},
            {'time': .25, 'type': 'bool', 'name': 'Press', 'value': commands[0] == 'true'}]})
        result['render'] = render(toolkit, ws, job, {'ui': params.get('ui', 'rive'), 'input': str(package/'fixtures/rocket.riv'),
            'scenario': str(scenario), 'output': params.get('output') or str(job/'frame.png')})
    return result


class Coordinator:
    def __init__(self, toolkit, ws):
        self.toolkit, self.ws = toolkit, ws
        self.lock = threading.Lock()
        self.active = None
        self.completed = 0
        self.server = None

    def dispatch(self, op, params):
        if op == 'status':
            return {'ok': True, 'running': True, 'pid': os.getpid(), 'workspace': str(self.ws), 'toolkit': str(self.toolkit),
                    'active_job': self.active, 'completed_jobs': self.completed, 'native_worker_lifetime': 'one operation'}
        if op == 'stop':
            if not self.lock.acquire(blocking=False):
                raise ToolError('busy', 'An operation is active; inspect status/jobs and stop after it finishes', 75)
            try:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return {'ok': True, 'stopping': True, 'pid': os.getpid()}
            finally:
                self.lock.release()
        if op not in ['render', 'widget', 'verse']:
            raise ToolError('unknown_operation', 'Unknown operation')
        if not self.lock.acquire(blocking=False):
            raise ToolError('busy', 'Another operation is active in this workspace', 75)
        job_id = uuid.uuid4().hex
        job = self.ws/'runs'/job_id
        job.mkdir()
        started = time.perf_counter()
        self.active = {'job_id': job_id, 'command': op, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        save(job/'request.json', {'command': op, 'parameters': params})
        save(job/'result.json', {'ok': None, 'status': 'running', **self.active})
        try:
            data = {'render': render, 'widget': widget, 'verse': verse}[op](self.toolkit, self.ws, job, params)
            result = {'ok': True, 'exit_code': 0, 'command': op, 'job_id': job_id, 'data': data}
        except Exception as error:
            result = failure(error)
            result.update(command=op, job_id=job_id)
        finally:
            self.active = None
            self.completed += 1
            self.lock.release()
        result.update(wall_ms=(time.perf_counter()-started)*1000, report=str(job/'result.json'))
        save(job/'result.json', result)
        return result


def failure(error):
    return {'ok': False, 'exit_code': getattr(error, 'exit_code', 1),
            'error': {'code': getattr(error, 'code', 'operation_failed'), 'message': str(error)}}


def endpoint(ws):
    return '\0rive-ue-lite-'+str(os.getuid())+'-'+hashlib.sha256(str(ws).encode()).hexdigest()[:24]


def request(ws, op, params=None, timeout=480):
    info = load(ws/'.rive-tool/control.json')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(endpoint(ws))
        connection.sendall((json.dumps({'protocol': PROTOCOL, 'token': info['token'], 'operation': op, 'parameters': params or {}})+'\n').encode())
        with connection.makefile('rb') as stream:
            line = stream.readline(32*1024*1024)
    if not line:
        raise ToolError('server_disconnected', 'Coordinator disconnected; consult jobs for the persisted result', 1)
    return json.loads(line)


def serve(toolkit, ws):
    info_path = ws/'.rive-tool/control.json'
    info = load(info_path)
    controller = Coordinator(toolkit, ws)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                incoming = self.rfile.readline(1024*1024+1)
                if uid != os.getuid() or len(incoming) > 1024*1024:
                    raise ToolError('invalid_client', 'Unauthorized or oversized request')
                message = json.loads(incoming)
                if message.get('protocol') != PROTOCOL or not hmac.compare_digest(str(message.get('token', '')), info['token']):
                    raise ToolError('invalid_client', 'Invalid local session')
                result = controller.dispatch(message['operation'], message.get('parameters', {}))
            except Exception as error:
                result = failure(error)
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write((json.dumps(result, ensure_ascii=False, allow_nan=False)+'\n').encode())

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = False

    with Server(endpoint(ws), Handler) as server:
        controller.server = server
        info.update(pid=os.getpid(), phase='ready')
        save(info_path, info, private=True)
        server.serve_forever(poll_interval=.1)
    info.update(phase='stopped')
    save(info_path, info, private=True)


def start(toolkit, ws):
    import fcntl
    with (ws/'.rive-tool/start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            status = request(ws, 'status', timeout=2)
            if status.get('running'):
                if status['toolkit'] != str(toolkit):
                    raise ToolError('different_toolkit', 'Stop the existing coordinator before changing toolkit versions')
                return {**status, 'reused': True}
        except (OSError, ValueError, KeyError):
            pass
        started = time.perf_counter()
        save(ws/'.rive-tool/control.json', {'protocol': PROTOCOL, 'token': secrets.token_hex(32), 'toolkit': str(toolkit), 'phase': 'starting'}, private=True)
        with (ws/'.rive-tool/server.log').open('ab') as log:
            proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--toolkit', str(toolkit),
                '--workspace', str(ws), 'serve'], stdout=log, stderr=subprocess.STDOUT, cwd=ws, start_new_session=True)
        for _ in range(200):
            try:
                result = request(ws, 'status', timeout=1)
                if result.get('running'):
                    return {**result, 'reused': False, 'coordinator_start_ms': (time.perf_counter()-started)*1000,
                            'native_workers_started': 0}
            except (OSError, ValueError, KeyError):
                pass
            if proc.poll() is not None:
                break
            time.sleep(.05)
        raise ToolError('start_failed', f'Coordinator failed to start; inspect {ws}/.rive-tool/server.log', 1)


def parse_args():
    parser = Parser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.cwd()/'workspaces/default')
    parser.add_argument('--toolkit', type=Path, default=ROOT, help='Combined distribution directory')
    parser.add_argument('--json', action='store_true', help='JSON is already the default for every operation')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['init', 'start', 'status', 'stop', 'capabilities', 'serve']:
        sub.add_parser(name, help=CATALOG.get(name))
    sub.add_parser('doctor', help=CATALOG['doctor']).add_argument('--verify', action='store_true')
    jobs = sub.add_parser('jobs', help=CATALOG['jobs'])
    jobs.add_argument('--id')
    jobs.add_argument('--logs', action='store_true')
    jobs.add_argument('--lines', type=int, default=80)
    rend = sub.add_parser('render', help=CATALOG['render'])
    rend.add_argument('--ui', choices=['rive', 'umg'], default='rive')
    rend.add_argument('--input')
    rend.add_argument('--output')
    rend.add_argument('--scenario')
    rend.add_argument('--width', type=int, default=512)
    rend.add_argument('--height', type=int, default=512)
    rend.add_argument('--seconds', type=float, default=0)
    sub.add_parser('widget', help=CATALOG['widget']).add_argument('argv', nargs=argparse.REMAINDER)
    verse_parser = sub.add_parser('verse', help='Native VerseVM tools')
    actions = verse_parser.add_subparsers(dest='action', required=True)
    run = actions.add_parser('run', help=CATALOG['verse run'])
    run.add_argument('--source', required=True)
    run.add_argument('--args', nargs='*', default=[])
    for action in ['test', 'ui']:
        cmd = actions.add_parser(action, help=CATALOG['verse '+action])
        cmd.add_argument('--controller')
        cmd.add_argument('--mode', choices=['pressed', 'idle'], default='pressed')
        if action == 'ui':
            cmd.add_argument('--ui', choices=['rive', 'umg'], default='rive')
            cmd.add_argument('--output')
    return parser.parse_args()


def main():
    args = parse_args()
    toolkit = args.toolkit.expanduser().resolve()
    if args.command in ['capabilities', 'doctor']:
        data = capabilities(toolkit) if args.command == 'capabilities' else doctor(toolkit, args.verify)
        ok = args.command != 'doctor' or data['ready']
        emit({'ok': ok, 'exit_code': 0 if ok else 1, 'data': data})
        return 0 if ok else 1
    if args.command == 'widget' and (args.argv == ['capabilities'] or '--help' in args.argv):
        script = components(toolkit)['widget']/'scripts/widget_bp.py'
        proc = subprocess.run([sys.executable, '-B', str(script), *args.argv], capture_output=True, text=True, timeout=20)
        if proc.returncode:
            raise ToolError('invalid_arguments', proc.stderr or proc.stdout)
        emit({'ok': True, 'exit_code': 0, 'data': json.loads(proc.stdout) if args.argv == ['capabilities'] else {'help': proc.stdout}})
        return 0
    if not sys.platform.startswith('linux'):
        raise ToolError('unsupported_host', 'Use the Linux distribution; rive-tool.ps1 forwards Windows commands to WSL Ubuntu')
    ws = workspace(args.workspace, toolkit)
    if args.command == 'serve':
        serve(toolkit, ws)
        return 0
    if args.command == 'init':
        emit({'ok': True, 'exit_code': 0, 'data': initialize(toolkit, ws)})
        return 0
    if args.command == 'jobs':
        if args.id:
            if not re.fullmatch(r'[0-9a-f]{32}', args.id):
                raise ToolError('invalid_job', 'Job IDs contain 32 lowercase hex digits')
            data = load(ws/'runs'/args.id/'result.json')
            if args.logs:
                if not 1 <= args.lines <= 500:
                    raise ToolError('invalid_arguments', 'Log tail lines must be 1..500')
                tails = {}
                for path in sorted((ws/'runs'/args.id).rglob('*.log')):
                    if path.resolve().is_relative_to(ws/'runs'/args.id):
                        with path.open(encoding='utf-8', errors='replace') as stream:
                            tails[path.relative_to(ws/'runs'/args.id).as_posix()] = ''.join(deque(stream, maxlen=args.lines))
                data = {'result': data, 'logs': tails}
        else:
            paths = sorted((ws/'runs').glob('*/result.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
            data = [{'job_id': p.parent.name, 'ok': load(p).get('ok'), 'command': load(p).get('command'), 'report': str(p)} for p in paths]
        emit({'ok': True, 'exit_code': 0, 'data': data})
        return 0
    if args.command == 'start':
        result = start(toolkit, ws)
    elif args.command == 'status':
        try:
            result = request(ws, 'status', timeout=2)
        except (OSError, ValueError, KeyError):
            result = {'ok': True, 'running': False, 'workspace': str(ws)}
    elif args.command == 'stop':
        try:
            result = request(ws, 'stop', timeout=3)
        except (OSError, ValueError, KeyError):
            result = {'ok': True, 'running': False}
        if result.get('ok'):
            for _ in range(100):
                try:
                    request(ws, 'status', timeout=.1)
                except (OSError, ValueError):
                    break
                time.sleep(.05)
    else:
        if not all(item['available'] for item in capabilities(toolkit)['components'].values()):
            raise ToolError('incomplete_toolkit', 'Use the combined all-tools distribution; inspect doctor')
        start(toolkit, ws)
        params = {key: value for key, value in vars(args).items() if key not in ['toolkit', 'workspace', 'command', 'json']}
        result = request(ws, args.command, params)
    emit(result)
    return result.get('exit_code', 0 if result.get('ok') else 1)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        result = failure(error)
        emit(result)
        raise SystemExit(result['exit_code'])
