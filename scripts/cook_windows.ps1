param([string]$Output)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (!$Output) { $Output="$root/artifacts/windows/cook" }
if (Test-Path $Output) { throw 'Use a fresh shader output directory' }
$oldCache=[Environment]::GetEnvironmentVariable('UE-LocalDataCachePath')
try {
    foreach ($flavor in @('lite','reference')) {
        $dir=New-Item "$Output/$flavor" -ItemType Directory -Force
        [Environment]::SetEnvironmentVariable('UE-LocalDataCachePath',"$dir/ddc")
        & "$root/Binaries/Win64/RiveUeShaderCooker.exe" -nullrhi -unattended -stdout -NoShaderWorker -NoSplash -DDC=RiveLiteOffline "-LocalDataCachePath=$dir/ddc" "-ProjectDir=$root/" "-UserDir=$dir/user/" "-RiveShaderDir=$root/Shaders" "-Output=$dir/global.bin" "-abslog=$dir/cook.log"
        if ($LASTEXITCODE -ne 0 -or !(Test-Path "$dir/global.bin")) { throw "Native cooker failed: $flavor" }
    }
} finally { [Environment]::SetEnvironmentVariable('UE-LocalDataCachePath',$oldCache) }
