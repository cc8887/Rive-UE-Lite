#!/usr/bin/env python3
"""Execute real VerseVM code, validate its protocol, then render its UI command.

The transport is a batch command bridge, not a UEFN player/widget API emulator.
Shared controller source is concatenated unchanged with the standalone adapter.
"""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import time

from compare_png import sha256
from measure_ue_lite import run_once

ROOT = Path(__file__).resolve().parents[1]
TESTS = ['event_resume', 'event_no_sticky_replay', 'suspended',
         'race_cancel_defer_no_late_resume', 'failure_rollback', 'all']

def run_worker(exe, script, mode, dest, env):
    dest.mkdir(parents=True, exist_ok=True)
    process_env = dict(env)
    process_env.pop('RIVE_VERSE_INCREMENTAL', None)
    command = [str(exe), str(script), mode]
    started = time.perf_counter()
    with (dest/'worker.log').open('wb') as log:
        run = subprocess.run(['/usr/bin/time', '-v', '-o', str(dest/'time.txt'), *command],
            cwd=Path('/tmp'), env=process_env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    text = (dest/'worker.log').read_text(errors='replace')
    markers = re.findall(r'^RIVE_TEST (\w+) PASS$', text, re.M)
    commands = re.findall(r'^RIVE_UI bool Pressed (true|false)$', text, re.M)
    memory = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', (dest/'time.txt').read_text())
    phases = re.findall(r'^RIVE_VERSE_PHASE (.*)$', text, re.M)
    errors = re.findall(r'^.*(?:Ensure condition failed|Fatal error:|Log\w+: Error:).*$', text, re.M)
    result = {'command': command, 'exit_code': run.returncode,
        'process_wall_ms': (time.perf_counter()-started)*1000,
        'peak_rss_kib': int(memory[1]) if memory else None,
        'markers': markers, 'ui_commands': commands, 'phases': phases,
        'errors': errors, 'log': str(dest/'worker.log')}
    result['status'] = 'passed' if (run.returncode == 0 and not errors and set(TESTS) <= set(markers)
        and len(commands) == 1) else 'failed'
    return result

def make_scenario(command):
    if command not in ['true', 'false']:
        raise ValueError('Unsupported UI command')
    return {'mode': 'state_machine', 'artboard': 'New Artboard', 'state_machine': 'Button',
        'fixed_delta': 1/60, 'target_time': 1.0,
        'events': [{'time': 0, 'type': 'bool', 'name': 'Hover', 'value': True},
                   {'time': .25, 'type': 'bool', 'name': 'Press', 'value': command == 'true'}]}

def run_pipeline(exe, package, source, mode, dest, env):
    dest.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    worker = run_worker(exe, source, mode, dest/'worker', env)
    if worker['status'] != 'passed':
        return {'status': 'failed', 'worker': worker}
    scenario = dest/'scenario.json'
    scenario.write_text(json.dumps(make_scenario(worker['ui_commands'][0]), indent=2)+'\n')
    render_dir = dest/'render'; render_dir.mkdir()
    render_offset = time.perf_counter()-started
    rendering = run_once(Path('/bin/bash'), [str(package/'render.sh'),
        str(package/'fixtures/rocket.riv'), '{output}', '-Width=512', '-Height=512',
        f'-Scenario={scenario}', f'-PlaybackMetadata={dest}/playback.json'],
        dest/'output.png', 0, render_dir, env, 120, Path('/tmp'))
    first_png = render_offset + rendering['first_png_wall_seconds'] if rendering['first_png_wall_seconds'] is not None else None
    status = 'passed' if rendering['status'] == 'passed' and rendering['runtime_device']['status'] == 'passed' else 'failed'
    return {'status': status, 'worker': worker, 'render': rendering,
        'pipeline_wall_ms': (time.perf_counter()-started)*1000,
        'sequential_first_png_seconds': first_png,
        'first_png_scope': 'worker process including compile/execute/exit, followed by renderer startup and complete PNG; 10ms renderer sampling',
        'shared_source_sha256': sha256(source)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, default=ROOT/'Binaries/Linux/RiveVerseWorker')
    parser.add_argument('--package', type=Path, default=ROOT/'package/ui-rive-01')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--mode', choices=['pressed', 'idle'], default='pressed')
    args = parser.parse_args()
    dest = args.output_dir.resolve()
    if dest.exists() and any(dest.iterdir()):
        parser.error('Use a fresh output directory')
    dest.mkdir(parents=True, exist_ok=True)
    controller = ROOT/'fixtures/verse/ui_controller.verse'
    adapter = ROOT/'fixtures/verse/worker_main.verse'
    source = dest/'ui_test.verse'
    source.write_text(controller.read_text()+'\n'+adapter.read_text())
    report = run_pipeline(args.worker.resolve(), args.package.resolve(), source, args.mode, dest/'run', os.environ)
    report['source_inputs'] = [{'path': str(p), 'sha256': sha256(p)} for p in [controller, adapter]]
    report['uefn_comparison'] = 'not_run'
    (dest/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'report': str(dest/'report.json')}))
    return 0 if report['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
