#!/usr/bin/env bash
# Build both actual playback hosts; keep the original static build logs intact.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
RUN_NAME="${1:-playback-hosts-01}"
[[ "$RUN_NAME" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
for TARGET in RiveRhiLite RiveUeReference; do
    bash "$TASK_ROOT/scripts/build_linux_cached.sh" "$TARGET" -NoMutex \
        -MaxParallelActions=6 "-Log=$TASK_ROOT/artifacts/setup/$RUN_NAME-$TARGET.ubt.log"
done
