# Windows Rive-only build

The Windows target uses the existing Rive UE RHI/RDG adapter with Vulkan SM5.
`RiveRhiLite` remains `WITH_ENGINE=0`, `WITH_VERSE_VM=0`, and `WITH_VERSE_COMPILER=0`.
The native UE cooker and reference are separate development targets. They are
never dependencies of the default target and are excluded from deployment.
Windows UMG/Verse packages and CPU-only Windows rendering are not qualified by
this workflow. Linux CPU validation remains a separate result.

## Prerequisites and isolated toolchain

Use the pinned engine and Rive source/dependencies described in the root README,
Python 3.12+, .NET 10, Windows SDK 10.0.26100.0, and MSBuild 18 with the v145
platform targets. The compiler itself is installed inside this prototype:

```powershell
python scripts/install_windows_msvc.py
python scripts/prepare_windows.py --with-tools --fetch-dependencies
python scripts/build_native_windows.py
./scripts/build_windows.ps1
```

The installer downloads the Microsoft VSIX payloads listed in
`scripts/windows-msvc-manifest.json`, checks each SHA-256, and extracts the x64
toolchain under `dependencies/windows-msvc/AutoSDK`. The actual compiler is
14.50.35731 (the servicing directory retains the 14.50.35717 name). UBT's
minimum-version and banned-version checks remain enabled. No global Visual
Studio registration, PATH, or SDK setting is changed. `build_windows.ps1` sets
AutoSDK and native-library paths only for its invocation and restores them.
The toolchain is a build dependency, not part of the runtime package.

Patch 0009 fixes a Windows monolithic Program exit-order defect in the pinned
UE6 span-allocator statistics registry. Global renderer owners unregister after
the function-static registry would already have been destroyed. A process-lived
registry keeps those final unregister calls valid; runtime statistics and render
algorithms remain unchanged. This affects the Engine-linked development tools,
not the Engine-free Lite target. The Windows CLI-only capability/rejection paths
also avoid CoreUObject static teardown without bootstrap initialization.

Native Rive compilation exports the pinned source to `build/windows`, uses its
upstream Python shader generator with MSVC string embedding, and verifies all
36 generated UE shader texts against the tracked adapter. The Rive standalone
D3D shader generation step is not needed by `--for_unreal`; no native D3D,
Skia, or native Rive Vulkan backend replaces UE RHI/RDG. Linux generated headers
and libraries are preserved. `/utf-8` prevents system-code-page-dependent C++
compilation failures.

## Independent shader cooking and comparison

```powershell
./scripts/build_windows.ps1 -Target RiveUeShaderCooker
./scripts/build_windows.ps1 -Target RiveUeReference
./scripts/cook_windows.ps1 -Output "$PWD/artifacts/windows/cook-new"
python scripts/verify_windows.py --lite-shaders artifacts/windows/cook-new/lite/global.bin --reference-shaders artifacts/windows/cook-new/reference/global.bin --output artifacts/windows/verify-new
python scripts/audit_windows_boundary.py
python scripts/package_windows.py --shader-archive artifacts/windows/cook-new/lite/global.bin --output package/windows-new
./package/windows-new/render.ps1 -Output "$PWD/artifacts/windows/package.png"
```

The two cooks use separate DDC and output directories. Verification requires
successful UE RHI/RDG capture markers, no asserts/ensures, and exact RGBA PNG
comparison. It records the actual adapter, process peak working set and first
image time. Separate process runs can share OS/driver caches; these are not
cold-machine startup measurements.

The boundary audit reads the actual PE executable, UBT receipt, MSVC linker
response, and compile definitions. Windows also links the UE `WindowsD3D`
platform utility module; it does not link D3D11RHI/D3D12RHI, Engine, Renderer,
UMG, Slate, or optional Verse modules. The package follows the receipt, includes
app-local CRT DLLs and cooked shaders, and excludes source, SDK, PDB, cooker,
and reference executables. Package acceptance additionally requires a fresh
extraction run with the development engine/vendor unavailable.

