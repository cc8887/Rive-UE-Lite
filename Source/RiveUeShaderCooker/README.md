# Independent native Engine shader cook

This is a separate `WITH_ENGINE=1`, `WITH_EDITOR=1` Program. It selects the
existing Rive shader types and the same unchanged RenderCore utility family as
the lite compiler, then calls the real Engine path:

`FGlobalShaderTypeCompiler::BeginCompileShader` → `GlobalBeginCompileShader` →
`FShaderCompilingManager::SubmitJobs` / `FinishCompilation` →
`SaveGlobalShaderFile`.

It does not load a lite archive, copy `SetupInput`, reproduce Engine's compiler
environment in local code, or inject generated View/InstancedView declarations.
The real Engine/Renderer modules register those structures. The native shader
type initialization discovers uniform-buffer references, and Engine generates
its stereo/autogen includes and applies its original compilation settings.
The Linux target platform determines the cooked layout and permutation flags.
The global `ALLOW_OTHER_PLATFORM_CONFIG=1` override enables Core's original
cross-platform configuration API, as in the native `UnrealAssetStringify` Program;
it is applied to every module so the console/config interfaces share one layout.
`bBuildDeveloperTools=false` remains: the tool needs that Core API and the
`WITH_EDITOR` shader compiler, without adding the unrelated developer-tool graph.

The Core bootstrap comes from the prototype's independently built Engine
reference, with native Editor startup ordering from `LaunchEngineLoop.cpp`;
the extraction, native reference and output hashes are recorded beside
`Private/CanonicalBootstrap.inl`. It sets commandlet/cook flags, starts an actual
NullRHI and runs native `RenderUtilsInit`. Before shader compilation it also runs
native project/scalability/device-profile CVar initialization, constructs the
registered constinit UObject types and creates the real Editor asset thread pool.
NullRHI is only used during offline
compilation, and supplies no rendering evidence. The tool creates no World and
does not launch an Editor UI. It compiles a selected global-shader domain, not
the entire UE global map, materials, plugins or an Editor project cook.

`UE_RIVE_STANDALONE_SHADER_COOKER=1` isolates optional by-name Engine authoring /
gameplay modules, Slate reflector, Turnkey and source-control asset tools. Small
non-shader editor integrations are guarded separately: network test worlds,
editor viewport initialization, PIE startup, animation Blueprint actions,
packed-level asset creation, audio asset fixups and texture asset conversions.
Unused editor test headers and an AssetTools progress label are also excluded.
The scene ray-tracing instance sink is not registered for this offline target:
its Landscape grass CVar belongs to an omitted world module. No substitute CVar
is registered; native shader preparation does not read that grass setting.
Unsupported authoring calls retain their existing fallback or report unavailable.
Those changes preserve UObject field layouts and
the default behavior of other targets. Engine's shader preparation, compilation
environment, native result processing and archive serializer remain unchanged.
The shared UE preprocessor token-paste repair remains explicit in patch `0006`.

Build only after the pinned dependencies and native Rive library are prepared:

```sh
python3 Source/RiveUeShaderCooker/prepare_bootstrap.py
sudo bash Source/RiveUeShaderCooker/build_linux.sh
```

On this Windows/WSL workspace, update the Runtime cache manifest with Windows
Python first: `python scripts/prepare_runtime_cache.py`. The cached-build wrapper
is run as WSL root to create its private mount namespace, then drops privileges.

An independent cook requires a new output file and a fresh evidence directory:

```sh
bash Source/RiveUeShaderCooker/cook_linux.sh \
  "$PWD/artifacts/shaders-canonical/full-01/global.bin" \
  "$PWD/artifacts/shaders-canonical/full-01/provenance" \
  "$PWD/artifacts/setup/canonical-cooker-build-07.log"
```

Use the actual final successful build log. `-Type=FNULLPS` explicitly requests a
single diagnostic shader; omit it for the complete selected domain. The wrapper
directly invokes the compiler through `measure_cook_provenance.py`, preserving
its command, executable/source/output hashes, actual exit status and log. It uses
`-noshaderworker` to run native compilation in process and the original
`-DDC=(Local)` filesystem graph under the isolated `canonical-ddc` cache. Neither
`-NoShaderCompile` nor `-PrecompiledShadersOnly` is used.

The archive manifest records the selected/submitted count, target layout,
entrypoints, native first-Rive compiler flags/environment hash and a separate
defines CSV. It stays incomplete until all selected shaders are present and the
native archive save succeeds. Acceptance also requires process exit 0; an output
file alone does not establish a successful cook or image parity. Compare the
result using distinct lite/canonical archives and the actual renderer captures.

The recorded full run is `artifacts/shaders-canonical/full-01`. Repeat the command
with a different run directory because the runner rejects an existing archive.
The actual build `canonical-cooker-build-07.log` succeeded, and the independent
full cook exited 0 after 137.753 seconds. Its complete, unfiltered manifest
records 11,469 selected, submitted and successful jobs, zero failed jobs, and
11,360 Rive permutations. The remaining jobs are the selected utility family;
this does not mean that the entire UE global shader map was cooked.

| Recorded artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Binaries/Linux/RiveUeShaderCooker` | 186,055,344 | `5b9e06d0b4adfaad552bcd0fd2e4a23743b3d4d61fcc7b7f24f759e7a3322b37` |
| `artifacts/shaders-canonical/full-01/global.bin` | 7,082,186 | `64e87e74218e9dfe1e23ed0c268ec47d2bbb6fc7a71b0cbcd710d26c4138aa0e` |

The build-side compiler is not part of the lite deployment package. Its actual
input/output hashes, native environment summary and process log are in
`full-01/provenance/provenance.json`, `full-01/global.bin.manifest.json` and
`full-01/provenance/cook.log`. Execution ID:
`7465ea0b-86fe-49dd-a788-e90565fd076d`. This proves an independent native cook;
rendered parity requires the separate paired-capture results.
