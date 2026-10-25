#!/usr/bin/env bash
# Records a direct invocation of the independently linked native Engine compiler.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
[[ $# -ge 3 ]] || { echo 'Usage: cook_linux.sh NEW_ARCHIVE NEW_EVIDENCE_DIR FINAL_BUILD_LOG [native cook flags]' >&2; exit 2; }
OUTPUT="$(realpath -m -- "$1")"
EVIDENCE="$(realpath -m -- "$2")"
BUILD_LOG="$(realpath -- "$3")"
shift 3
COMPILER="$TASK_ROOT/Binaries/Linux/RiveUeShaderCooker"
CACHE="${RIVE_LITE_CANONICAL_DDC:-${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}/canonical-ddc}"
mkdir -p "$CACHE"
ulimit -c 0
PATCH_INPUTS=()
for PATCH in "$TASK_ROOT"/prototype/patches/[0-9][0-9][0-9][0-9]-*.patch; do
    PATCH_INPUTS+=(--source-input "$PATCH")
done
exec python3 "$TASK_ROOT/scripts/measure_cook_provenance.py" \
    --kind ue_engine_canonical --compiler "$COMPILER" --archive "$OUTPUT" \
    --output-dir "$EVIDENCE" --build-log "$BUILD_LOG" \
    --source-input "$TASK_ROOT/Source/RiveUeShaderCooker/Private" \
    --source-input "$TASK_ROOT/Source/RiveUeShaderCooker/RiveUeShaderCooker.Build.cs" \
    --source-input "$TASK_ROOT/Source/RiveUeShaderCooker/RiveUeShaderCooker.Target.cs" \
    --source-input "$TASK_ROOT/Source/RiveUeShaderCooker/prepare_bootstrap.py" \
    --source-input "$TASK_ROOT/Source/RiveUeReferenceRenderer/Private" \
    --source-input "$TASK_ROOT/Source/RiveUeReferenceRenderer/Public" \
    --source-input "$TASK_ROOT/Source/RiveUeReferenceRenderer/RiveUeReferenceRenderer.Build.cs" \
    --source-input "$TASK_ROOT/engine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp" \
    --source-input "$TASK_ROOT/engine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompilerEditor.cpp" \
    --source-input "$TASK_ROOT/engine/Engine/Source/Runtime/Engine/Public/SceneView.h" \
    --source-input "$TASK_ROOT/engine/Engine/Source/Runtime/Engine/Private/SceneView.cpp" \
    --source-input "$TASK_ROOT/engine/Engine/Shaders" \
    --source-input "$TASK_ROOT/engine/Engine/Config" \
    --source-input "$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libdxcompiler.so" \
    --source-input "$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libShaderConductor.so" \
    --source-input "$TASK_ROOT/Config" \
    --source-input "$TASK_ROOT/Shaders" "${PATCH_INPUTS[@]}" \
    --env "LD_LIBRARY_PATH=$TASK_ROOT/engine/Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu:${LD_LIBRARY_PATH:-}" \
    --env SDL_VIDEODRIVER=dummy --env SDL_AUDIODRIVER=dummy --execute -- \
    "$COMPILER" -nullrhi -noshaderworker -unattended -nosound -NoSplash -NoCrashDialog \
    -stdout -FullStdOutLogOutput -TargetPlatform=Linux '-DDC=(Local)' \
    -LocalDataCachePath="$CACHE" -ProjectDir="$TASK_ROOT/" \
    -UserDir="$EVIDENCE/user/" \
    -RiveShaderDir="$TASK_ROOT/Shaders" -Output="$OUTPUT" "$@"
