#!/usr/bin/env bash
# Hide prototype development sources and GPU nodes in private namespaces.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ "${1:-}" != --inside ]]; then
    [[ "$(id -u)" == 0 && $# -ge 2 ]] || { echo 'Usage (root): check_verse_portable.sh package output-dir [--mode idle]' >&2; exit 2; }
    export RIVE_VERSE_ORIGIN="$(readlink /proc/self/ns/mnt)"
    exec unshare --mount --fork -- bash "$0" --inside "$@"
fi
shift
[[ "$(readlink /proc/self/ns/mnt)" != "$RIVE_VERSE_ORIGIN" ]]
PACKAGE="$(realpath -- "$1")"
OUTPUT="$(realpath -m -- "$2")"
shift 2
[[ "$PACKAGE" == "$TASK_ROOT/package/"* ]]
[[ -x "$PACKAGE/worker/Binaries/Linux/RiveVerseWorker" ]]
mount --make-rprivate /
for DIRECTORY in engine vendor Source; do
    mount -t tmpfs -o nosuid,nodev,mode=0555,size=1M "rive-verse-hidden-$DIRECTORY" "$TASK_ROOT/$DIRECTORY"
done
echo 'RIVE_VERSE_PORTABLE development_engine=hidden vendor=hidden Source=hidden cwd=/tmp' >&2
cd /tmp
exec bash "$TASK_ROOT/scripts/measure_no_gpu.sh" -- bash "$PACKAGE/verse-ui.sh" --output-dir "$OUTPUT" "$@"
