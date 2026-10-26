#!/usr/bin/env python3
"""Capture Lite/native UE on Mac with separately cooked Metal archives."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from package_macos import validate_shader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lite-shaders', type=Path, required=True)
    parser.add_argument('--reference-shaders', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('Metal runtime comparison must run on a Mac')
    for path in [args.lite_shaders, args.reference_shaders]:
        validate_shader(path)
    if os.path.samefile(args.lite_shaders, args.reference_shaders):
        raise RuntimeError('Two independent cooker outputs are required, not one shared file')
    out = args.output.resolve()
    if out.exists(): raise RuntimeError('Use a fresh evidence directory')
    out.mkdir(parents=True)
    reports = []
    for name, archive in [('RiveRhiLite', args.lite_shaders), ('RiveUeReference', args.reference_shaders)]:
        binary = ROOT/f'Binaries/Mac/{name}'
        if not binary.is_file(): binary = ROOT/f'Binaries/Mac/{name}.app/Contents/MacOS/{name}'
        png, log = out/(name+'.png'), out/(name+'.log')
        command = ['/usr/bin/time', '-l', str(binary), '-mtl', '-sm5', '-RenderOffScreen', '-norhithread',
                   '-unattended', '-stdout', '-NoSplash', '-Ui=rive', '-ProjectDir='+str(ROOT)+'/',
                   '-Input='+str(ROOT/'fixtures/bankcard.riv'), '-Output='+str(png),
                   '-ShaderArchive='+str(archive.resolve()), '-ShaderDirectory='+str(ROOT/'Shaders'),
                   '-abslog='+str(log), '-UserDir='+str(out/name)+'/']
        start = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        text = result.stdout+result.stderr
        (out/(name+'.console.log')).write_text(text)
        marker = 'RiveDrawCompleted=1' if name == 'RiveRhiLite' else 'engine_frender_target=1'
        passed = (result.returncode == 0 and png.is_file() and 'Metal' in text
                  and 'render_path=UE_RHI_RDG' in text and marker in text
                  and not any(error in text for error in ['Ensure condition failed', 'Fatal error:', 'Assertion failed:']))
        reports.append({'target': name, 'exit_code': result.returncode, 'wall_seconds': time.monotonic()-start,
                        'passed': passed, 'command': command})
        if not passed: break
    passed = len(reports) == 2 and all(r['passed'] for r in reports)
    if passed:
        comparison = subprocess.run(['python3', str(ROOT/'scripts/compare_png.py'),
                                     '--actual', str(out/'RiveRhiLite.png'), '--reference', str(out/'RiveUeReference.png'),
                                     '--output', str(out/'comparison.json')], capture_output=True, text=True)
        (out/'comparison.log').write_text(comparison.stdout+comparison.stderr)
        passed = comparison.returncode == 0
    report = {'status': 'passed' if passed else 'failed', 'captures': reports,
              'scope': 'bankcard static capture on native Metal; not UMG, animation matrix or CPU Metal'}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
