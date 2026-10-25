#!/usr/bin/env bash
# Run the Engine-free compiler into a new archive with independent provenance.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
[[ $# -ge 3 ]] || { echo 'Usage: cook_independent_linux.sh NEW_ARCHIVE NEW_EVIDENCE_DIR FINAL_BUILD_LOG [compiler flags]' >&2; exit 2; }
OUTPUT="$(realpath -m -- "$1")"
EVIDENCE="$(realpath -m -- "$2")"
BUILD_LOG="$(realpath -- "$3")"
shift 3
COMPILER="$TASK_ROOT/Binaries/Linux/RiveLiteShaderCompiler"
CACHE="${RIVE_LITE_SHADER_JOB_CACHE:-${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}/shader-jobs}"
ulimit -c 0
unset DISPLAY WAYLAND_DISPLAY
exec python3 "$TASK_ROOT/scripts/measure_cook_provenance.py" \
    --kind lite_helper --compiler "$COMPILER" --archive "$OUTPUT" \
    --output-dir "$EVIDENCE" --build-log "$BUILD_LOG" \
    --source-input "$TASK_ROOT/Source/RiveLiteShaderCompiler/Private" \
    --source-input "$TASK_ROOT/Source/RiveLiteShaderCompiler/RiveLiteShaderCompiler.Build.cs" \
    --source-input "$TASK_ROOT/Source/RiveLiteShaderCompiler/RiveLiteShaderCompiler.Target.cs" \
    --source-input "$TASK_ROOT/Source/RiveLiteShaderCompiler/generate_shader_support.py" \
    --source-input "$TASK_ROOT/Source/RiveLiteRenderer/Private" \
    --source-input "$TASK_ROOT/Source/RiveLiteRenderer/Public" \
    --source-input "$TASK_ROOT/Source/RiveLiteRenderer/RiveLiteRenderer.Build.cs" \
    --source-input "$TASK_ROOT/engine/Engine/Shaders" \
    --source-input "$TASK_ROOT/engine/Engine/Config" \
    --source-input "$TASK_ROOT/Config" --source-input "$TASK_ROOT/Shaders" \
    --source-input "$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libdxcompiler.so" \
    --source-input "$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libShaderConductor.so" \
    --env "LD_LIBRARY_PATH=$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu" \
    --env SDL_VIDEODRIVER=dummy --env SDL_AUDIODRIVER=dummy --execute -- \
    "$COMPILER" -nullrhi -unattended -nosound -stdout -CrashTrace \
    -RiveShaderDir="$TASK_ROOT/Shaders" -Output="$OUTPUT" -CacheDir="$CACHE" "$@"
