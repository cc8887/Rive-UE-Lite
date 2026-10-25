#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$ROOT/scripts/build_linux_cached.sh" RiveUeReference \
    "-WriteOutdatedActions=$ROOT/artifacts/setup/reference-actions.json" \
    "-Log=$ROOT/artifacts/setup/reference-actions-ubt.log"
