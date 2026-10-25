#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export DOTNET_ROOT="$TASK_ROOT/engine/Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64"
export DOTNET_CLI_HOME="$TASK_ROOT/build/dotnet-home"
export NUGET_PACKAGES="$TASK_ROOT/dependencies/nuget"
export NUGET_CERT_REVOCATION_MODE=offline
export DOTNET_CLI_TELEMETRY_OPTOUT=1
exec "$DOTNET_ROOT/dotnet" publish \
    "$TASK_ROOT/engine/Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj" \
    -c Development --no-build --no-restore -p:NuGetAudit=false \
    -o "$TASK_ROOT/engine/Engine/Binaries/DotNET/UnrealBuildTool"
