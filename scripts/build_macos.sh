#!/usr/bin/env bash
# Native Mac build; WSL experiments use probe_macos_cross.py.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
ARCH=arm64
TARGET=RiveRhiLite
PLAN=0
ARGS=()
for ARG in "$@"; do
    case "$ARG" in
        --arch=arm64) ARCH=arm64 ;;
        --arch=x64) ARCH=x64 ;;
        --probe) TARGET=RiveLiteRhiProbe ;;
        --cooker) TARGET=RiveUeShaderCooker ;;
        --reference) TARGET=RiveUeReference ;;
        --plan) PLAN=1 ;;
        --help|-h) echo 'Usage: build_macos.sh [--arch=arm64|x64] [--probe|--cooker|--reference] [--plan] [UBT arguments]'; exit 0 ;;
        --*) echo "Unsupported Mac option: $ARG (UMG/Verse builds remain separate)" >&2; exit 2 ;;
        *) ARGS+=("$ARG") ;;
    esac
done
printf 'RIVE_MAC_BUILD target=%s arch=%s rhi=Metal default_runtime=RiveRhiLite\n' "$TARGET" "$ARCH"
[[ "$PLAN" == 0 ]] || exit 0
[[ "$(uname -s)" == Darwin ]] || { echo 'Native Mac build needs macOS/Xcode. On WSL run: python3 scripts/probe_macos_cross.py' >&2; exit 2; }
command -v python3 >/dev/null
xcrun --sdk macosx --find clang++ >/dev/null
if [[ "$TARGET" == RiveUeShaderCooker || "$TARGET" == RiveUeReference ]]; then
    python3 "$ROOT/scripts/prepare_macos.py" --check --with-tools
else
    python3 "$ROOT/scripts/prepare_macos.py" --check
fi
NATIVE="$ROOT/build/macos/native-driver/Source/ThirdParty/RiveLibrary"
if [[ "$TARGET" != RiveLiteRhiProbe ]]; then
    SUFFIX=Mac; [[ "$ARCH" != x64 ]] || SUFFIX=Intel
    export RIVE_LITE_NATIVE_LIB_DIR="${RIVE_LITE_NATIVE_LIB_DIR:-$NATIVE/Libraries/Mac/$SUFFIX}"
    export RIVE_LITE_INCLUDE_DIR="${RIVE_LITE_INCLUDE_DIR:-$NATIVE/Includes}"
    python3 "$ROOT/scripts/check_macos_archives.py" --arch "$ARCH" "$RIVE_LITE_NATIVE_LIB_DIR"
    [[ -f "$RIVE_LITE_INCLUDE_DIR/rive/file.hpp" ]] || { echo 'Run scripts/build_native_macos.py first' >&2; exit 2; }
fi
# Development tools are explicit targets, never dependencies of the Lite runtime.
export DOTNET_CLI_HOME="$ROOT/build/macos/dotnet-home"
export NUGET_PACKAGES="$ROOT/dependencies/nuget"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 DOTNET_CLI_TELEMETRY_OPTOUT=1
mkdir -p "$ROOT/artifacts/macos"
bash "$ROOT/engine/Engine/Build/BatchFiles/Mac/Build.sh" "$TARGET" Mac Development \
    -architecture="$ARCH" -Project="$ROOT/RiveRhiLite.uproject" \
    -NoUBA -NoUbaLocal -NoHotReload -MaxParallelActions=8 \
    -Log="$ROOT/artifacts/macos/$TARGET-$ARCH.log" "${ARGS[@]}"
if [[ "$TARGET" == RiveRhiLite ]]; then
    python3 "$ROOT/scripts/audit_macos_boundary.py" --arch "$ARCH"
fi
