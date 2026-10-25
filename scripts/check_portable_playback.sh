#!/usr/bin/env bash
# The new playback package must also work with source/vendor and GPU nodes hidden.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PACKAGE_ROOT="$(realpath -- "${1:?package directory}")"
OUTPUT_ROOT="$(realpath -m -- "${2:?fresh output directory}")"
mkdir -p "$OUTPUT_ROOT"
exec bash "$TASK_ROOT/scripts/check_portable_linux.sh" \
    "$PACKAGE_ROOT" "$OUTPUT_ROOT/bounce.png" --fixture fixtures/ball_test.riv \
    "-Scenario=$PACKAGE_ROOT/fixtures/playback/bounce_animation.json" \
    "-PlaybackMetadata=$OUTPUT_ROOT/playback.json"
