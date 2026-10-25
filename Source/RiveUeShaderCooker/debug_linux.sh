#!/usr/bin/env bash
# Diagnostic execution only; formal cook evidence comes from cook_linux.sh.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
[[ $# -eq 1 ]] || { echo 'Usage: debug_linux.sh FRESH_DIAGNOSTIC_DIR' >&2; exit 2; }
DIAGNOSTIC="$(realpath -m -- "$1")"
mkdir -p "$DIAGNOSTIC"
export LD_LIBRARY_PATH="$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu:${LD_LIBRARY_PATH:-}"
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
ulimit -c 0
cd "$TASK_ROOT"
RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}"
exec bash "$TASK_ROOT/scripts/gdb_linux.sh" --batch --return-child-result -ex 'set pagination off' -ex run \
    -ex 'thread apply all bt 20' --args "$TASK_ROOT/Binaries/Linux/RiveUeShaderCooker" \
    -nullrhi -noshaderworker -unattended -nosound -NoSplash -NoCrashDialog \
    -stdout -FullStdOutLogOutput -TargetPlatform=Linux '-DDC=(Local)' \
    -LocalDataCachePath="$RIVE_LITE_CACHE_ROOT/canonical-ddc" \
    -ProjectDir="$TASK_ROOT/" -UserDir="$DIAGNOSTIC/user/" \
    -RiveShaderDir="$TASK_ROOT/Shaders" -Output="$DIAGNOSTIC/global.bin" -Type=FNULLPS
