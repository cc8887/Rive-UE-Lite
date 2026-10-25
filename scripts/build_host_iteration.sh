#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveRhiLite -NoMutex \
  -MaxParallelActions=6 "-Log=$TASK_ROOT/artifacts/setup/rive-host-ubt.log"
