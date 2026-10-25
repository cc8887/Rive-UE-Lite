#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveLiteShaderCompiler \
    -NoMutex -MaxParallelActions=4 \
    -Log="$TASK_ROOT/artifacts/setup/shader-compiler-diagnostic-ubt.log" "$@"
