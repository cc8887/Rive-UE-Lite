#!/usr/bin/env python3
"""Measure the optional packaged VerseVM -> Rive chain and scoped runtime tests."""
from pathlib import Path
import argparse
import json
import os
import re
import statistics
import time

from compare_png import compare_images, sha256
from measure_ue_lite import apply_cpu_profile, run_once
from run_verse_ui import run_pipeline, run_worker

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--native-archive', type=Path, default=ROOT/'artifacts/umg-optional/shaders-reference/global.bin')
    a = p.parse_args()
    out, package = a.output_dir.resolve(), a.package.resolve()
    if out.exists(): p.error('Use a fresh evidence directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1': p.error('Run under measure_no_gpu.sh')
    out.mkdir(parents=True)
    env = dict(os.environ, VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json',
        VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json',
        SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LANG='C', LC_ALL='C')
    profile = apply_cpu_profile(2, 2, env)
    controller = (package/'fixtures/verse/ui_controller.verse').read_text()
    adapter = (package/'fixtures/verse/worker_main.verse').read_text()
    script = out/'ui_test.verse'; script.write_text(controller+'\n'+adapter)
    exe = package/'worker/Binaries/Linux/RiveVerseWorker'
    before = {str(path): sha256(path) for path in [exe, ROOT/'Binaries/Linux/RiveRhiLite', ROOT/'Binaries/Linux/RiveUmgHost']}
    report = {'status': 'incomplete', 'cpu_profile': profile, 'runs': [], 'negative_tests': [], 'native_pairs': [],
        'scope': 'actual VerseVM bytecode and batch UI transport; shared controller semantics; CPU UE RHI/RDG screenshots; excludes Fortnite native APIs and UEFN sessions',
        'gpu_nodes': {n: Path(n).exists() for n in ['/dev/dxg', '/dev/dri']},
        'namespace': os.environ.get('RIVE_UE_LITE_MOUNT_NAMESPACE'),
        'worker_sha256': sha256(exe), 'controller_sha256': sha256(package/'fixtures/verse/ui_controller.verse'),
        'hot_reload': {'status': 'failed_in_experiment_not_exposed',
            'evidence': str(ROOT/'artifacts/verse-vm/incremental-probe-01.log'),
            'reason': 'Second BuildAll hit native LoaderImport assertion while replacing compiled framework packages. Supported edit path restarts worker.'},
        'uefn_comparison': {'status': 'not_run', 'unverified': ['target UEFN compiler/language/API version',
            'BPVM and new VerseVM sessions', 'Fortnite player/devices/UI bindings', 'UEFN layout/pixels',
            'network/replication/persistence', 'Verse Reload/Live Edit', 'Rive custom widget import into UEFN']}}
    try:
        for repeat in range(3):
            for mode in ['pressed', 'idle']:
                dest = out/f'{mode}-{repeat}'
                result = run_pipeline(exe, package, script, mode, dest, env)
                result.update(mode=mode, repeat=repeat)
                report['runs'].append(result)
                if result['status'] != 'passed': raise RuntimeError(f'{mode}-{repeat} failed')
                assert result['worker']['ui_commands'] == ['true' if mode == 'pressed' else 'false']
        # Semantic edits to the same controller body; each edit executes new
        # bytecode in a fresh worker. Native executable must stay identical.
        edit_times = []
        for index, increment in enumerate([2, 3, 4]):
            changed = out/f'edited-{index}.verse'
            changed_controller = controller.replace('set Clicks += 1', f'set Clicks += {increment}')
            changed_adapter = re.sub(r'Model\.Clicks = ([12])\b',
                lambda match: f'Model.Clicks = {int(match[1])*increment}', adapter)
            changed.write_text(changed_controller+'\n'+changed_adapter)
            result = run_worker(exe, changed, 'pressed', out/f'edit-{index}', env)
            if result['status'] != 'passed': raise RuntimeError(f'Edited script {index} failed')
            edit_times.append(result)
        report['verse_edit_runs'] = edit_times
        mutations = [('event', controller.replace('set Pressed = Value', 'set Pressed = false'), 11),
            ('cancel_cleanup', controller.replace('set Cancelled += 1', 'set Cancelled += 0'), 14),
            ('failure_expected', controller.replace('        false?', '        true?'), 15)]
        for name, content, expected in mutations:
            changed = out/f'negative-{name}.verse'; changed.write_text(content+'\n'+adapter)
            result = run_worker(exe, changed, 'pressed', out/f'negative-{name}', env)
            result['expected_exit_code'] = expected
            result['rejected_as_expected'] = result['exit_code'] == expected and not result['ui_commands']
            report['negative_tests'].append(result)
            if not result['rejected_as_expected']: raise RuntimeError(f'Negative {name} not rejected by runtime guard')
        native_archive = a.native_archive.resolve()
        assert native_archive != (package/'shaders/global.bin').resolve()
        report['shader_archives'] = {str(p): sha256(p) for p in [native_archive, package/'shaders/global.bin']}
        for mode in ['pressed', 'idle']:
            dest = out/f'native-{mode}'; dest.mkdir()
            scenario = out/f'{mode}-0/scenario.json'
            metadata = dest/'playback.json'
            result = run_once(ROOT/'Binaries/Linux/RiveUeReference',
                ['-Ui=rive', '-vulkan', '-sm5', '-AllowCPUDevices', '-RenderOffscreen', '-norhithread', '-unattended', '-stdout',
                 f'-ProjectDir={ROOT}/', f'-UserDir={dest}/user/', f'-Input={package}/fixtures/rocket.riv',
                 '-Output={output}', f'-ShaderArchive={native_archive}', f'-ShaderDirectory={ROOT}/Shaders',
                 '-Width=512', '-Height=512', f'-Scenario={scenario}', f'-PlaybackMetadata={metadata}'],
                dest/'output.png', 0, dest, env, 120, Path('/tmp'))
            comparison = compare_images(dest/'output.png', out/f'{mode}-0/output.png')
            same_state = json.loads(metadata.read_text()) == json.loads((out/f'{mode}-0/playback.json').read_text())
            report['native_pairs'].append({'mode': mode, 'native': result, 'comparison': comparison, 'playback_equal': same_state})
            if result['status'] != 'passed' or result['runtime_device']['status'] != 'passed' or comparison['status'] != 'passed' or not same_state:
                raise RuntimeError(f'Native comparison failed for {mode}')
        report['visible_state_difference'] = compare_images(out/'pressed-0/output.png', out/'idle-0/output.png')
        assert report['visible_state_difference']['different_pixels'] > 0
        report['binaries_unchanged_during_verse_edits'] = all(sha256(Path(path)) == digest for path, digest in before.items())
        assert report['binaries_unchanged_during_verse_edits']
        runs = report['runs']
        def phases(key):
            return [float(match[1]) for r in runs for phase in r['worker']['phases']
                if (match := re.search(rf'\b{key}=([\d.]+)', phase))]
        report['metrics'] = {
            'worker_process_wall_ms_median': statistics.median(r['worker']['process_wall_ms'] for r in runs),
            'worker_core_ready_ms_median': statistics.median(phases('core_ready_ms')),
            'worker_compile_load_ms_median': statistics.median(phases('compile_load_ms')),
            'worker_ready_ms_median': statistics.median(phases('ready_ms')),
            'worker_peak_rss_kib_range': [min(r['worker']['peak_rss_kib'] for r in runs), max(r['worker']['peak_rss_kib'] for r in runs)],
            'renderer_peak_rss_kib_range': [min(r['render']['peak_rss_kib'] for r in runs), max(r['render']['peak_rss_kib'] for r in runs)],
            'sequential_first_png_seconds_median': statistics.median(r['sequential_first_png_seconds'] for r in runs),
            'sequential_first_png_seconds_range': [min(r['sequential_first_png_seconds'] for r in runs), max(r['sequential_first_png_seconds'] for r in runs)],
            'verse_edit_worker_cycle_ms_median': statistics.median(r['process_wall_ms'] for r in edit_times),
            'timing_scope': '2 CPU cores; separate process per run/edit, OS caches may be warm; not a cold machine boot or in-process hot reload'}
        report['status'] = 'passed_scoped'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = str(error)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ['status', 'metrics', 'error']}, indent=2))
    return 0 if report['status'] == 'passed_scoped' else 1

if __name__ == '__main__':
    raise SystemExit(main())
