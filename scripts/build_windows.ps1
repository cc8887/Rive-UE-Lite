param(
    [ValidateSet('RiveRhiLite','RiveLiteRhiProbe','RiveUeShaderCooker','RiveUeReference')]
    [string]$Target='RiveRhiLite',
    [string]$DotNet='dotnet',
    [int]$MaxParallelActions=4,
    [switch]$Plan
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Write-Output "RIVE_WINDOWS_BUILD target=$Target arch=x64 rhi=Vulkan default_runtime=RiveRhiLite"
if ($Plan) { return }
$patchArgs=@('--check')
if ($Target -in @('RiveUeShaderCooker','RiveUeReference')) { $patchArgs += '--with-tools' }
& python "$root/scripts/prepare_windows.py" @patchArgs
if ($LASTEXITCODE -ne 0) { throw 'Prepare the Windows prototype patches first' }
$tool="$root/dependencies/windows-msvc/AutoSDK/HostWin64/Win64/VS2026/14.50.35717"
if (!(Test-Path "$tool/bin/Hostx64/x64/cl.exe")) { throw 'Run python scripts/install_windows_msvc.py first' }
$oldSdk=$env:UE_SDKS_ROOT
$oldNative=$env:RIVE_LITE_NATIVE_LIB_DIR
try {
    $env:UE_SDKS_ROOT="$root/dependencies/windows-msvc/AutoSDK"
    $env:RIVE_LITE_NATIVE_LIB_DIR="$root/build/windows/rive-runtime/out/windows/release"
    New-Item "$root/artifacts/windows" -ItemType Directory -Force | Out-Null
    & $DotNet "$root/engine/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll" $Target Win64 Development "-Project=$root/RiveRhiLite.uproject" '-Compiler=VisualStudio2026' '-CompilerVersion=14.50.35731' -NoUBA -NoUbaLocal -NoHotReload "-MaxParallelActions=$MaxParallelActions" "-Log=$root/artifacts/windows/$Target-build.log"
    if ($LASTEXITCODE -ne 0) { throw "UBT failed ($LASTEXITCODE)" }
} finally {
    $env:UE_SDKS_ROOT=$oldSdk
    $env:RIVE_LITE_NATIVE_LIB_DIR=$oldNative
}
