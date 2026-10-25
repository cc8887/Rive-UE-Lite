#!/usr/bin/env bash
set -euo pipefail
MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROTOTYPE_ROOT="$(cd -- "$MODULE_DIR/../.." && pwd)"
export RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}"
BUILD_ROOT="$RIVE_LITE_CACHE_ROOT/native"
VENDOR_SOURCE="$PROTOTYPE_ROOT/vendor/rive-unreal"
VENDOR_BUILD="$BUILD_ROOT/vendor/rive-unreal"
RUNTIME_ROOT="$VENDOR_BUILD/submodules/rive-runtime"
TOOLCHAIN_REL=Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu
mkdir -p "$RUNTIME_ROOT" "$BUILD_ROOT/vendor/rive-native-deps" "$BUILD_ROOT/engine/$TOOLCHAIN_REL" "$VENDOR_BUILD/Scripts/build-rive"

rsync -a --exclude=.git --exclude=out --exclude='*.riv' --exclude='*.png' --exclude='*.jpg' --exclude='*.jpeg' \
    "$VENDOR_SOURCE/submodules/rive-runtime/" "$RUNTIME_ROOT/"
rsync -a --exclude=.git "$PROTOTYPE_ROOT/vendor/rive-native-deps/" "$BUILD_ROOT/vendor/rive-native-deps/"
rsync -a "$VENDOR_SOURCE/Scripts/build-rive/" "$VENDOR_BUILD/Scripts/build-rive/"
if [[ -x "$PROTOTYPE_ROOT/engine/$TOOLCHAIN_REL/bin/clang++" ]]; then
    rsync -a "$PROTOTYPE_ROOT/engine/$TOOLCHAIN_REL/" "$BUILD_ROOT/engine/$TOOLCHAIN_REL/"
elif [[ ! -x "$BUILD_ROOT/engine/$TOOLCHAIN_REL/bin/clang++" ]]; then
    printf '%s\n' "Missing isolated compiler in both prototype and approved native cache" >&2
    exit 2
fi
SIZE_BYTES="$(du -sb "$RIVE_LITE_CACHE_ROOT" | cut -f1)"
if (( SIZE_BYTES > 8589934592 )); then
    printf '%s\n' "The approved Linux staging budget was exceeded: $SIZE_BYTES bytes" >&2
    exit 2
fi
export RIVE_UNREAL_ENGINE="$BUILD_ROOT/engine"
export DEPENDENCIES="$BUILD_ROOT/vendor/rive-native-deps"
export RIVE_NATIVE_BUILD_JOBS=8
export PYTHONUNBUFFERED=1

# Windows checkout line endings and truthful upstream failure propagation.
python3 - "$VENDOR_BUILD" <<'PY'
from pathlib import Path
import sys
vendor = Path(sys.argv[1])
for path in (vendor / 'Scripts/build-rive').glob('*.sh'):
    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
driver = vendor / 'Scripts/build-rive/build-rive.py'
old = 'if not do_linux(rive_runtime_path, True) or not do_linux(rive_runtime_path, False):\n                return'
new = 'if not do_linux(rive_runtime_path, True) or not do_linux(rive_runtime_path, False):\n                raise SystemExit("Rive Linux native build failed")'
text = driver.read_text()
if old in text:
    driver.write_text(text.replace(old, new), newline='\n')
elif new not in text:
    raise RuntimeError('Unexpected native driver failure branch')
PY

cd "$VENDOR_BUILD/Scripts/build-rive"
# The minifier Makefile does not track FLAGS as an input. Force regeneration
# when changing from minified names to the upstream raw-shader mode required
# by UE's generated uniform metadata; no source content is changed.
touch "$RUNTIME_ROOT/renderer/src/shaders/minify.py"
python3 build-rive.py --rive_runtime_path "$RUNTIME_ROOT" --disable_scripting --release_only --disable_lto --raw_shaders Linux

# Return only native build outputs to the standalone Windows prototype.
mkdir -p "$VENDOR_SOURCE/Source/ThirdParty/RiveLibrary/Libraries/Linux"
rsync -a "$VENDOR_BUILD/Source/ThirdParty/RiveLibrary/Libraries/Linux/" "$VENDOR_SOURCE/Source/ThirdParty/RiveLibrary/Libraries/Linux/"
rsync -a "$VENDOR_BUILD/Source/ThirdParty/RiveLibrary/Includes/" "$VENDOR_SOURCE/Source/ThirdParty/RiveLibrary/Includes/"
rsync -a "$VENDOR_BUILD/Shaders/" "$VENDOR_SOURCE/Shaders/"
python3 "$MODULE_DIR/stage_adapter.py" --source "$VENDOR_SOURCE"
python3 "$MODULE_DIR/validate_source_slice.py"
python3 "$MODULE_DIR/record_native_build.py" --root "$PROTOTYPE_ROOT" --build-root "$BUILD_ROOT" --toolchain "$BUILD_ROOT/engine/$TOOLCHAIN_REL"
