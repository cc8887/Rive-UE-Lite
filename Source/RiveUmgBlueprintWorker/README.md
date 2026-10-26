# Source UMG Blueprint worker

Texture/Image authoring is available through `texture import/read`, `Image` in
WidgetTree specifications and Image/Border `brush` patches. PNG/JPEG imports are
saved as native source Texture2D assets; exports include direct brush texture
dependencies and can be reimported as a ZIP. See [texture workflow and scope](../../prototype/widget-textures.md).

Native animations are also available through `animation list/create/patch` and
`preview --animation ...`. See [animation implementation and measurements](../../prototype/umg-animation.md).
The older static figures below are historical snapshots, not animation metrics
or the current complete deployment package size.

Current user entry: `python scripts/widget_bp.py` (`create`, `read`, `import`,
`patch`, `preview`, `export`). Windows forwards to WSL Ubuntu. Build explicitly
with `sudo bash scripts/build_ui.sh --with-widget-blueprint`. See
[the authoring workflow](../../prototype/widget-blueprint-authoring.md).
Creation accepts `-Spec=` for a custom typed WidgetTree, including Button.
Patching reads existing source assets and accepts the documented typed widget
properties. Graph/pin snapshots and member variables are readable; this entry
does not edit graph nodes/links. The fixed fixture and measurements below are
historical scoped evidence, not qualification of arbitrary project assets.

This separate Editor-capable Program implements a source-asset round trip. The
default `scripts/build_ui.sh` still selects `RiveRhiLite`; `--with-umg` still
selects the existing runtime `RiveUmgHost`. Neither selects this authoring worker.

The worker uses native `UWidgetBlueprint`, `FKismetEditorUtilities`, the UE
Blueprint compilation manager, `UPackage::SavePackage`, and `LoadObject`. It
preserves an **uncooked `.uasset`**, including its editable WidgetTree. Preview
instantiates the saved `UWidgetBlueprintGeneratedClass`, then uses the real
`FWidgetRenderer` / Slate RHI renderer on CPU Vulkan. No JSON tree reconstruction
is used to display the Blueprint.

`create` authors a small test asset using the same native Blueprint factory APIs
used by UE's widget editor subsystem. `patch`, `inspect`, and `render` load a
source Blueprint from the selected content mount. `patch` accepts typed text,
font/color, visibility/opacity/enabled/variable properties and Canvas slot layout.
It validates the complete request before
modifying any objects, compiles natively, and saves the source package.

## Build and native shader cook

All commands run from this independent prototype. WSL distro: Ubuntu. Root is
needed for the private build/render mount namespaces; actual programs run as
uid/gid 1000. Building this worker is explicit and includes UnrealEd/UMGEditor;
the native editing tool is larger than either runtime host.

```sh
sudo bash scripts/build_linux_cached.sh RiveUmgBlueprintWorker \
  -NoDebugInfo -NoDumpSyms -NoMutex -MaxParallelActions=8 \
  -Log="$PWD/artifacts/umg-blueprint/build-new.log"

sudo bash scripts/build_linux_cached.sh RiveUeShaderCooker \
  -NoDumpSyms -NoMutex -MaxParallelActions=2 \
  -Log="$PWD/artifacts/umg-blueprint/build-cooker-new.log"

# Choose fresh output directories for both independent native invocations.
RIVE_LITE_CANONICAL_DDC="$PWD/artifacts/umg-blueprint/shaders-host-new/ddc" \
  bash Source/RiveUeShaderCooker/cook_linux.sh \
  "$PWD/artifacts/umg-blueprint/shaders-host-new/global.bin" \
  "$PWD/artifacts/umg-blueprint/shaders-host-new/provenance" \
  "$PWD/artifacts/umg-blueprint/build-cooker-new.log" \
  -IncludeSlate -SlateOnly -EditorShaders

RIVE_LITE_CANONICAL_DDC="$PWD/artifacts/umg-blueprint/shaders-reference-new/ddc" \
  bash Source/RiveUeShaderCooker/cook_linux.sh \
  "$PWD/artifacts/umg-blueprint/shaders-reference-new/global.bin" \
  "$PWD/artifacts/umg-blueprint/shaders-reference-new/provenance" \
  "$PWD/artifacts/umg-blueprint/build-cooker-new.log" \
  -IncludeSlate -SlateOnly -EditorShaders
```

Only the new shader flags select a Slate/RenderCore archive for `LinuxEditor`.
The existing Rive/UMG runtime cooks retain their original defaults. The worker
does not link Rive shader types, so its archive deliberately excludes Rive shader
sections. Source/compile provenance is recorded by the existing native cooker
harness. Each completed Editor archive contains 160 permutations, 261,515 bytes.

## Repeat the full round trip

```sh
sudo bash scripts/measure_no_gpu.sh -- \
  python3 scripts/verify_umg_blueprint_roundtrip.py \
  --host-archive artifacts/umg-blueprint/shaders-host-new/global.bin \
  --reference-archive artifacts/umg-blueprint/shaders-reference-new/global.bin \
  --output-dir artifacts/umg-blueprint/roundtrip-new --cpu-limit 2
```

