param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ToolArguments)
$ErrorActionPreference='Stop'
$linuxRoot=& wsl.exe -d Ubuntu --exec wslpath -u $PSScriptRoot.Replace('\','/')
if ($LASTEXITCODE -ne 0) { throw 'The complete toolkit requires WSL Ubuntu' }
$converted=@()
$pathFlags=@('--workspace','--toolkit','--input','--output','--spec','--patch','--content-dir','--scenario','--source','--controller','--playback-script','--shader-archive')
for ($i=0; $i -lt $ToolArguments.Count; $i++) {
    $value=$ToolArguments[$i]
    $parts=$value -split '=',2
    $key=$parts[0]
    if ($pathFlags -contains $key -and ($parts.Count -eq 2 -or $i+1 -lt $ToolArguments.Count)) {
        $pathValue=if ($parts.Count -eq 2) { $parts[1] } else { $i++; $ToolArguments[$i] }
        $isWindowsAbsolute=$pathValue -match '^[A-Za-z]:[\\/]|^\\\\'
        if ($isWindowsAbsolute -or (($key -in @('--workspace','--toolkit')) -and !$pathValue.StartsWith('/'))) {
            $absolute=[IO.Path]::GetFullPath($pathValue)
            $pathValue=& wsl.exe -d Ubuntu --exec wslpath -u $absolute.Replace('\','/')
        }
        # Command-relative paths are resolved by the Linux CLI against workspace.
        $converted+=$key; $converted+=$pathValue
    } else { $converted+=$value }
}
& wsl.exe -d Ubuntu --cd $linuxRoot --exec bash "$linuxRoot/rive-tool" @converted
exit $LASTEXITCODE
