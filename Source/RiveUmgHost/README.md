# Optional native UMG host

One project, two separately cached runtime Targets:

```sh
# Run at the prototype root. The build wrapper uses a private mount namespace
# as root, then runs UBT as uid 1000. It never changes the original UE project.
sudo bash scripts/build_ui.sh
sudo bash scripts/build_ui.sh --with-umg
bash scripts/build_ui.sh --plan
bash scripts/build_ui.sh --with-umg --plan
```

The default selects `RiveRhiLite` only. It does not build the reference, native
Engine cooker, UMG bridge, or Slate. `--with-umg` first verifies/materializes the
pinned Slate content, then selects `RiveUmgHost`. It does not automatically cook
or rebuild the reference during ordinary C++ iteration.

The normal build prerequisites and isolated SDK/source cache remain those of
this prototype. `scripts/build_linux_cached.sh` carries the selected cache root
across its privilege drop. This experiment's default cache is
`/home/yuchencui/.cache/rive-ue-lite-20261024`.

## UI and runtime selection

The demo is a real `UCanvasPanel`, a `UBorder`, a native `UButton`, and
`UNativeWidgetHost` children for labels and Rive. Labels use a pinned, file-backed
Roboto font. A custom Slate element draws Rive directly into Slate's live RDG
output texture, using its original UE renderer, preserving the render target and
clipping to the allotted region. There is no PNG/CPU raster substitute for Rive.

`RiveUmgHost` links `RiveLiteRenderer`; the independent `RiveUeReference` links
`RiveUeReferenceRenderer`. They share the demo layout/playback specification and
native UMG bridge, and never link both Rive renderer copies into one process.
The reference remains a real UE Engine Program, not an Editor viewport.

```sh
Binaries/Linux/RiveRhiLite -Capabilities  # rive=true, umg=false
Binaries/Linux/RiveUmgHost -Capabilities # rive=true, umg=true
# The Lite executable rejects -Ui=umg with exit 9 and UMG_NOT_COMPILED.
```

The enhanced launcher defaults to `-Ui=umg`; pass `-Ui=rive` to draw Rive directly.
The enhanced executable/package keeps its Engine/UMG cost in either mode. It does
not dynamically load UMG into a WITH_ENGINE=0 process.

```sh
bash package/ui-umg-02/render.sh package/ui-umg-02/fixtures/input.riv /tmp/umg.png
bash package/ui-umg-02/render.sh package/ui-umg-02/fixtures/input.riv /tmp/rive.png -Ui=rive
```

The pinned build uses `UE_WITH_CONSTINIT_UOBJECT=0`. Before opening Slate, the
bridge uses UE6's existing `SetPreCreateCompiledInClassDefaultObjects(false)` and
`ProcessNewlyLoadedUObjects()` startup APIs to fully register reflected properties
without eagerly constructing every Engine CDO. Required CDOs/config objects are
still real and constructed on demand. Module UObject processing is then enabled.
No Engine source, default assets, config-error gates or filesystem APIs are
replaced for this path. A guarded constinit startup branch is present but has not
been runtime-qualified in this configuration.

## Native shader cook and package

The previous Lite archive stays separate. An explicit native cook adds the 43
Slate shader types / 51 permutations needed by the selected global shader family.
Each completed UMG archive contains 11,520 permutations. UI materials and source
Widget Blueprint compilation are outside this demo.

```sh
# Explicit tooling setup; this is not part of the default build_ui path.
sudo bash scripts/build_linux_cached.sh RiveUeShaderCooker \
  -Log="$PWD/artifacts/umg-optional/cooker-build-new.log"

# Run the cooker as an ordinary user; always choose fresh output/evidence paths.
RIVE_LITE_CANONICAL_DDC="$PWD/artifacts/umg-optional/shaders-new/ddc" \
  bash Source/RiveUeShaderCooker/cook_linux.sh \
  "$PWD/artifacts/umg-optional/shaders-new/global.bin" \
  "$PWD/artifacts/umg-optional/shaders-new/provenance" \
  "$PWD/artifacts/umg-optional/cooker-build-new.log" -IncludeSlate

python3 scripts/package_linux.py --with-umg \
  --receipt Binaries/Linux/RiveUmgHost.target \
  --shader-archive artifacts/umg-optional/shaders-host/global.bin \
  --fixture fixtures/bankcard.riv --playback-manifest fixtures/playback/scenarios.json \
  --output package/ui-umg-new
```

For the default package, omit `--with-umg`, select `RiveRhiLite.target`, and use
the Lite archive. The packager rejects a receipt/flag mismatch and rejects
UMG/Slate content in a Lite receipt. It stages actual receipt dependencies,
excludes debug symbols/SDK/editor tools, and uses a flavor-specific launcher.
Always use new package/evidence directories; existing deliveries are not deleted.

Completed UMG delivery: `package/ui-umg-02`. Completed Lite delivery:
`package/ui-rive-01`. Both require a system CPU Vulkan ICD and its system-library
closure, which are counted separately from the application package.

## Repeatable verification

```sh
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/measure_optional_umg.py \
  --package package/ui-umg-02 \
  --native-archive artifacts/umg-optional/shaders-reference/global.bin \
  --output-dir artifacts/umg-optional/matrix-new --cpu-limit 2

sudo python3 scripts/measure_ui_incremental.py \
  --output-dir artifacts/umg-optional/incremental-rive-new
sudo python3 scripts/measure_ui_incremental.py --with-umg \
  --output-dir artifacts/umg-optional/incremental-umg-new

python3 scripts/audit_optional_umg.py --package package/ui-rive-01 \
  --output artifacts/umg-optional/lite-exclusion-new.json
```

The capture runner checks selected CPU-device logs, native widget class names,
normal exit, complete PNG, no runtime errors/ensures, exact RGBA/alpha comparison,
and matching playback metadata. It also requires animation/state-machine changes
and an actual image difference when hiding Rive. Each side uses an independently
generated archive and its own fresh Mesa cache. CPU capture affinity and Mesa
threads are both set to 2; build parallelism is measured separately.

The incremental runner invalidates exactly one Main.cpp via mtime, verifies that
one actual compile and one Link ran, and restores the original timestamp without
changing source bytes. The full Link includes linker, Breakpad symbol processing,
and strip/debug separation. It is not a cold-build or statistical benchmark.

The matrix validates six selected worldless Program screenshots, not continuous
frame rate, UMG Designer, arbitrary Widget Blueprints, gameplay/world-dependent
bindings, UI materials, IME, or a full interactive editor.

Results and source/command identities are collected under
`artifacts/umg-optional/`; failed integration runs are preserved there as well.
