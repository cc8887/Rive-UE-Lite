#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$TASK_ROOT"
ulimit -c 0
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
unset DISPLAY WAYLAND_DISPLAY
mkdir -p artifacts/probe
exec "$TASK_ROOT/Binaries/Linux/RiveLiteRhiProbe" \
    -RenderOffScreen -AllowCPUDevices -vulkan -sm5 -norhithread \
    -unattended -NoSplash -NoCrashDialog -stdout -FullStdOutLogOutput \
    -ProbeRHI -Output="$TASK_ROOT/artifacts/probe/rhi-clear.png" \
    -abslog="$TASK_ROOT/artifacts/probe/ue-probe.log" "$@"
