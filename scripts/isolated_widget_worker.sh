#!/usr/bin/env bash
# Hide development/build resources in a private namespace, then hide GPU nodes
# and drop privileges. Package contents remain visible and unmodified.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ "${1:-}" != --inside ]]; then
    [[ "$(id -u)" == 0 && "${1:-}" == -- ]] || exit 2
    export WIDGET_WORKER_ORIGIN_MNT="$(readlink /proc/self/ns/mnt)"
    shift
    exec unshare --mount --fork -- bash "$0" --inside "$@"
fi
shift
[[ "$(readlink /proc/self/ns/mnt)" != "$WIDGET_WORKER_ORIGIN_MNT" ]] || exit 2
mount --make-rprivate /
for DIR in engine vendor Binaries Intermediate Source dependencies build Config; do
    [[ -d "$TASK_ROOT/$DIR" ]] || continue
    mount -t tmpfs -o nosuid,nodev,mode=0555,size=1M widget-worker-hidden "$TASK_ROOT/$DIR"
done
echo 'WIDGET_WORKER_PORTABLE development_engine=hidden development_vendor=hidden build_sources=hidden native_cwd=/tmp' >&2
# Keep CLI-relative arguments rooted in the prototype. Both native test drivers
# explicitly launch the UE process from /tmp, avoiding development-path fallback.
cd "$TASK_ROOT"
exec bash "$TASK_ROOT/scripts/measure_no_gpu.sh" -- "$@"
