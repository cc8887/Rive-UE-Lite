#!/usr/bin/env bash
# Focused regression before the full 60-capture suite; explicit custom scope.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
LITE_ARCHIVE="$(realpath -- "${1:?new lite archive}")"
LITE_PROVENANCE="$(realpath -- "${2:?new lite cook provenance}")"
OUTPUT_ROOT="$(realpath -m -- "${3:?fresh diagnostic directory}")"
PROBE_MANIFEST="${OUTPUT_ROOT}-inputs.json"
[[ ! -e "$OUTPUT_ROOT" && ! -e "$PROBE_MANIFEST" ]] || exit 2
mkdir -p -- "$(dirname -- "$PROBE_MANIFEST")"
python3 - "$TASK_ROOT" "$PROBE_MANIFEST" <<'PY'
import copy
import json
from pathlib import Path
import sys

root, output = map(Path, sys.argv[1:])
source = json.loads((root / 'fixtures/playback/scenarios.json').read_text())
case = copy.deepcopy(next(item for item in source['scenarios'] if item['id'] == 'bounce_animation'))
case['fixture'] = str((root / 'fixtures/ball_test.riv').resolve())
case['sample_times'] = [0, 0.25]
case['required_changes'] = [{'from': 0, 'to': 0.25}]
output.write_text(json.dumps({'schema_version': 1, 'scenarios': [case]}, indent=2) + '\n')
PY
exec bash "$TASK_ROOT/scripts/measure_no_gpu.sh" -- python3 \
    "$TASK_ROOT/scripts/measure_playback_matrix.py" \
    --lite-executable "$TASK_ROOT/Binaries/Linux/RiveRhiLite" \
    --reference-executable "$TASK_ROOT/Binaries/Linux/RiveUeReference" \
    --lite-archive "$LITE_ARCHIVE" --lite-cook-provenance "$LITE_PROVENANCE" \
    --reference-archive "$TASK_ROOT/artifacts/shaders-canonical/full-01/global.bin" \
    --reference-cook-provenance "$TASK_ROOT/artifacts/shaders-canonical/full-01/provenance/provenance.json" \
    --lite-shader-directory "$TASK_ROOT/Shaders" --reference-shader-directory "$TASK_ROOT/Shaders" \
    --scenario-manifest "$PROBE_MANIFEST" \
    --static-fixture "$TASK_ROOT/fixtures/bankcard.riv" \
    --coverage-profile custom-selected --output-dir "$OUTPUT_ROOT" --execute
