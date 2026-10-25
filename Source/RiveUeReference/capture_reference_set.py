#!/usr/bin/env python3
"""Capture the pinned five-file Engine Program baseline in a GPU-free namespace."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'scripts'))
from compare_png import read_png, sha256

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-name', default='integration-02')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('The private no-GPU namespace wrapper requires root; the host runs as uid1000.')
output = root / 'artifacts/captures' / args.run_name
output.mkdir(parents=True, exist_ok=True)
archive = root / 'artifacts/shaders/RiveGlobalShaderCache-VULKAN_SM5_LINUX.bin'
archive_hash = sha256(archive)
pin = json.loads((root / 'Source/RiveUeReferenceRenderer/upstream-manifest.json').read_text())
report = {
    'scope': 'Engine/Renderer-linked Program with original Rive FRenderTarget wrapper; same shader archive as lite',
    'editor_viewport': False, 'umg_composite': False, 'independent_canonical_cook_verified': False,
    'binary_sha256': sha256(root / 'Binaries/Linux/RiveUeReference'),
    'rive_unreal_commit': pin['source_commit'], 'rive_runtime_commit': pin['runtime_commit'],
    'shader_archive_sha256': archive_hash, 'captures': []}
for fixture in ('fix_rectangle', 'blend_test', 'clip_tests', 'bankcard', 'circle_clips'):
    log = output / f'RiveUeReference-{fixture}.console.log'
    with log.open('w') as stream:
        result = subprocess.run(['bash', str(root / 'Source/RiveUeReference/run_reference_capture.sh'), fixture, args.run_name],
                                stdout=stream, stderr=subprocess.STDOUT)
    entry = {'fixture': fixture, 'linux_exit_code': result.returncode,
             'fixture_sha256': sha256(root / 'fixtures' / (fixture + '.riv'))}
    contents = log.read_text(errors='replace')
    entry['capture_markers'] = [line for line in contents.splitlines() if 'RIVE_UE_REFERENCE_CAPTURE ' in line]
    entry['gpu_free_namespace_evidence'] = 'dxg=absent dri=absent' in contents
    entry['cpu_device_selected'] = 'Type=VK_PHYSICAL_DEVICE_TYPE_CPU' in contents and 'llvmpipe' in contents
    png = output / f'RiveUeReference-{fixture}.png'
    if result.returncode == 0 and png.is_file():
        decoded = read_png(png)
        pixels = decoded.pop('rgba')
        entry.update(png=str(png), png_sha256=sha256(png), png_info=decoded,
                     nonzero_alpha_pixels=sum(value > 0 for value in pixels[3::4]),
                     unique_rgba=len({pixels[index:index + 4] for index in range(0, len(pixels), 4)}))
        if not entry['nonzero_alpha_pixels']:
            entry['coverage_note'] = 'transparent initial artboard state; does not establish visible clipping coverage'
    entry['passed'] = result.returncode == 0 and bool(entry['capture_markers']) and png.is_file() and entry['cpu_device_selected'] and entry['gpu_free_namespace_evidence']
    report['captures'].append(entry)
    print(f'{fixture}: exit={result.returncode} png={png.is_file()} passed={entry["passed"]}', flush=True)
    if not entry['passed']:
        break
report['shader_archive_unchanged'] = sha256(archive) == archive_hash
report['complete'] = len(report['captures']) == 5 and all(item['passed'] for item in report['captures']) and report['shader_archive_unchanged']
(output / 'reference-captures.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report['complete'] else 1)
