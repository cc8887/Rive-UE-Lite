param([string]$Output='output.png', [string]$InputFile, [string]$Scenario)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if (!$InputFile) { $InputFile="$root/fixtures/input.riv" }
$extra=@()
if ($Scenario) { $extra += "-Scenario=$([IO.Path]::GetFullPath($Scenario))" }
# This offscreen host uses the graphics queue. Avoid additional async-compute
# queues, which failed vkCreateDevice on the release validation driver.
& "$root/Engine/Binaries/Win64/RiveRhiLite.exe" -vulkan -sm5 -RenderOffscreen -norhithread -DisableAsyncCompute -unattended -stdout -NoSplash "-ProjectDir=$root/" "-Input=$([IO.Path]::GetFullPath($InputFile))" "-Output=$([IO.Path]::GetFullPath($Output))" "-ShaderArchive=$root/shaders/global.bin" "-ShaderDirectory=$root/Engine/Shaders" @extra
exit $LASTEXITCODE
