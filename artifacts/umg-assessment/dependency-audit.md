# UMG dependency assessment on the pinned UE6 source

This is a source audit, not an additional UMG build, deployable package measurement, or rendered UMG acceptance. The existing RiveUeReference binary already links UMG and its runtime dependency family; do not add its Engine cost a second time when estimating an incremental change to that reference host. The material difference is between RiveRhiLite and the Engine-backed reference host.

## Three different scopes

| Scope | Source requirements | What can stay out of the deployment host |
|---|---|---|
| Native UWidget tree, offscreen capture, Rive custom Slate element | UMG, Engine, Renderer, Slate/SlateCore, SlateRHIRenderer, normal UMG runtime dependencies, native UObject/class registration, Slate startup | Play session, game viewport, full UWorld for the selected simple widget path; UMGEditor/Designer; source Blueprint compiler |
| Run an already cooked Widget Blueprint | The same runtime family plus actual cooked generated class, widget tree, bytecode, referenced fonts/textures/materials and their shader maps | UMGEditor, UnrealEd and Blueprint authoring/compiler tools, if all assets have been cooked elsewhere |
| Accept/edit/recompile source Widget Blueprints or run the UMG Designer on the server | UMGEditor, Kismet compiler integration, UnrealEd and broad editor framework dependencies | A stock UMGEditor module cannot be reduced to runtime UMG by setting WITH_EDITOR=0 |

## Native UMG has unconditional runtime dependencies

- `engine/Engine/Source/Runtime/UMG/UMG.Build.cs:9-24` adds Engine, CoreUObject, AssetRegistry, Slate, SlateCore, RHI, RenderCore, ApplicationCore and others.
- `UMG.Build.cs:26-29,50-65` adds Renderer and SlateRHIRenderer for non-Server targets. A headless Program remains non-Server.
- `UMG.Build.cs:31-40` unconditionally adds MovieScene, MovieSceneTracks, TimeManagement, PropertyPath, HTTP and FieldNotification. There is no stock rule here that removes MovieScene when the application only uses Rive animation.
- `engine/Engine/Source/Runtime/MovieScene/MovieScene.Build.cs:18-28` includes Engine, SlateCore, TimeManagement and UniversalObjectLocator.
- `engine/Engine/Source/Runtime/MovieSceneTracks/MovieSceneTracks.Build.cs:9-27` includes AnimationCore, Constraints, AudioMixer and AnimGraphRuntime in addition to Engine and MovieScene. Their presence in rules is not a byte-for-byte estimate of retained code after link-time garbage collection.
- `engine/Engine/Source/Runtime/SlateRHIRenderer/SlateRHIRenderer.Build.cs:9-29` requires SlateBaseRenderer plus Engine, Renderer, Slate/SlateCore, RHI, RenderCore, ImageCore, HeadMountedDisplay and PreLoadScreen.
- `engine/Engine/Source/Runtime/Engine/Engine.Build.cs:232-261` already declares UMG, MovieScene/Tracks, SlateRHIRenderer and other by-name modules. The dedicated native shader cooker flag clears that by-name list at lines 448-455; it is not a general UMG runtime optimization.

`TargetType.Server` is not an escape hatch for screenshots: `UMG/Private/Slate/WidgetRenderer.cpp:217-273` compiles the actual offscreen paint and renderer submission only under `!UE_SERVER`. Its constructor only creates the Slate 3D renderer under that same condition at lines 28-33.

## A selected native UMG path does not require Play/UWorld

There is explicit source support for a worldless tree; this still needs execution tests in the prototype:

