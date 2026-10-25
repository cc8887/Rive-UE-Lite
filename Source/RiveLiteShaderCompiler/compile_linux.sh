#!/usr/bin/env bash
# Offline shader compilation only; this process never supplies rendering evidence.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
OUTPUT="${RIVE_LITE_SHADER_ARCHIVE:-$TASK_ROOT/artifacts/shaders/RiveGlobalShaderCache-VULKAN_SM5_LINUX.bin}"
CACHE="${RIVE_LITE_SHADER_JOB_CACHE:-${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}/shader-jobs}"
if [[ "${1:-}" != -* && -n "${1:-}" ]]; then
    OUTPUT="$1"
    shift
fi
cd "$TASK_ROOT"
ulimit -c 0
export LD_LIBRARY_PATH="$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu:${LD_LIBRARY_PATH:-}"
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
unset DISPLAY WAYLAND_DISPLAY
exec "$TASK_ROOT/Binaries/Linux/RiveLiteShaderCompiler" \
    -nullrhi -unattended -nosound -stdout -CrashTrace \
    -RiveShaderDir="$TASK_ROOT/Shaders" -Output="$OUTPUT" -CacheDir="$CACHE" "$@"
