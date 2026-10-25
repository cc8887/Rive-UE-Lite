#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export DOTNET_ROOT="$TASK_ROOT/engine/Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64"
export DOTNET_CLI_HOME="$TASK_ROOT/build/dotnet-home"
export NUGET_PACKAGES="$TASK_ROOT/dependencies/nuget"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export NUGET_CERT_REVOCATION_MODE=offline
if [[ -n "${UE_GIT_OBJECTS:-}" ]]; then
    export GIT_ALTERNATE_OBJECT_DIRECTORIES="$UE_GIT_OBJECTS"
fi
if [[ ! -d "$TASK_ROOT/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8" ]]; then
    # Reuse only this experiment's verified native-build SDK cache.
    RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-$HOME/.cache/rive-ue-lite}"
    export LINUX_MULTIARCH_ROOT="$RIVE_LITE_CACHE_ROOT/native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8"
fi
export PATH="$DOTNET_ROOT:$PATH"
cd "$TASK_ROOT/engine"
if [[ "${1:-}" == "publish-ubt" ]]; then
    shift
    dotnet publish Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj -c Development \
        --no-build --no-restore --output Engine/Binaries/DotNET/UnrealBuildTool -v minimal "$@"
elif [[ "${1:-}" == "ubt" ]]; then
    shift
    dotnet build Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj -c Development -v minimal "$@"
else
    TARGET="${1:-RiveLiteRhiProbe}"
    shift || true
    PARALLEL_ARG=-MaxParallelActions=12
    for ARG in "$@"; do
        [[ "$ARG" == -MaxParallelActions=* ]] && PARALLEL_ARG=""
    done
    dotnet Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll "$TARGET" Linux Development \
        -Project="$TASK_ROOT/RiveRhiLite.uproject" -NoUBA -NoUbaLocal \
        -NoHotReload ${PARALLEL_ARG:+"$PARALLEL_ARG"} "$@"
fi
