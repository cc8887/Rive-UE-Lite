#!/usr/bin/env bash
# Run as root: only the private GPU-free wrapper needs root, the host is uid1000.
set -uo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="${1:-fix_rectangle}"
RUN_NAME="${2:-integration-01}"
shift "$(( $# < 2 ? $# : 2 ))"
CAPTURE_DIR="$ROOT/artifacts/captures/$RUN_NAME"
mkdir -p "$CAPTURE_DIR"
bash "$ROOT/scripts/measure_no_gpu.sh" -- \
    bash "$ROOT/scripts/run_rive_linux.sh" RiveUeReference "$FIXTURE" "$RUN_NAME" "$@"
STATUS=$?
printf '{"target":"RiveUeReference","fixture":"%s","linux_exit_code":%d}\n' \
    "$FIXTURE" "$STATUS" > "$CAPTURE_DIR/RiveUeReference-$FIXTURE.exit.json"
exit "$STATUS"