The pinned Windows Core module unconditionally includes the external `libpas`
allocator library. Unlike the Linux default, Windows therefore has this baseline
library in its link response even with both Verse VM/compiler definitions zero.
It is not evidence that the optional Verse worker has been enabled.

## Verified results (2026-10-26)

The preview.3 follow-up encountered `VK_ERROR_INITIALIZATION_FAILED` during
device creation. Disabling async compute passed the five native comparisons,
but the final extracted-package repeat still failed on its third process.
It was insufficient as a stability fix.

A separate Vulkan 1.1 API probe with no enabled device extensions repeated
three cases three times: one graphics queue succeeded; all 16 graphics queues
succeeded; 16 graphics plus 8 compute queues failed each time with result -3.
The pinned `FVulkanQueue` constructor only obtains queue index zero, while
device creation requested every queue advertised by the selected families.

Patch `0010-vulkan-offscreen-single-queue.patch` adds an explicit
`-VulkanSingleQueue` option gated by `-RenderOffscreen`. It requests one queue
per selected family and sizes/fills the matching priority arrays. Without
these flags the original behavior is retained. The Windows launcher and both
comparison hosts use that flag together with `-DisableAsyncCompute`.
Both actual Windows targets rebuilt, and all five static/animation/state-machine
comparisons passed again. Rive's shaders and RHI/RDG rendering algorithm were
not changed. This qualifies the selected offscreen path, not every driver.
See [queue validation](windows-queue-validation.json); final extracted-package
acceptance is recorded separately with the release.

The figures below describe the earlier Windows package; preview.3's final
archive sizes, hashes and extracted-package verification are reported with
that release.

See [windows-validation.json](windows-validation.json) for hashes and measured
results. All five exact RGBA8 comparisons passed: bankcard, Bounce at 0 and
0.25 seconds, and trigger state machine at 0 and 0.5 seconds. Both dynamic
fixtures also changed pixels between their initial and advanced states.
Each independent native cooker submitted and completed 11,469 jobs, using
separate fresh DDC and archive paths, and exited normally. This reference is
the Engine-linked offscreen FRenderTarget host, not an Editor viewport or UEFN.

The actual release ZIP is 24,594,292 bytes (23.46 MiB); unpacked files including
the manifest total 62,879,541 bytes (59.97 MiB). Its 57 extracted files all match
the staged hashes. With development engine/vendor renamed out of reach and
PATH restricted to System32, three packaged runs and the public PowerShell
launcher matched the native reference exactly. Capability discovery reports
Rive enabled / UMG disabled; attempting UMG exits with code 9.

On Windows 11 build 26100 with NVIDIA RTX 5080, packaged first-image times were
1,936.087 / 878.641 / 958.475 ms and peak working sets were
406,151,168 / 406,323,200 / 406,974,464 bytes. OS/driver caches may be warm.
Touching Main.cpp without changing its content triggered one compilation and
relink: 15.39 seconds wall time (12.90 seconds UBT). A subsequent unchanged
build took 3.81 seconds wall time (1.30 seconds UBT). These are incremental,
not cold-build measurements. The existing Linux script test suite passed all
23 tests under WSL; Linux loader-specific tests are not a native Windows suite.

To reproduce archive acceptance, ZIP the fresh package (including the empty
Engine/Shaders directory), extract it into a fresh directory in this prototype,
then run the following after all builds/cooks finish. The verifier temporarily
renames this prototype's engine/vendor directories and restores them in a
finally block; do not run concurrent development tools against those paths.

```powershell
python scripts/verify_windows_package.py --package package/windows-extracted --reference artifacts/windows/verify-new/bankcard-RiveUeReference.png --output artifacts/windows/package-verify-new
```

Only the Windows x64 Rive-only Vulkan package is qualified. A Vulkan driver is
still required. CPU-only Windows, Windows UMG/Verse and macOS binaries remain
unverified. The release tag retains its earlier source revision; its Windows
asset report and release notes identify the newer Windows source commit.