- `UMG/Private/UserWidget.cpp:2848-2856`: the official `CreateWidgetInstance(UWidgetTree&)` overload calls `CreateInstanceInternal` with null World and LocalPlayer when its tree has no UUserWidget outer.
- `UserWidget.cpp:2898-2954`: World teardown checks are conditional on World; Outer must exist; construction is NewObject followed by Initialize, with player context only when LocalPlayer exists.
- `UserWidget.cpp:139-179`: Initialize accepts the native-class path, creates a transient WidgetTree, and only runs NativeOnInitialized when a player context or the Blueprint's explicit no-context opt-in permits it. A worldless host must not assume normal gameplay lifecycle callbacks run automatically.
- `UMG/Private/Components/Widget.cpp:967-1104`: TakeWidget builds/caches the Slate widget through RebuildWidget, wraps a UUserWidget for GC, then synchronizes properties. It does not unconditionally create or require a UWorld in this route.
- `UMG/Private/Slate/WidgetRenderer.cpp:102-134,208-273`: DrawWidget/DrawWindow accept `FRenderTarget*`, create a virtual window, prepass, paint and submit to Slate. The host can supply an RHI render-target wrapper instead of using the convenience overload that creates UTextureRenderTarget2D at lines 81-96.
- `Slate/Public/Framework/Application/SlateApplication.h:316-318` exposes InitializeAsStandaloneApplication, including an explicit GenericApplication overload. The actual platform renderer/application selection, font service, default styles, resource loading, threading, input and teardown remain integration work.

This proves an available source route, not that every UUserWidget, Blueprint graph, timer, viewport query or world-dependent binding will work without UWorld or UEngine. Keep those features as explicit host capabilities.

There are concrete limits when GEngine is null:

- `SlateRHIRenderer/Private/SlateRHIRenderingPolicy.cpp:1259-1265` explicitly skips material render batches without GEngine. A worldless basic panel/text/Rive proof must not be presented as UI-material support.
- `UMG/Private/WidgetLayoutLibrary.cpp:87-109` GetViewportScale dereferences GEngine at line 95; the original Rive mouse handlers call this function. Its descriptor defaults bScaleLayoutByDPI=false (`Rive/Public/Rive/RiveDescriptor.h:47`), so paint can avoid that DPI branch, but pointer handling still needs an explicit host DPI path or a real Engine object.
- `SlateRHIRenderer/Private/SlateRHIResourceManager.cpp:600-615` has a legacy path-loaded UTexture brush fallback that accesses GEngine->DefaultTexture when the asset is missing. Resource path closure must be validated; missing-asset fallback is not safely covered by a null-Engine host.
- `SlateRHIRenderer/Private/SlateRHIRenderingPolicy.cpp:1656` has an explicit 2.2 gamma fallback without GEngine; matching the reference still requires an intentional gamma policy and screenshot tests.

## Cooked Blueprint runtime versus the compiler

- `UMG/Public/Blueprint/WidgetBlueprintGeneratedClass.h:8,80,121-131` defines the runtime class as an Engine UBlueprintGeneratedClass and retains its widget tree and animations.
- `UMG/Private/WidgetBlueprintGeneratedClass.cpp:192-318,330-354` implements runtime tree instancing, bindings and animation binding. These functions are in the Runtime/UMG module, not UMGEditor.
- `UMG/Public/Animation/WidgetAnimation.h:8,25,143` derives UWidgetAnimation from UMovieSceneSequence and owns a UMovieScene. Removing MovieScene while preserving normal UMG animation is not a Build.cs-only change.
- `Editor/UMGEditor/UMGEditor.Build.cs:12-72` brings Sequencer, ContentBrowser, AssetTools, EditorFramework, UnrealEd, Kismet, GraphEditor, BlueprintGraph, PropertyEditor and many other editor modules.
- `Editor/UMGEditor/Private/UMGEditorModule.cpp:134-149` registers its widget compiler with KismetCompiler and registers the UWidgetBlueprint compiler implementation.
- `Editor/UMGEditor/Private/WidgetBlueprintCompiler.cpp:252-258` constructs FWidgetBlueprintCompilerContext and compiles the asset. A source Widget Blueprint edit is an asset/bytecode compilation, not automatically a C++ compile/link.

Thus a thin server that only loads cooked Widget Blueprints should not ship UMGEditor. A service that receives source `.uasset` Blueprints and recompiles them must retain a compatible editor-side worker or extract a genuine compiler service; calling a runtime tree builder a Blueprint compiler would overstate compatibility.

## Rive's native widget route and optional work

