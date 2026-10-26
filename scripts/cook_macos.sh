#!/usr/bin/env bash
# Two native cooker invocations with separate DDCs/outputs for comparison.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
[[ "$(uname -s)" == Darwin ]] || { echo 'Metal cooking requires the Mac toolchain' >&2; exit 2; }
ARCH="${1:-arm64}"
[[ "$ARCH" == arm64 || "$ARCH" == x64 ]] || exit 2
OUTPUT="${2:-$ROOT/artifacts/macos/cook-$ARCH}"
[[ ! -e "$OUTPUT" ]] || { echo 'Use a fresh shader output directory' >&2; exit 2; }
bash "$ROOT/scripts/build_macos.sh" --arch="$ARCH" --cooker
COOKER="$ROOT/Binaries/Mac/RiveUeShaderCooker"
[[ -x "$COOKER" ]] || COOKER="$ROOT/Binaries/Mac/RiveUeShaderCooker.app/Contents/MacOS/RiveUeShaderCooker"
[[ -x "$COOKER" ]] || { echo 'Cooker executable missing' >&2; exit 2; }
mkdir -p "$OUTPUT"
OUTPUT="$(cd -- "$OUTPUT" && pwd)"
for FLAVOR in lite reference; do
    mkdir -p "$OUTPUT/$FLAVOR"
    env "UE-LocalDataCachePath=$OUTPUT/$FLAVOR/ddc" "$COOKER" \
        -nullrhi -unattended -stdout -NoShaderWorker -NoSplash \
        -ProjectDir="$ROOT/" -UserDir="$OUTPUT/$FLAVOR/user/" \
        -RiveShaderDir="$ROOT/Shaders" -Output="$OUTPUT/$FLAVOR/global.bin" \
        -abslog="$OUTPUT/$FLAVOR/cook.log"
done
echo "Independent Metal archives: $OUTPUT/lite/global.bin and $OUTPUT/reference/global.bin"
