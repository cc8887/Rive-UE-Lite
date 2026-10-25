#!/usr/bin/env bash
# A real Rive capture through UE Vulkan RHI/RDG; no shader compiler at runtime.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
TARGET="${1:-RiveRhiLite}"
FIXTURE="${2:-fix_rectangle}"
RUN_NAME="${3:-integration}"
shift "$(( $# < 3 ? $# : 3 ))"
[[ "$TARGET" == RiveRhiLite || "$TARGET" == RiveUeReference ]] || exit 2
CAPTURE_ROOT="$TASK_ROOT/artifacts/captures/$RUN_NAME"
mkdir -p "$CAPTURE_ROOT"
ulimit -c 0
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
unset DISPLAY WAYLAND_DISPLAY
cd "$TASK_ROOT"
exec "$TASK_ROOT/Binaries/Linux/$TARGET" \
    -RenderOffScreen -AllowCPUDevices -vulkan -sm5 -norhithread \
    -unattended -NoSplash -NoCrashDialog -stdout -FullStdOutLogOutput \
    -ProjectDir="$TASK_ROOT/" \
    -UserDir="$CAPTURE_ROOT/$TARGET-$FIXTURE-user/" \
    -Input="$TASK_ROOT/fixtures/$FIXTURE.riv" \
    -Output="$CAPTURE_ROOT/$TARGET-$FIXTURE.png" \
    -ShaderArchive="$TASK_ROOT/artifacts/shaders/RiveGlobalShaderCache-VULKAN_SM5_LINUX.bin" \
    -ShaderDirectory="$TASK_ROOT/Shaders" -Width=512 -Height=512 -Seconds=0 \
    -abslog="$CAPTURE_ROOT/$TARGET-$FIXTURE.ue.log" "$@"
