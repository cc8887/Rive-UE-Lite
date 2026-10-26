#!/usr/bin/env bash
# Run the staged application with its development engine/vendor trees hidden.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
MODE="${1:-}"
if [[ "$MODE" == --capture ]]; then
    shift
    PACKAGE_ROOT="$(realpath -- "$1")"
    OUTPUT_PNG="$(realpath -m -- "$2")"
    shift 2
    CAPTURE_INPUT="$PACKAGE_ROOT/fixtures/input.riv"
    if [[ "${1:-}" == --fixture ]]; then
        [[ $# -ge 2 ]] || exit 2
        CAPTURE_INPUT="$(realpath -- "$PACKAGE_ROOT/$2")"
        [[ "$CAPTURE_INPUT" == "$PACKAGE_ROOT/"* ]] || exit 2
        shift 2
    fi
    mkdir -p "$(dirname -- "$OUTPUT_PNG")"
    export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
    export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
    unset DISPLAY WAYLAND_DISPLAY
    ulimit -c 0
    cd /tmp
    exec bash "$PACKAGE_ROOT/render.sh" "$CAPTURE_INPUT" "$OUTPUT_PNG" \
        -Width=512 -Height=512 -Seconds=0 "$@"
fi
if [[ "$MODE" != --inside ]]; then
    [[ "$(id -u)" == 0 && $# -ge 2 ]] || { echo 'Usage (root): check_portable_linux.sh package-dir output.png [host flags]' >&2; exit 2; }
    PACKAGE_ROOT="$(realpath -- "$1")"
    [[ -x "$PACKAGE_ROOT/Engine/Binaries/Linux/RiveRhiLite" || -x "$PACKAGE_ROOT/Engine/Binaries/Linux/RiveUmgHost" ]]
    [[ "$PACKAGE_ROOT" != "$TASK_ROOT/engine"* && "$PACKAGE_ROOT" != "$TASK_ROOT/vendor"* ]]
    export RIVE_LITE_PORTABLE_ORIGIN="$(readlink /proc/self/ns/mnt)"
    shift
    exec unshare --mount --fork -- bash "$0" --inside "$PACKAGE_ROOT" "$@"
fi
shift
[[ "$(readlink /proc/self/ns/mnt)" != "$RIVE_LITE_PORTABLE_ORIGIN" ]]
mount --make-rprivate /
mount -t tmpfs -o nosuid,nodev,mode=0555,size=1M rive-lite-hidden-engine "$TASK_ROOT/engine"
mount -t tmpfs -o nosuid,nodev,mode=0555,size=1M rive-lite-hidden-vendor "$TASK_ROOT/vendor"
echo 'RIVE_LITE_PORTABLE_CHECK development_engine=hidden development_vendor=hidden cwd=/tmp' >&2
exec bash "$TASK_ROOT/scripts/measure_no_gpu.sh" -- bash "$0" --capture "$@"
