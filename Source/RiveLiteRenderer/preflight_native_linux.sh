#!/usr/bin/env bash
set -euo pipefail
MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROTOTYPE_ROOT="$(cd -- "$MODULE_DIR/../.." && pwd)"
RUNTIME_ROOT="$PROTOTYPE_ROOT/vendor/rive-unreal/submodules/rive-runtime"
export DEPENDENCIES="$PROTOTYPE_ROOT/vendor/rive-native-deps"
export PREMAKE_PATH="$RUNTIME_ROOT/build"
cd "$RUNTIME_ROOT/renderer"
"$RUNTIME_ROOT/build/dependencies/premake-core/bin/v5.0.0-beta7_release/premake5" \
    gmake2 --config=release --out=../out/linux/release --os=linux \
    --for_unreal --no_gl --cpp20 --with_rive_canvas --track_rive_shader_id \
    --with_rive_text --with_rive_layout --with_rive_audio=external --raw_shaders --no-lto --with-pic
