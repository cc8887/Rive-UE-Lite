#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
LITE_ARCHIVE="$(realpath -- "${1:?lite archive}")"
REFERENCE_ARCHIVE="$(realpath -- "${2:?reference archive}")"
OUTPUT_ROOT="$(realpath -m -- "${3:?fresh evidence directory}")"
exec bash "$TASK_ROOT/scripts/measure_no_gpu.sh" -- python3 \
    "$TASK_ROOT/scripts/check_playback_rejections.py" \
    --scenario-manifest "$TASK_ROOT/fixtures/playback/scenarios.json" \
    --lite-archive "$LITE_ARCHIVE" --reference-archive "$REFERENCE_ARCHIVE" \
    --output-dir "$OUTPUT_ROOT"
