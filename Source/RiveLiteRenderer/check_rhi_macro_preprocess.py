#!/usr/bin/env python3
"""Diagnose the unchanged Rive multiline ATTR macro with real clang -E."""
from pathlib import Path
import os
import json
import re
import subprocess

root = Path(__file__).resolve().parents[2]
shader = root / 'Shaders/Private/Rive/Generated'
output = root / 'artifacts/shaders/rhi-macro-probe'
output.mkdir(parents=True, exist_ok=True)
rhi = (shader / 'rhi.minified.ush').read_text()
constants = (shader / 'constants.minified.ush').read_text()
draw = (shader / 'atomic_draw.minified.ush').read_text()
declarations = [re.search(r'^#define ' + key + r'.*$', text, re.M).group(0)
                for key, text in [('CONCAT', rhi), ('ATTR\\(', rhi),
                                  ('IMAGE_CLIP_RECT_INVERSE_MATRIX_ATTRIB_IDX', constants)]]
call = re.search(r'ATTR\(\s*IMAGE_CLIP_RECT_INVERSE_MATRIX_ATTRIB_IDX,.*?\);', draw, re.S).group(0)
probe = output / 'exact-upstream-multiline-attr.hlsl'
probe.write_text('\n'.join(declarations) + '\n' + call + '\n')
cache_root = Path(os.environ.get('RIVE_LITE_CACHE_ROOT', Path.home() / '.cache/rive-ue-lite'))
compiler = Path(os.environ.get(
    'UE_LINUX_CLANG',
    cache_root / 'native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++',
))
result = subprocess.run([str(compiler), '-E', '-P', '-x', 'c', str(probe)], capture_output=True, text=True)
(output / 'clang-preprocessed.hlsl').write_text(result.stdout)
(output / 'clang-stderr.log').write_text(result.stderr)
passed = result.returncode == 0 and 'ATTRIBUTE3' in result.stdout
report = {'scope': 'exact upstream macro, clang C preprocessing only; not UE ShaderPreprocessor acceptance',
          'compiler_exit_code': result.returncode, 'attribute3_expansion_passed': passed,
          'preprocessed': result.stdout.strip()}
(output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(0 if passed else 1)
