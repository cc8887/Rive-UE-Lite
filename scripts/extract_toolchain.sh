#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
TC_PARENT="$TASK_ROOT/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64"
mkdir -p "$TC_PARENT"
tar -xzf "$TASK_ROOT/dependencies/native-linux-v26_clang-20.1.8-rockylinux8.tar.gz" -C "$TC_PARENT"
"$TC_PARENT/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++" --version