- Original plugin `F:/Github/rive-unreal/Source/Rive/Public/UMG/RiveWidget.h:27` derives URiveWidget from UUserWidget.
- `Rive/Private/UMG/RiveWidget.cpp:45-56` rebuilds as SRiveLeafWidget. Its mouse routes use UWidgetLayoutLibrary viewport scaling, e.g. lines 78-83; a worldless host needs explicit DPI/input policy rather than assuming a game viewport.
- `Rive/Private/Slate/SRiveLeafWidget.cpp:48-107` supplies an ICustomSlateElement; lines 374-407 submit it via FSlateDrawElement::MakeCustom; lines 193-303 draw/replay the artboard and flush the original RHI/RDG context into Slate's output texture.
- `SlateRHIRenderer/Private/SlateRHIRenderingPolicy.cpp:2052-2074` invokes that custom element with the live FRDGBuilder and actual output texture, so an offscreen Slate host can retain Rive's current rendering algorithm.
- Original `Rive/Rive.Build.cs:25-40` includes AudioMixer. For a no-audio prototype, a new narrow wrapper using the already extracted Rive library/renderer avoids importing the whole original gameplay/plugin module. Actual API compatibility must then be stated at that wrapper's scope.
- `Rive/Public/Rive/RiveArtboard.h:33` derives URiveArtboard from FTickableGameObject, and `Rive/Private/Rive/RiveArtboard.cpp:487-500` advances the state machine in Tick. A standalone Program must explicitly drive the intended native tick/command submission lifecycle; linking the class does not advance it.

Practical optional capabilities are audio, UMG MovieScene animation, arbitrary Blueprint graph/gameplay access, UI-domain materials, world-space WidgetComponent, editor design surface and text/font coverage. Stock UMG's rule-level MovieScene/Audio dependencies will remain until actual source/UHT/API surgery removes them, even if an application never calls them.

## Shaders and staged data are separate from the ELF

- `Slate/Slate.Build.cs:51-68` stages Engine Content/Slate TTF/PNG/SVG/TPS files and project Content/Slate when bUsesSlate is enabled. The current reference target has bUsesSlate=false, so its executable size does not demonstrate a complete usable UMG data package.
- `SlateCore/SlateCore.Build.cs:33-51` includes FreeType when enabled, ICU when enabled, and HarfBuzz/Nanosvg for non-Server targets. Smaller text scope and disabling ICU have a functionality cost; fonts and Unicode coverage must be measured separately.
- `SlateRHIRenderer/Private/SlateShaders.cpp:17-72` registers Slate vertex, masking, element/font/rounded-box and other global shader variants.
- `SlateRHIRenderer/Private/SlateMaterialShader.cpp:31,50,111-132` registers UI-domain material shader types in addition to the global shader family.
- The current native cooker only selects Rive and eight utility source files in `Source/RiveUeShaderCooker/Private/Main.cpp:73-89`. None of the normal Slate shader source files are selected. Its existing archive is not sufficient evidence for a working UMG renderer. A scoped UMG host must independently cook its additional global shader family and each actually used UI material, then test the full composition/alpha/clipping/gamma/input path against native UE.

## Source scale, not build-action or time measurements

`rg --files` on the pinned source found the following physical `.cpp` counts. Unity merging, generated code, preprocessor flags and dependency reuse change the actual compile action count:

| Module | Source .cpp files |
|---|---:|
| UMG | 156 |
| Slate | 205 |
| SlateCore | 134 |
| SlateRHIRenderer | 22 |
| MovieScene | 211 |
| MovieSceneTracks | 198 |

These six modules total 926 physical C++ translation-unit source files; this is neither 926 incremental actions nor a linear multiplier for wall time. In the existing Engine-backed reference these modules have already been compiled/linked, so a wrapper `.cpp` edit reuses them unless its headers, target definitions or build configuration invalidate the cache. Updating a Widget Blueprint or a data-driven UI can avoid native relinking entirely, but the Blueprint worker/render host costs remain separate.

Recommended next measurement is a native UMG tree with one Panel, TextBlock, Button and the Rive custom element, using the existing Engine-backed reference build cache. Measure stripped ELF and staged assets, a complete independently cooked shader archive, peak render RSS, fresh build versus leaf `.cpp` edit versus Blueprint-only compile, and finally exact CPU-only screenshot comparisons. Until then, the reference size is a linkage anchor, not a tested UMG deployment minimum.
