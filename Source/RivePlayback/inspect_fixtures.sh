#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
NATIVE="${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}/native"
SDK="$NATIVE/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu"
VENDOR="$NATIVE/vendor/rive-unreal"
mkdir -p "$ROOT/artifacts/playback"
"$SDK/bin/clang++" --sysroot="$SDK" -stdlib=libc++ -std=c++20 -fno-exceptions -fno-rtti \
    -DWITH_RIVE_TEXT -DRIVE_CANVAS -DTRACK_RIVE_SHADER_ID -DWITH_RIVE_AUDIO -DEXTERNAL_RIVE_AUDIO_ENGINE -DWITH_RIVE_LAYOUT \
    -I"$VENDOR/submodules/rive-runtime/include" "$ROOT/Source/RivePlayback/inspect_fixtures.cpp" \
    "$VENDOR/submodules/rive-runtime/utils/no_op_factory.cpp" \
    -Wl,--start-group "$VENDOR"/Source/ThirdParty/RiveLibrary/Libraries/Linux/*.a -Wl,--end-group \
    -Wl,--start-group -lc++ -lc++abi -Wl,--end-group -lpthread -ldl -lm \
    -o "$ROOT/artifacts/playback/inspect_fixtures" >"$ROOT/artifacts/playback/inspect-build.log" 2>&1
"$ROOT/artifacts/playback/inspect_fixtures" "$@"
