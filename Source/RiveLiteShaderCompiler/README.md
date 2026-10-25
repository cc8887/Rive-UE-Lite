# Offline shader compiler

This build-time tool compiles the existing Rive UE global shader types and the
RenderCore utility shaders required by the standalone RHI/RDG renderer. It links
neither `Engine` nor `Renderer`. It uses `WITH_EDITOR=1` because UE keeps shader
type compilation callbacks behind that define. The rendering executable remains
`WITH_EDITOR=0` and consumes the produced cooked archive.

The generated View/InstancedView shader declarations and stereo source generator
come from the exact engine source commit. They are needed by `Common.ush`, which
RenderCore fullscreen, texture-copy and clear shaders still include. They do not
implement a world, renderer, game engine or scene. The extraction records source
hashes in `Private/Generated/provenance.json`.
The OneColor utility family also includes non-NDC vertex permutations that use
`DrawRectangleParameters`. Its three-vector data declaration is extracted from
the pinned `SceneFilterRendering.h`; its Renderer implementation is not copied
or linked. The ordinary NDC clear used by Rive remains unchanged.

The isolated engine applies four compiler patches in `prototype/patches`:
`0003` omits Turnkey's deployment/editor graph for no-Engine
tools, `0004` makes the existing ZIP writer available under `WITH_EDITOR` (as the
ZIP reader and shader symbol exporter already are), and `0005` excludes the
upstream stb preprocessor's standalone benchmark/demo/test programs from the
ShaderPreprocessor module. None changes shader preprocessing or rendering code.
Those three preserve the existing code behavior. `0006` fixes a pinned UE6
preprocessor defect: newlines preserved in
macro arguments must be removed at the edges of `##` operands. The unchanged
Rive `ATTR` macro otherwise produces `ATTRIBUTE` and `3` as separate tokens.
`-MacroRegression` reproduces that case and a paste with newlines on both sides;
the baseline fails, the patch passes, and the same source passes Clang's standard
C preprocessor. Rive shader text and rendering algorithms stay unchanged.

Prepare source after updating the isolated engine:

```sh
python3 Source/RiveLiteShaderCompiler/generate_shader_support.py --engine engine
python3 Source/RiveLiteRenderer/generate_native_shaders.py
```

Build the `RiveLiteShaderCompiler` Program target with the same pinned engine and
native Rive library as the runtime. Register this module and Target with the same
isolated project/source staging mechanism used for `RiveRhiLite`.

```sh
python3 scripts/prepare_runtime_cache.py
sudo bash scripts/build_linux_cached.sh RiveLiteShaderCompiler
python3 prototype/patches/validate_patches.py
```

On the Windows workspace, run `prepare_runtime_cache.py` with Windows Python;
the Linux cached-build wrapper uses the separately prepared ext4 Runtime cache.

Run on Linux without a display or GPU:

```sh
bash Source/RiveLiteShaderCompiler/compile_linux.sh \
  /absolute/path/to/Rive-UE-Lite/package/GlobalShaderCache-VULKAN_SM5_LINUX.bin
```

The wrapper supplies the pinned ShaderConductor library directory, display-free
SDL configuration, and optional fatal-signal diagnostics. The generated Rive
headers, shader files, and native library must all use the upstream Unreal
`--raw_shaders`/`--human-readable` option, which preserves the uniform names
shared with UE's generated uniform-buffer metadata.

The runtime must load the archive for `SP_VULKAN_SM5_LINUX`. The shader compiler
uses `Linux` cooked target layout and embeds code in the archive, so the target
machine needs neither the compiler nor shader source files.
Stage the project's `Config/DefaultGame.ini`, which sets
`[/Script/UnrealEd.ProjectPackagingSettings] bShareMaterialShaderCode=False`.
That setting makes `LoadFromGlobalArchive` consume the embedded SPIR-V instead
of trying to open a separate shared `Global` shader-code library.

`-ListOnly` writes a manifest of selected types/permutations without compiling.
`-Limit=N` limits an investigation; reaching the limit marks the run incomplete
and does not publish an archive. `-AllRegistered` expands selection to every
registered global shader for diagnosis; some of these may require additional
offline Engine shader declarations and are outside the initial renderer scope.
`-Type=<exact C++ shader type>` is an explicit diagnostic subset, recorded in the
manifest. A failed compile writes the unstripped preprocessed source next to the
requested archive. `-MacroRegression` writes its independent source, preprocessed
result and JSON outcome without compiling or publishing a shader archive.

The tool does not change upstream shader entrypoints, Rive's draw algorithm, or
its C++ permutation callbacks. Its common compiler input is a focused SM5
environment instead of Engine's entire scene/material environment. Compilation,
archive loading, and UE image comparison are separate validation gates. This
implementation is not screenshot parity evidence until all three have run.

Successful compile jobs are cached in the isolated Linux cache by UE's
`FShaderCompileJob::GetInputHash()`, including the preprocessed source, complete
compilation dependencies, shader target, root-parameter layout signature, UE
shader-cache GUID and shader-format version. Each
record carries a BLAKE3 checksum and its input hash; missing, truncated, stale or
corrupt records trigger a real compile. The wrapper defaults to
`$HOME/.cache/rive-ue-lite/shader-jobs`; override it with
`RIVE_LITE_SHADER_JOB_CACHE`. Cache contents are disposable and are not part of
the runtime package. Each manifest records cache hits separately from compiles.
This experiment uses one pinned engine/compiler revision. The native UE key is
not a hash of the compiler executable or entire Git tree; discard this cache
when changing compiler implementations without advancing their format version,
or when changing the cached-output serialization schema.

