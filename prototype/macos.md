# macOS adaptation and WSL cross-build evidence

2026-10-26: source adaptation and build/staging commands are present. **No Mac binary has been built or run.** WSL arm64 and x64 UBT attempts stop at Mac SDK validation; a real Rive `src/math/aabb.cpp` cross compile stops at missing target system headers. This is not successful macOS support or a three-platform release.

## Runtime boundary

The default target remains `RiveRhiLite`: `WITH_ENGINE=0`, no UMG/Slate, no new Verse compiler/VM worker. Linux selects VulkanRHI; Mac selects MetalRHI. There is no fallback to Skia, Rive's native Metal renderer or NullRHI. The Rive UE RHI/RDG implementation and tracked shaders are unchanged.

`0008-metalrhi-offscreen-without-engine.patch` isolates MetalRHI's Engine/Slate dependency and guards its Slate window hit-testing and application-scale hooks behind `WITH_ENGINE`. Engine-enabled builds retain those branches. Offscreen texture rendering, command encoding and resource handling are unchanged. This is a source patch awaiting native compilation, not proof that the entire transitive Mac link closure is clean.

The build script requires an actual Mac receipt, binary, linker response and compile definitions to pass `audit_macos_boundary.py`. Missing evidence fails the command. It checks MetalRHI is present and Engine, Renderer, UMG, Slate, SlateCore, VulkanRHI and the optional Verse modules are absent. Packaging binds the receipt and binary hashes to that audit.

The common Rive archive selector chooses `Mac/Mac` for arm64 and `Mac/Intel` for x64. It rejects LFS pointer files and empty directories. The Mac entrypoint additionally verifies all ten required native libraries with `xcrun lipo`. Builds are single-architecture; no universal binary is claimed. Native build outputs and generated headers live in `build/macos`, separate from the Linux vendor libraries/headers. Generated shader strings must match the tracked UE adapter.

## Prerequisites

Use a Mac with Xcode and the same independent pinned UE/Rive source checkouts as the root README. The pinned UE configuration requires macOS deployment target 15.0 and Xcode 26.1.1–27.9.0; these are source requirements, not a tested host matrix. Install Python 3.12+ and the upstream Rive build prerequisites (make, Git and Xcode command-line tools).

`engine/`, `vendor/` and native GitDependencies are not in this repository's source archive. Materialize the pinned source and Mac GitDependencies inside this prototype before building. On a new native Mac engine checkout, Epic's `Setup.sh` supplies those dependencies; do not carry over this Windows experiment's Linux-only `.gitdepsignore` or Windows-path Git alternates. Existing Linux `setup_dependencies.py` deliberately excludes Mac and cannot provision it. No Mac SDK is downloaded by the WSL probe, and no SDK validation is bypassed.

## Native Mac commands

Run from the independent prototype root:

```sh
# Apply the lightweight Metal patch. Optional tool patches are applied later.
python3 scripts/prepare_macos.py

# Build upstream Rive libraries/headers in their own Mac staging tree.
# Upstream builds both arm64 and x64 libraries; UE targets remain single-arch.
python3 scripts/build_native_macos.py

# Default runtime only; no cooker, reference, UMG or Verse target is invoked.
bash scripts/build_ui.sh --platform=macos --arch=arm64
# Intel alternative:
bash scripts/build_ui.sh --platform=macos --arch=x64
```

`--plan` works on Windows/WSL without Xcode. On a Mac, `build_ui.sh` selects macOS automatically. Mac `--with-umg` and `--with-verse` are rejected explicitly because those combinations have not been ported/qualified; existing Linux options are preserved. `build_macos.sh --probe` builds only the RHI clear probe, which is not Rive visual evidence.

The actual compile/link audit defaults to `Binaries/Mac/RiveRhiLite.target` and `Intermediate/Build/Mac/<arch>/RiveRhiLite/Development/RiveRhiLite.rsp`. If the pinned UBT selects another response-file layout, inspect the build log and pass its actual file with `audit_macos_boundary.py --link-response`; do not disable the audit.

## Explicit development tools and Metal verification

These Engine-enabled development tools are separate targets, excluded from the runtime build and package:

```sh
python3 scripts/prepare_macos.py --with-tools
bash scripts/cook_macos.sh arm64 artifacts/macos/cook-arm64
bash scripts/build_macos.sh --arch=arm64 --reference
python3 scripts/verify_macos.py \
  --lite-shaders artifacts/macos/cook-arm64/lite/global.bin \
  --reference-shaders artifacts/macos/cook-arm64/reference/global.bin \
  --output artifacts/macos/compare-arm64
python3 scripts/package_macos.py --arch arm64 \
  --shader-archive artifacts/macos/cook-arm64/lite/global.bin \
  --output package/macos-arm64
bash package/macos-arm64/render.sh fixtures/bankcard.riv artifacts/macos/packaged.png
```

The cooker now selects Mac/METAL_SM5 on a Mac and retains Linux/VULKAN_SM5_LINUX on Linux. Its two invocations use separate output paths, user directories and local DDCs. NullRHI is used **only by the offline cooker**; screenshots use real Metal. Packaging rejects Linux/editor/filtered/failed cook manifests and binds the built runtime to its boundary audit.

Verification currently scripts a static bankcard pair and exact RGBA comparison. `/usr/bin/time -l` output records native RSS in the console log; wall time includes process execution, not a cold-machine or frame-rate benchmark. Package staging does not establish portable runtime closure: run the packaged executable with the development checkout unavailable, check dependent dylibs and compare its PNG before publishing. Signing, notarization, universal slices, animation/state-machine Mac tests and UEFN comparisons remain unverified. Native Metal requires a Metal-capable device; Linux llvmpipe results do not prove CPU-only macOS rendering.

## WSL attempts

The release follow-up also searched Ubuntu, the Podman WSL image cache and the
local development disks. An existing Zig 0.15.2 installation was found at
`${USER_HOME}/zig-0.15.2/zig-x86_64-windows-0.15.2/zig.exe`. Its Darwin support
reports SDK display version 15.5 and provides libc headers/link stubs and a small
set of framework link stubs. It is not a complete Apple platform SDK.

Invoked through WSL interop, that existing Zig compiler **successfully compiled
the real Rive `src/math/aabb.cpp` into an arm64 Mach-O object**. An Objective-C++
probe including `<Metal/Metal.h>` failed because that header is absent.
Actual `RiveRhiLite Mac Development -architecture=arm64` still failed UBT SDK
validation. No SDK checks were bypassed. No UE Mac executable, Metal shader
archive, package size or Mac startup result was produced. The missing SDK is
only the first blocker: full UBT link/tool support, native library closure and
Metal cooking/runtime acceptance also remain to be qualified.

```sh
python3 scripts/probe_macos_cross.py --arch arm64
python3 scripts/probe_macos_cross.py --arch x64
# Optional: point at an existing SDK; this does not configure UBT's Apple SDK.
python3 scripts/probe_macos_cross.py --arch arm64 --sdk /path/to/MacOSX.sdk
# Reuse a previously installed Zig compiler; Windows zig.exe works via WSL interop.
python3 scripts/probe_macos_cross.py --arch arm64 --target RiveRhiLite \
  --zig /path/to/zig.exe --output-dir artifacts/macos/new-zig-probe
```

The probe runs actual UBT (`RiveLiteRhiProbe Mac Development`) and an actual Rive translation unit with a Darwin target triple. It preserves commands, exit codes, timing and errors under `artifacts/macos/cross-<arch>`. An object-only success would still not establish a linked UE program or Metal rendering. Run probes serially with other UBT builds.

The new UE Apple portable toolchain handles distributed compilation of translation units not requiring Apple SDKs. MetalRHI/ApplicationCore require platform SDKs and MacToolChain keeps linking on the Mac. This repository does not patch those requirements away.

## Verified in this environment

- Linux default target rebuilt after the platform-rule changes; actual link still excludes Engine/Renderer/UMG/Slate/SlateCore and optional Verse modules.
- Linux native cooker also rebuilt successfully after adding the conditional Metal platform selection.
- Fresh Linux package rendered with GPU nodes and development engine/vendor hidden; a separately cooked native UE reference produced identical RGBA pixels (`different_pixels=0`). Evidence: `artifacts/macos/linux-regression/report.json`.
- Script guard/metrics tests: 23 passed, including LFS pointers, missing native archives, wrong architectures, foreign/partial shader archives and default build selection.
- The Metal patch applies/reverse-checks against the pinned independent engine. Mac compile, package size, launch/RSS and pixel equivalence remain unverified.
- A preprocessor-only check of the five changed Metal C++/header files preserves Engine-enabled tokens and excludes Slate types from Engine-disabled branches. Includes were removed for this check: it does not validate declarations, linking or Objective-C compilation. Evidence: `artifacts/macos/source-boundary.json`.
