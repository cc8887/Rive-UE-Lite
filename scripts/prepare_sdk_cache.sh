#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
VERSION=v26_clang-20.1.8-rockylinux8
CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}"
SDK_ROOT="$CACHE_ROOT/native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/$VERSION"
test -x "$SDK_ROOT/x86_64-unknown-linux-gnu/bin/clang++"
tar -xOzf "$TASK_ROOT/dependencies/native-linux-$VERSION.tar.gz" "$VERSION/ToolchainVersion.txt" > "$SDK_ROOT/ToolchainVersion.txt"
cat "$SDK_ROOT/ToolchainVersion.txt"
