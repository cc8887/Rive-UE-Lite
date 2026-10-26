#!/usr/bin/env bash
# Native Metal offscreen capture. It requires a Metal-capable Mac, not CPU Vulkan.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
INPUT="${1:-$ROOT/fixtures/input.riv}"
OUTPUT="${2:-$PWD/rive-output.png}"
shift "$(( $# < 2 ? $# : 2 ))"
[[ "$(uname -s)" == Darwin ]] || { echo 'This package requires macOS/Metal' >&2; exit 2; }
# BSD macOS does not provide GNU realpath -m.
[[ "$INPUT" = /* ]] || INPUT="$PWD/$INPUT"
[[ "$OUTPUT" = /* ]] || OUTPUT="$PWD/$OUTPUT"
mkdir -p "$(dirname -- "$OUTPUT")"
exec "$ROOT/Engine/Binaries/Mac/RiveRhiLite" \
    -mtl -sm5 -RenderOffScreen -norhithread -unattended -stdout -NoSplash -NoCrashDialog \
    -ProjectDir="$ROOT/" -UserDir="$(dirname -- "$OUTPUT")/.rive-ue-lite/" \
    -Input="$INPUT" -Output="$OUTPUT" -abslog="$OUTPUT.ue.log" \
    -ShaderArchive="$ROOT/shaders/global.bin" -ShaderDirectory="$ROOT/Engine/Shaders" "$@"
