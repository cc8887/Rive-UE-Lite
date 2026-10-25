#!/usr/bin/env bash
# Diagnostic: a valid archive must load before the deliberately missing .riv.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
unset DISPLAY WAYLAND_DISPLAY
ulimit -c 0
cd "$TASK_ROOT"
set +e
"$TASK_ROOT/Binaries/Linux/RiveRhiLite" \
  -vulkan -sm5 -RenderOffScreen -AllowCPUDevices -norhithread -unattended -stdout \
  -ProjectDir="$TASK_ROOT/" -ShaderDirectory="$TASK_ROOT/Shaders" \
  -UserDir="$TASK_ROOT/artifacts/shaders/archive-smoke-user/" \
  -ShaderArchive="$TASK_ROOT/artifacts/shaders/freeze-smoke.bin" \
  -Input="$TASK_ROOT/fixtures/__deliberately_absent__.riv" \
  -Output="$TASK_ROOT/artifacts/shaders/archive-load-diagnostic.png" \
  -abslog="$TASK_ROOT/artifacts/shaders/archive-load-diagnostic.ue.log"
RESULT=$?
set -e
echo "RIVE_LITE_ARCHIVE_LOAD_DIAGNOSTIC expected_exit=4 actual_exit=$RESULT no_rive_draw_expected=1"
[[ "$RESULT" == 4 ]]
