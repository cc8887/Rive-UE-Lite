#!/usr/bin/env python3
"""Compare the five final lite captures with the genuine Engine Program output."""
from pathlib import Path
import argparse
import json
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'scripts'))
from compare_png import compare_images, sha256

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-name', default='integration-02')
args = parser.parse_args()
folder = root / 'artifacts/captures' / args.run_name
baseline = json.loads((folder / 'reference-captures.json').read_text())
report = {'scope': 'five initial default-artboard states, 512x512 linear RGBA8, Seconds=0, same inline SPIR-V archive',
          'canonical_ue_cook_independently_verified': False, 'editor_or_umg_composite_verified': False,
          'shader_archive_sha256': baseline['shader_archive_sha256'], 'fixtures': []}
for item in baseline['captures']:
    fixture = item['fixture']
    reference = folder / f'RiveUeReference-{fixture}.png'
    lite = folder / f'RiveRhiLite-{fixture}.png'
    if not (reference.is_file() and lite.is_file()):
        raise SystemExit(f'Wait for both final capture files: {fixture}')
    comparison = compare_images(reference, lite)
    comparison.update(fixture=fixture, fixture_sha256=item['fixture_sha256'],
                      reference_nonzero_alpha_pixels=item['nonzero_alpha_pixels'],
                      reference_unique_rgba=item['unique_rgba'])
    if 'coverage_note' in item:
        comparison['coverage_note'] = item['coverage_note']
    report['fixtures'].append(comparison)
    print(f'{fixture}: {comparison["status"]} different={comparison.get("different_pixels")} alpha_different={comparison.get("alpha_different_pixels")}', flush=True)
report['shader_archive_unchanged'] = sha256(root / 'artifacts/shaders/RiveGlobalShaderCache-VULKAN_SM5_LINUX.bin') == baseline['shader_archive_sha256']
report['status'] = 'passed' if baseline['complete'] and report['shader_archive_unchanged'] and len(report['fixtures']) == 5 and all(item['status'] == 'passed' for item in report['fixtures']) else 'failed'
(folder / 'comparison-five-fixtures.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report['status'] == 'passed' else 1)
