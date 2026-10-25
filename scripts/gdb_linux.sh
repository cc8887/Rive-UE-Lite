#!/usr/bin/env bash
# Isolated Ubuntu debugger prefix; no system package installation required.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DEBUGGER_ROOT="$TASK_ROOT/dependencies/gdb/root"
export LD_LIBRARY_PATH="$DEBUGGER_ROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export DEBUGINFOD_URLS=
exec "$DEBUGGER_ROOT/usr/bin/gdb" --data-directory="$DEBUGGER_ROOT/usr/share/gdb" \
    -nx -iex 'set debuginfod enabled off' "$@"
