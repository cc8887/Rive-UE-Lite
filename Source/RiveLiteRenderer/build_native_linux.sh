#!/usr/bin/env bash
set -euo pipefail

# Run this on Linux/WSL only after the isolated engine toolchain is installed.
# Invoke this script from the mounted prototype directory in WSL.
MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROTOTYPE_ROOT="$(cd -- "$MODULE_DIR/../.." && pwd)"
RUNTIME_ROOT="$PROTOTYPE_ROOT/vendor/rive-unreal/submodules/rive-runtime"
export RIVE_UNREAL_ENGINE="$PROTOTYPE_ROOT/engine"
export DEPENDENCIES="$PROTOTYPE_ROOT/vendor/rive-native-deps"

TOOLCHAIN_ROOT="$RIVE_UNREAL_ENGINE/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu"
test -x "$TOOLCHAIN_ROOT/bin/clang++" || { printf '%s\n' "Missing isolated UE clang toolchain: $TOOLCHAIN_ROOT/bin/clang++" >&2; exit 2; }
test -d "$DEPENDENCIES/dabeaz_ply_3.11" || { printf '%s\n' 'Run prepare_native_dependencies.py on Windows first.' >&2; exit 2; }

# Keep this build from occupying every CPU while UE builds alongside it.
export RIVE_NATIVE_BUILD_JOBS="${RIVE_NATIVE_BUILD_JOBS:-8}"
python3 - "$RUNTIME_ROOT" "$MODULE_DIR" <<'PY'
import json, pathlib, sys
runtime, module = map(pathlib.Path, sys.argv[1:])
normalized = []
for shell_script in (runtime.parents[1] / 'Scripts/build-rive').glob('*.sh'):
    data = shell_script.read_bytes()
    if b'\r\n' in data:
        shell_script.write_bytes(data.replace(b'\r\n', b'\n'))
        normalized.append(str(shell_script.relative_to(runtime.parents[1])))
script = runtime / 'build/build_rive.sh'
old = 'NUM_CORES=$(grep -c processor /proc/cpuinfo)'
new = 'NUM_CORES=${RIVE_NATIVE_BUILD_JOBS:-8}'
text = script.read_text()
if old in text:
    if text.count(old) != 1:
        raise RuntimeError('Ambiguous native job-count patch')
    script.write_text(text.replace(old, new), newline='\n')
elif new not in text:
    raise RuntimeError('Upstream native job-count detection changed')
driver = runtime.parents[1] / 'Scripts/build-rive/build-rive.py'
old_exit = 'if not do_linux(rive_runtime_path, True) or not do_linux(rive_runtime_path, False):\n                return'
new_exit = 'if not do_linux(rive_runtime_path, True) or not do_linux(rive_runtime_path, False):\n                raise SystemExit("Rive Linux native build failed")'
driver_text = driver.read_text()
if old_exit in driver_text:
    driver.write_text(driver_text.replace(old_exit, new_exit), newline='\n')
elif new_exit not in driver_text:
    raise RuntimeError('Upstream Linux failure propagation changed')
(module / 'native-build-patches.json').write_text(json.dumps({'patches': [{'path': 'vendor/rive-unreal/submodules/rive-runtime/build/build_rive.sh', 'old': old, 'new': new, 'scope': 'build parallelism only'}, {'path': 'vendor/rive-unreal/Scripts/build-rive/build-rive.py', 'scope': 'propagate native build failure as nonzero exit'}], 'normalized_shell_line_endings': normalized}, indent=2) + '\n')
PY

cd "$PROTOTYPE_ROOT/vendor/rive-unreal/Scripts/build-rive"
touch "$RUNTIME_ROOT/renderer/src/shaders/minify.py"
python3 build-rive.py --rive_runtime_path "$RUNTIME_ROOT" --disable_scripting --release_only --disable_lto --raw_shaders Linux

# Refresh the isolated 2D adapter from precisely the native build's generated headers/shaders.
python3 "$MODULE_DIR/stage_adapter.py" --source "$PROTOTYPE_ROOT/vendor/rive-unreal" --generated-include-root "$RUNTIME_ROOT/out/linux/release/include"
python3 "$MODULE_DIR/validate_source_slice.py"

python3 "$MODULE_DIR/record_native_build.py" --root "$PROTOTYPE_ROOT" --build-root "$PROTOTYPE_ROOT" --toolchain "$TOOLCHAIN_ROOT"