The verifier creates an actual source WBP and a backup, previews the disk asset,
patches it, saves, and previews it in two fresh processes. Independently authored
expected assets use native typed setters for their initial properties. Reference
captures use UE's `DuplicateAndInitializeFromWidgetTree` source-tree preview API
(also used in `UWidgetBlueprint::DetectSlateWidgetLeaks`), while normal captures
instantiate the compiled class. Both use unchanged native Slate drawing. The
strict comparator checks RGBA including alpha, actual arranged geometry, text,
unmodified widgets, distinct process IDs, CPU adapter identity, errors, and
independent shader-cook provenance. It records peak RSS and first-PNG time.

This is an offscreen native UE UMG comparison, **not a complete Editor viewport**.
The fixture covers native CanvasPanel, Border and TextBlock with Engine fonts,
640 x 400, DPI 1, static layout. Rive's existing RHI/RDG route is preserved in
the other targets; this asset fixture does not embed Rive. Custom project widget
classes, arbitrary graph execution, UI materials and other asset dependencies
need their own qualification.

## Use an existing source Blueprint

Mount the folder containing its `Content` at `/Game/` and use the package name,
without `.uasset` or an object suffix. Stage its actual assets/classes in this
isolated worker environment. Use an asset copy for a job, then return its saved
`.uasset` to the client.

```json
{
  "widgets": [
    {"name": "Title", "text": "Saved Blueprint preview", "position": [84, 44], "size": [440, 52]},
    {"name": "Badge", "position": [96, 266], "size": [240, 42]}
  ]
}
```

```sh
WORKER="$PWD/Binaries/Linux/RiveUmgBlueprintWorker"
CONTENT="$PWD/job/Content"
# These authoring modes initialize native NullRHI and null Slate, and do not draw.
"$WORKER" -unattended -stdout -Mode=inspect -ProjectDir="$PWD/" \
  -ContentDir="$CONTENT" -Asset=/Game/UI/WBP_RoundTrip -Metadata="$PWD/job/before.json"
"$WORKER" -unattended -stdout -Mode=patch -ProjectDir="$PWD/" \
  -ContentDir="$CONTENT" -Asset=/Game/UI/WBP_RoundTrip \
  -Patch="$PWD/job/patch.json" -Metadata="$PWD/job/saved.json"

# Rendering always initializes the real Vulkan RHI and real Slate RHI renderer.
sudo bash scripts/measure_no_gpu.sh -- env \
  VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json \
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  "$WORKER" -unattended -stdout -vulkan -sm5 -AllowCPUDevices \
  -AllowCommandletRendering -RenderOffscreen -norhithread \
  -Mode=render -ProjectDir="$PWD/" -ContentDir="$CONTENT" \
  -Asset=/Game/UI/WBP_RoundTrip \
  -ShaderArchive="$PWD/artifacts/umg-blueprint/shaders-host-new/global.bin" \
  -Output="$PWD/job/preview.png" -Metadata="$PWD/job/preview.json"
```

The final verifier output contains `WBP_RoundTrip-edited.zip`, with the saved
source `.uasset`, the exact patch, and the pinned engine revision. Asset version
compatibility must match the receiving UE project.

## Evidence status

Completed qualification: `artifacts/umg-blueprint/roundtrip-03/summary.json`.
All nine independent processes exited successfully, without runtime errors or
ensures. Both before/after captures match the independently authored native UE
source-tree reference exactly; a second fresh reload also matches exactly.
All three full RGBA comparisons have zero differing pixels. The edit itself
changes 16,887 pixels. Native text and arranged position/size match the patch;
the nested label follows its Border parent. Readonly previews leave the source
asset hashes unchanged. All top-level Slate window counts are zero.

| Actual single-run observations, 2 CPU affinity / 2 Mesa threads | Result |
| --- | ---: |
| Worker ELF without debug information (not a packaged deployment closure) | 568.68 MiB |
| Compiled-class preview peak RSS, three fresh processes | 701.58–717.21 MiB |
| Compiled-class first complete PNG, three fresh Mesa caches | 12.82–13.45 s |
| Native source-tree reference first complete PNG | 12.44–12.47 s |
| Load, patch, native compile, save and full process exit | 4.53 s |
| Patch process peak RSS | 446.56 MiB |
| Saved source `.uasset` | 23,268 bytes |
| Download ZIP with source asset, patch and engine pin | 5,339 bytes |

These are WSL2/Ubuntu Development Program observations on the local host with
process affinity, not a dedicated cloud VM, continuous frame-rate, cold C++
build, or a complete worker package benchmark. Source creation/patching uses
NullRHI only for native non-rendering asset resources; every screenshot asserts
`using_null_rhi=false`, selects llvmpipe, and runs with `/dev/dxg` and `/dev/dri`
absent. Each reference and host archive has its own native cook process/cache.

Download: `artifacts/umg-blueprint/roundtrip-03/WBP_RoundTrip-edited.zip`.
Screenshots: `04-load-original/output.png`, `07-reload-edited/output.png` and
`08-native-edited/output.png` under that run directory.

The final worker build is `artifacts/umg-blueprint/build-09.log`. The first target
build required 910 planned actions; failed integration attempts and warmed
caches mean its development logs are not a controlled cold-build benchmark.
The native core bootstrap commits shader parameter layouts before RHI init,
initializes the Editor shader hash cache, loads EditorStyle/PropertyEditor before
source-BP regeneration, drains asynchronous config futures before task workers,
and shuts down the native shader symbol exporter before event-pool teardown.
No Engine source or default assets were replaced to pass these checks.
