"""Actual Lite RHI playback diagnostic; not the final paired archive gate."""
from pathlib import Path
import copy
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from compare_png import compare_images, read_png

OUT = ROOT / 'artifacts/playback/lite-smoke-01'
OUT.mkdir(parents=True, exist_ok=True)
if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1' or Path('/dev/dxg').exists() or Path('/dev/dri').exists():
    raise SystemExit('Use the real no-GPU namespace wrapper')
manifest_path = ROOT / 'fixtures/playback/scenarios.json'
manifest = json.loads(manifest_path.read_text())
env = dict(os.environ, VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json', VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json')
env.pop('DISPLAY', None)
env.pop('WAYLAND_DISPLAY', None)
report = {'scope': 'actual Lite CPU RHI driver diagnostic; no independent UE archive equivalence claim', 'cases': []}


def capture(case, point, control=False):
    folder = OUT / case['id'] / (('control-' if control else 'frame-') + str(point))
    folder.mkdir(parents=True, exist_ok=True)
    scenario = dict(copy.deepcopy(case['playback']), target_time=point)
    if control:
        scenario['events'] = []
    scenario_path = folder / 'scenario.json'
    scenario_path.write_text(json.dumps(scenario, indent=2) + '\n')
    cmd = [str(ROOT / 'Binaries/Linux/RiveRhiLite'), '-vulkan', '-sm5', '-RenderOffScreen', '-AllowCPUDevices', '-norhithread',
           '-unattended', '-stdout', '-FullStdOutLogOutput', '-NoCrashDialog', f'-ProjectDir={ROOT}/', f'-UserDir={folder / "user"}/',
           f'-Input={(manifest_path.parent / case["fixture"]).resolve()}', f'-Output={folder / "output.png"}',
           f'-ShaderDirectory={ROOT / "Shaders"}', f'-ShaderArchive={ROOT / "artifacts/shaders-independent-lite-01/global.bin"}',
           '-Width=512', '-Height=512', f'-Scenario={scenario_path}', f'-PlaybackMetadata={folder / "playback.json"}', f'-abslog={folder / "ue.log"}']
    with (folder / 'stdout.log').open('wb') as log:
        result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    metadata_path = folder / 'playback.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    pixels = read_png(folder / 'output.png')['rgba'] if (folder / 'output.png').exists() else b''
    record = {'time': point, 'control': control, 'exit_code': result.returncode, 'command': cmd,
              'metadata': metadata, 'png': str(folder / 'output.png'), 'unique_rgba': len(set(zip(*[iter(pixels)] * 4))) if pixels else 0}
    if result.returncode:
        print((folder / 'stdout.log').read_text(errors='replace')[-5000:], flush=True)
        raise RuntimeError(f'{case["id"]} {point}: actual exit {result.returncode}')
    print(json.dumps({'case': case['id'], 'time': point, 'control': control, 'exit': result.returncode,
                      'state_changes': metadata.get('state_changes'), 'current_animations': metadata.get('current_animations'),
                      'final_inputs': metadata.get('final_inputs'), 'unique_rgba': record['unique_rgba']}), flush=True)
    return record


for case in manifest['scenarios']:
    frames = [capture(case, point) for point in case['sample_times']]
    by_time = {row['time']: row for row in frames}
    changes = []
    for requirement in case['required_changes']:
        comparison = compare_images(Path(by_time[requirement['from']]['png']), Path(by_time[requirement['to']]['png']))
        changes.append(dict(requirement=requirement, different_pixels=comparison.get('different_pixels')))
    controls = []
    for point in case.get('event_effect_sample_times', []):
        row = capture(case, point, True)
        comparison = compare_images(Path(by_time[point]['png']), Path(row['png']))
        controls.append(dict(capture=row, different_pixels=comparison.get('different_pixels')))
    item = {'id': case['id'], 'frames': frames, 'changes': changes, 'controls': controls}
    item['status'] = 'passed' if all(row['different_pixels'] > 0 for row in changes + controls) else 'failed'
    report['cases'].append(item)
    (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'case': case['id'], 'status': item['status'], 'changes': changes,
                      'controls_different_pixels': [row['different_pixels'] for row in controls]}), flush=True)
report['status'] = 'passed' if all(case['status'] == 'passed' for case in report['cases']) else 'failed'
(OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report['status'] == 'passed' else 1)