The helper explicitly runs the `ShaderTypesReady` delayed registration phase
before freezing shader maps. That phase initializes the memory-layout type
hashes required by cooked serialization. It registers the shader-symbol CVars
with the pinned Engine defaults (symbols disabled), then shuts down the symbol
exporter and I/O dispatcher before the Core event pools are destroyed. These
are build-time bootstrap/lifetime steps, without an Engine module dependency.

Verified separately: `artifacts/setup/shader-compiler-freeze-smoke-03.log` exits
normally after cooking `FNULLPS`; its manifest records one cache hit and a
1,099-byte archive. `artifacts/setup/archive-runtime-load-02.log` records the
`WITH_EDITOR=0` runtime loading that archive through the actual Vulkan RHI.
The intentionally missing Rive input then returns code 4. This diagnostic proves
cooked-layout compatibility and shutdown, not Rive rendering or visual parity.

The earlier full selected domain was exported successfully with process exit 0:
`artifacts/shaders/RiveGlobalShaderCache-VULKAN_SM5_LINUX.bin`, 17,147,039 bytes,
SHA-256 `a252df0dd066ebbb06f754617dceaa38a4f75bb95c184d8dacb45a45e96d3d2d`.
Its manifest records 11,468 selected permutations, no type filter, 9,893 cache
hits, and 61.46 seconds in the compile/export stage. This includes all 50
supported permutations from `OneColorShader.usf`, required by the actual RDG
clear path exercised by clipping and blending fixtures. Equal native input hashes
reuse compiled output across permutations; this does not omit shader-map entries
or reduce the selected domain. The other 1,575 jobs invoked DXC.
See `artifacts/setup/shader-compiler-full-05.log` and the
adjacent archive manifest. These times describe the build-time compiler, not
rendering or time to the first image.

The later independent invocation is recorded in
`artifacts/shaders-independent-lite-01/provenance.json`. It created a new
`global.bin` with the same 17,147,039 bytes and SHA-256, into a previously absent
output, and exited 0. All 11,468 jobs hit this helper's own recorded input-hash
cache. This is a separate cook execution, not a claim that those jobs all reran
DXC. The Engine cooker uses a different program, output and canonical DDC;
the paired screenshot report must establish the resulting pixel equivalence.

The first independent native-Engine comparison (`artifacts/playback-independent-01`)
found 29 of 30 capture pairs exactly equal, with a bankcard feathering difference.
The lite helper had omitted `COMPILER_DXC`, although its Vulkan backend actually
uses DXC. UE's native compiler sets it to 1. Rive uses this macro to interpret
front-facing triangles in the feather atlas: leaving it at the default 0 reverses
signed fill coverage, which is later clamped to [0,1]. This affects feathered fills
without changing the atlas-stroke path. The preserved old compiler and source are
in `artifacts/playback/diagnostics/lite-compiler-before-dxc-02`; the first cook and
comparison reports remain unchanged.

The only C++ correction declares `COMPILER_DXC=1` in `SetupInput`. No Rive shader,
rendering algorithm, host or native-Engine compiler input was changed. The new
build `artifacts/setup/shader-compiler-parity-02.log` succeeded. Its independent
full cook exited 0 in 72.323 seconds and produced
`artifacts/shaders-independent-lite-02/global.bin`: 17,147,055 bytes, SHA-256
`6764c197931e00d62f51c95cf1e9a7c545c85eaff8f983719d80968633fe9176`.
All 11,468 permutations are present; 9,889 jobs hit the recorded input-hash cache
and 1,579 invoked DXC. The adjacent `provenance.json` records actual execution
`9ccd7e40-7690-4db4-a7eb-7ce2c2ed1360`, the new compiler and all source hashes.
`cook_independent_linux.sh` reproduces the provenance-wrapped invocation into a
new archive and evidence directory.

The focused paired run
`artifacts/playback/diagnostics/bankcard-dxc-03/summary.json` passed its six
captures with the corrected lite archive and unchanged native archive/runtime
hosts. Bankcard now has zero differing RGBA or alpha pixels and identical PNG
hashes. Bounce at 0 and 0.25 seconds also matches exactly. This confirms the
feathering correction for that focused scope; it does not replace the complete
60-capture independent comparison.

Pinned UE source interfaces used:

- `RenderCore/Public/ShaderCompilerCore.h`: public preprocessing/compilation.
- `RenderCore/Public/ShaderCompilerJobTypes.h`: compile job and key.
- `RenderCore/Public/GlobalShader.h`: permutation selection and archive.
- `Core/Public/Serialization/MemoryLayout.h:44`: delayed type-layout registration.
- `RenderCore/Internal/ShaderSymbolExport.h`: explicit cook shutdown.
- `RenderCore/Private/ShaderParameters.cpp`: generated uniform buffer includes.
- `Engine/Private/ShaderCompiler/ShaderCompilerEditor.cpp:80-175`: source pattern
  for global shader preparation and constructing a compiled shader.
- `Engine/Private/ShaderCompiler/ShaderCompiler.cpp:3133-3319`: source-only stereo
  generator extraction.
- `Engine/Private/ShaderCompiler/ShaderCompiler.cpp:5460-5515`: cooked archive
  export pattern; exact line positions follow the pinned engine revision.
