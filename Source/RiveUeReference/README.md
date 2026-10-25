# UE Engine Program offscreen reference

This target links the real UE `Engine` and `Renderer` modules. It is an offscreen
Engine Program reference for Rive's UE RHI/RDG output. It does not claim to be an
Editor viewport, UMG Designer preview, Slate composite or final game screenshot.

The reference adapter retains upstream `UTexture`, `UTextureRenderTarget2D` and
`FRenderTarget` wrappers. The default capture creates a real Engine
`FRenderTarget` subclass backed by an RHI texture. It overrides texture/size
accessors and inherits Engine's original RDG accessor. The target is passed
through upstream `makeRenderTarget(FRenderTarget*)`. Add `-UTextureTarget` for
the stronger path that creates a genuine `UTextureRenderTarget2D`, initializes
its Engine resource and uses that Engine render target instead. Both paths use
upstream 2D flush and RDG pass implementations with the lite adapter's hashes.
GPU Canvas/Ore is explicitly unavailable in both adapters for this experiment.

Bootstrap follows the current UE6 LowLevelTestsRunner Core/CoreUObject
initialization order, then explicitly loads Engine/Renderer and initializes a
real RHI. It never calls `FEngineLoop::PreInit`, `UEngine::Init`, creates a World,
installs filesystem stubs, replaces default assets or registers missing packages
as known missing. The host registers the normal UE monolithic Program module and
globals directly, without instantiating `FEngineLoop` or including
`LaunchEngineLoop.cpp`. The default target does not explicitly request all Engine CDOs
through `ProcessNewlyLoadedUObjects`; `-UTextureTarget` requests the full UObject
initialization branch. Any implicit CDO construction during Engine/Renderer
startup is still real. Genuine Engine default assets/configuration remain
required wherever requested; a resulting failure is a failed reference capture,
not parity evidence.

Default comparison conditions: the same static `.riv` bytes, default artboard,
512 by 512 RGBA8, one sample, no SRGB flag, transparent clear, contain/center,
`Seconds=0`, `SetLinearToGamma(false)`, and the same PNG encode route as lite.
Select the shader archive explicitly and use the unchanged `Shaders` directory.
Shader class names/source paths remain unchanged. The archive must actually load
and the process must finish a real draw and PNG output.

Sharing that archive tests the effect of removing Engine/Renderer while using
the same shader bytecode. It does not independently validate that the helper's
minimal SM5 compilation environment matches UE's canonical cook environment.
The canonical public APIs `FGlobalShaderTypeCompiler::BeginCompileShader` and
`GlobalBeginCompileShader` are gated by `WITH_EDITOR` in
`Runtime/Engine/Public/ShaderCompiler.h`; the environment implementation in
`Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp` is gated as well.
This `WITH_EDITOR=0` capture target cannot call those APIs to produce an
independent canonical archive. The separate `RiveUeShaderCooker` Program builds
that native `WITH_EDITOR=1` Engine path without launching an editor UI. It cooks
the selected Rive and RenderCore utility domain, including real Engine View
metadata and target-platform configuration; it does not cook a full Editor
project or material library. See `../RiveUeShaderCooker/README.md` for its exact
scope and isolation patches. Actual successful cooking and paired screenshots
remain separate gates.

Both capture hosts now use `RivePlayback/Public/RivePlayback.h` for named native
animation/state-machine playback. Pass `-Scenario=/absolute/case.json` and
`-PlaybackMetadata=/absolute/frame.json`. Each screenshot replays from zero,
using identical fixed deltas and timestamped inputs. Metadata records the actual
runtime selection, calls and states. `fixtures/playback/scenarios.json` defines
the finite five-case dynamic suite. The independent matrix also retains the
original five static fixtures and same-time no-events controls.

Example after an actual successful build:

```sh
RiveUeReference -vulkan -RenderOffscreen -AllowCPUDevices -unattended \
  -ProjectDir=/path/to/Rive-UE-Lite/ \
  -Input=/path/to/static.riv -Output=/path/to/ue-reference.png \
  -ShaderDirectory=/path/to/Rive-UE-Lite/Shaders \
  -ShaderArchive=/path/to/native-global-shaders.bin -Width=512 -Height=512 -Seconds=0
```

The full Engine graph includes physics, networking, audio codecs and Slate even
though this program does not run gameplay. It also includes Renderer runtime
data such as `Engine/Content/Renderer/TessellationTable.bin`. Missing SDKs,
libraries, cooked defaults or shader types must be reported as blocked gates.
Source staging alone does not establish that this executable builds or renders.

The final `integration-02` run has now built and captured five pinned fixtures
on llvmpipe with `/dev/dxg` and `/dev/dri` hidden. All five Engine Program runs
exited 0, and all five corresponding lite PNGs matched every decoded RGBA byte
including alpha. See `../../artifacts/captures/integration-02/reference-captures.json`
and `comparison-five-fixtures.json` in the same directory for hashes, device
evidence and content statistics. `clip_tests` is fully transparent at the default
initial state and does not establish visible clipping coverage; `circle_clips`
provides a nonempty clipped shape. These runs use the default Engine
`FRenderTarget` path. The optional `-UTextureTarget` mode is implemented but is
outside this validated five-fixture scope.

The current independent result is
`artifacts/playback-independent-02/review-summary.json`: 60 fresh processes,
30 exact full-RGBA/alpha pairs, five static fixtures, 19 animation/state-machine
keyframes and six same-time no-events controls. All runtime playback metadata,
CPU/no-GPU evidence and frozen-input hashes passed. Both hosts use separate
fresh Mesa cache directories and their own actually cooked archives:
`artifacts/shaders-independent-lite-02/global.bin` for Lite and
`artifacts/shaders-canonical/full-01/global.bin` for this reference. Their
11,360 Rive type/permutation identities are equal; archive bytes and hashes differ.

The first independent run is retained as `playback-independent-01`: bankcard
exposed the Lite compiler's missing `COMPILER_DXC` identity. Rive uses that
macro to select the front-face convention for signed feather coverage. Only
the Lite compiler environment was corrected; this reference executable,
native cooker environment and native archive remained unchanged. The focused
regression and then the complete fresh 60-capture matrix passed at zero tolerance.
The historical shared-archive static result above remains a separate baseline.
These finite offscreen results do not establish Editor/UMG, hardware-GPU or
whole-library equivalence. Reproduce with `scripts/measure_playback_README.md`.
