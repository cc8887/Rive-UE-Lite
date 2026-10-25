#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - "$ROOT" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
receipt = json.loads((root / 'Source/RiveLiteRenderer/native-build-result.json').read_text())
if not receipt.get('compiled') or not receipt.get('shader_token_names_preserved'):
    raise RuntimeError('Finish the actual raw-shader native library build before reference link')
PY
exec bash "$ROOT/scripts/build_linux_cached.sh" RiveUeReference \
    -MaxParallelActions=6 "-Log=$ROOT/artifacts/setup/reference-ubt.log" "$@"
