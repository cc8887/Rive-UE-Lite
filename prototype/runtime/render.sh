#!/usr/bin/env bash
# Usage: bash render.sh [input.riv] [output.png] [-Width=512 -Height=512 ...]
set -euo pipefail
PACKAGE_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
INPUT="${1:-$PACKAGE_ROOT/fixtures/input.riv}"
OUTPUT="${2:-$PWD/rive-output.png}"
shift "$(( $# < 2 ? $# : 2 ))"
INPUT="$(realpath -- "$INPUT")"
OUTPUT="$(realpath -m -- "$OUTPUT")"
mkdir -p "$(dirname -- "$OUTPUT")"
ICD="${RIVE_LITE_ICD:-}"
if [[ -z "$ICD" ]]; then
    shopt -s nullglob
    ICD_CANDIDATES=(/usr/share/vulkan/icd.d/*lvp*.json)
    [[ ${#ICD_CANDIDATES[@]} -gt 0 ]] || { echo 'Mesa Lavapipe ICD not found; install it or set RIVE_LITE_ICD=/absolute/path/lvp.json' >&2; exit 2; }
    ICD="${ICD_CANDIDATES[0]}"
fi
export VK_ICD_FILENAMES="$ICD" VK_DRIVER_FILES="$ICD"
unset DISPLAY WAYLAND_DISPLAY
exec "$PACKAGE_ROOT/Engine/Binaries/Linux/RiveRhiLite" \
    -vulkan -sm5 -RenderOffScreen -AllowCPUDevices -norhithread -unattended \
    -stdout -NoSplash -NoCrashDialog \
    -ProjectDir="$PACKAGE_ROOT/" -UserDir="$(dirname -- "$OUTPUT")/.rive-ue-lite/" \
    -Input="$INPUT" -Output="$OUTPUT" -abslog="$OUTPUT.ue.log" \
    -ShaderArchive="$PACKAGE_ROOT/shaders/global.bin" -ShaderDirectory="$PACKAGE_ROOT/Engine/Shaders" "$@"
