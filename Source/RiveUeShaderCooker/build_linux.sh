#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveUeShaderCooker \
    -NoMutex -MaxParallelActions="${RIVE_CANONICAL_JOBS:-12}" \
    -Log="${RIVE_CANONICAL_BUILD_LOG:-$TASK_ROOT/artifacts/setup/canonical-cooker-ubt.log}" "$@"
