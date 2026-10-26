// Native UE source-asset worker; deliberately separate from the runtime hosts.
#include "CoreMinimal.h"
#include "Algo/AllOf.h"
#include "Async/TaskGraphInterfaces.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Blueprint/WidgetTree.h"
#include "Animation/WidgetAnimation.h"
#include "Animation/WidgetAnimationHandle.h"
#include "Animation/WidgetAnimationState.h"
#include "Animation/UMGSequenceTickManager.h"
#include "Animation/MovieScene2DTransformTrack.h"
#include "Animation/MovieScene2DTransformSection.h"
#include "Engine/GameEngine.h"
#include "MovieScene.h"
#include "MovieSceneBinding.h"
#include "Channels/MovieSceneChannelProxy.h"
#include "Tracks/MovieSceneFloatTrack.h"
#include "Sections/MovieSceneFloatSection.h"
#include "Tracks/MovieSceneBoolTrack.h"
#include "Sections/MovieSceneBoolSection.h"
#include "Compilation/MovieSceneCompiledDataManager.h"
#include "Evaluation/MovieSceneEvaluationField.h"
#include "Evaluation/MovieSceneEvaluationState.h"
#include "EntitySystem/MovieSceneEntitySystemLinker.h"
#include "EntitySystem/MovieSceneEntitySystemRunner.h"
#include "EntitySystem/MovieSceneEntitySystem.h"
#include "UObject/UObjectHash.h"
#include "HAL/IConsoleManager.h"
#include "Slate/WidgetRenderer.h"
#include "BlueprintCompilationManager.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "Components/Image.h"
#include "Engine/Texture2D.h"
#include "TextureCompiler.h"
#include "DerivedDataCache.h"
#include "DerivedDataBuild.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "DeviceProfiles/DeviceProfileManager.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "DynamicRHI.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "GlobalShader.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformOutputDevices.h"
#include "HAL/PlatformTLS.h"
#include "IImageWrapperModule.h"
#include "IImageWrapper.h"
#include "ImageCore.h"
#include "Internationalization/EnginePackageLocalizationCache.h"
#include "Internationalization/PackageLocalizationManager.h"
#include "IO/IoDispatcher.h"
#include "Interfaces/ISlateRHIRendererModule.h"
#include "Interfaces/ISlateNullRendererModule.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "KismetCompiler.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_ExecutionSequence.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/ConfigUtilities.h"
#include "Misc/CoreMisc.h"
#include "Misc/CoreDelegates.h"
#include "Misc/DelayedAutoRegister.h"
#include "Misc/FileHelper.h"
#include "Misc/OutputDeviceRedirector.h"
#include "Misc/OutputDeviceStdOut.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/QueuedThreadPool.h"
#include "Misc/QueuedThreadPoolWrapper.h"
#include "Misc/ScopeExit.h"
#include "Modules/ModuleManager.h"
#include "PipelineStateCache.h"
#include "RenderResource.h"
#include "RenderingThread.h"
#include "RenderUtils.h"
#include "RHICommandList.h"
#include "Scalability.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/BulkDataRegistry.h"
#include "ShaderCodeLibrary.h"
#include "ShaderParameterMetadata.h"
#include "ShaderSymbolExport.h"
#include "Stats/Stats.h"
#include "Brushes/SlateColorBrush.h"
#include "Styling/UMGCoreStyle.h"
#include "TextureResource.h"
#include "UObject/GCObject.h"
#include "UObject/Package.h"
#include "UObject/PackageResourceManager.h"
#include "UObject/SavePackage.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectBase.h"
#include "UObject/UnrealType.h"
#include "WidgetBlueprint.h"

#if !WITH_ENGINE || !WITH_EDITOR || !IS_PROGRAM || !IS_MONOLITHIC
#error Use the independent monolithic Editor-capable worker target.
#endif
TCHAR GInternalProjectName[64] = TEXT("RiveUmgBlueprintWorker");
IMPLEMENT_FOREIGN_ENGINE_DIR()
IMPLEMENT_SIGNING_KEY_REGISTRATION()
IMPLEMENT_ENCRYPTION_KEY_REGISTRATION()
IMPLEMENT_GAME_MODULE(FDefaultGameModuleImpl, RiveUmgBlueprintWorker)
PER_MODULE_BOILERPLATE
DEFINE_LOG_CATEGORY_STATIC(LogUmgBlueprintWorker, Log, All);
#if UE_ALLOW_ENGINE_STDIO_OUTPUT
static TUniquePtr<FOutputDeviceStdOutput> GWorkerStdOut;
#endif
extern ENGINE_API void InitializeRenderingCVarsCaching();
#include "WorkerBootstrap.inl"
static TArray<TSharedPtr<FJsonValue>> DescribeAnimations(UWidgetBlueprint* Blueprint);
static bool GWorkerTextureObjectsCreated = false;
#include "BlueprintAssets.inl"
#include "BlueprintAnimations.inl"
#include "BlueprintCapture.inl"

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    const double Started = FPlatformTime::Seconds();
    FTaskTagScope Scope(ETaskTag::EGameThread);
    FCommandLine::Set(*FCommandLine::BuildFromArgV(nullptr, ArgC, ArgV, nullptr));
    FString Mode, ContentDir, Asset, PatchPath, SpecPath, Output, MetadataPath, ShaderArchive, ProjectDirectory, InputPath, TextureFilter;
    FParse::Value(FCommandLine::Get(), TEXT("Mode="), Mode);
    FParse::Value(FCommandLine::Get(), TEXT("ContentDir="), ContentDir);
    FParse::Value(FCommandLine::Get(), TEXT("Asset="), Asset);
    FParse::Value(FCommandLine::Get(), TEXT("Patch="), PatchPath);
    FParse::Value(FCommandLine::Get(), TEXT("Spec="), SpecPath);
    FParse::Value(FCommandLine::Get(), TEXT("Output="), Output);
    FParse::Value(FCommandLine::Get(), TEXT("Metadata="), MetadataPath);
    FParse::Value(FCommandLine::Get(), TEXT("ShaderArchive="), ShaderArchive);
    FParse::Value(FCommandLine::Get(), TEXT("ProjectDir="), ProjectDirectory);
    FParse::Value(FCommandLine::Get(), TEXT("Input="), InputPath);
    FParse::Value(FCommandLine::Get(), TEXT("TextureFilter="), TextureFilter);
    int32 Width = 640, Height = 400;
    FParse::Value(FCommandLine::Get(), TEXT("Width="), Width);
    FParse::Value(FCommandLine::Get(), TEXT("Height="), Height);
    const bool AnimationWrite = Mode == TEXT("animation-create") || Mode == TEXT("animation-patch");
    const bool TextureOperation = Mode == TEXT("texture-import") || Mode == TEXT("texture-inspect");
    if ((Mode != TEXT("create") && Mode != TEXT("patch") && Mode != TEXT("render") && Mode != TEXT("inspect") && !AnimationWrite && !TextureOperation) ||
        ContentDir.IsEmpty() || !Asset.StartsWith(TEXT("/Game/")) || Asset.Contains(TEXT("..")) ||
        ((Mode == TEXT("patch") || Mode == TEXT("animation-patch")) && PatchPath.IsEmpty()) ||
        (Mode == TEXT("animation-create") && SpecPath.IsEmpty()) ||
        (Mode == TEXT("texture-import") && InputPath.IsEmpty()) ||
        (Mode == TEXT("render") && (Output.IsEmpty() || ShaderArchive.IsEmpty() ||
            Width < 1 || Width > 4096 || Height < 1 || Height > 4096))) return 2;
    if (!ProjectDirectory.IsEmpty())
    {
        FPaths::SetProjectFilePath(ProjectDirectory / TEXT("RiveRhiLite.uproject"));
        FPlatformMisc::SetOverrideProjectDir(*FPaths::ConvertRelativePathToFull(ProjectDirectory));
    }
    // Reuse the prototype's local-only DDC graph. Each CLI job owns its cache;
    // a packaged preview does not need a Zen service or a writable install.
    FString CacheOption;
    if (!FParse::Value(FCommandLine::Get(), TEXT("DDC="), CacheOption))
        FCommandLine::Append(TEXT(" -DDC=RiveLiteOffline"));
    if (!FParse::Value(FCommandLine::Get(), TEXT("LocalDataCachePath="), CacheOption))
    {
        const FString Cache = MetadataPath.IsEmpty() ? FPaths::ProjectSavedDir() / TEXT("TextureDDC") :
            FPaths::GetPath(MetadataPath) / TEXT("TextureDDC");
        FCommandLine::Append(*FString::Printf(TEXT(" -LocalDataCachePath=\"%ls\""), *Cache));
    }
    BootstrapWorkerCore(Mode != TEXT("render"));
    ContentDir = FPaths::ConvertRelativePathToFull(ContentDir) + TEXT("/");
    FPackageName::RegisterMountPoint(TEXT("/Game/"), ContentDir);
    FUMGCoreStyle::ResetToDefault();
#if UE_WITH_CONSTINIT_UOBJECT
    UE::CoreUObject::ConstructCompiledInObjects();
#else
    SetPreCreateCompiledInClassDefaultObjects(false);
    ProcessNewlyLoadedUObjects();
    FModuleManager::Get().StartProcessingNewlyLoadedObjects();
#endif
    FGCObject::StaticInit();
    bool RendererStarted = false;
    ON_SCOPE_EXIT
    {
        auto TeardownStage = [](const TCHAR* Stage) { FPlatformMisc::LowLevelOutputDebugStringf(TEXT("UMG_BP_TEARDOWN %s\n"), Stage); };
        TeardownStage(TEXT("begin"));
        RequestEngineExit(TEXT("UMG Blueprint worker complete"));
        // Editor shader setup owns event-backed symbol exporters. Release them
        // before native event pools are torn down (not at C++ static shutdown).
        if (GMaxRHIShaderPlatform < SP_NumPlatforms)
            FShaderSymbolExport::Shutdown(LegacyShaderPlatformToShaderFormat(GMaxRHIShaderPlatform));
        if (GWorkerTextureObjectsCreated) FTextureCompilingManager::Get().FinishAllCompilation();
        if (GWorkerAnimationObjectsCreated || GWorkerTextureObjectsCreated)
        {
            TeardownStage(TEXT("animation_gc"));
            CollectGarbage(RF_NoFlags, true);
            if (RendererStarted) FlushRenderingCommands();
        }
        TeardownStage(TEXT("slate"));
        if (FSlateApplication::IsInitialized()) FSlateApplication::Shutdown();
        if (RendererStarted)
        {
            FlushRenderingCommands();
            ShutdownRenderingThread();
            for (int32 Platform = 0; Platform < SP_NumPlatforms; ++Platform)
            {
                delete GGlobalShaderMap[Platform];
                GGlobalShaderMap[Platform] = nullptr;
            }
            FShaderCodeLibrary::Shutdown();
        }
        if (GDynamicRHI)
        {
            FRenderResource::ReleaseRHIForAllResources();
            RHIExit();
        }
        TeardownStage(TEXT("blueprint_compiler"));
        FBlueprintCompilationManager::Shutdown();
        TeardownStage(TEXT("delegates"));
        FCoreDelegates::OnPreExit.Broadcast();
        FCoreDelegates::OnExit.Broadcast();
        IBulkDataRegistry::Shutdown();
        IPackageResourceManager::Shutdown();
        FIoDispatcher::Shutdown();
        TeardownStage(TEXT("modules"));
        FModuleManager::Get().UnloadModulesAtShutdown();
        // Editor config loading uses asynchronous platform futures. Drain them
        // while their task workers still exist; otherwise a short job can wait
        // forever in ConfigCacheIni::Exit after the pools have been destroyed.
        TeardownStage(TEXT("config"));
        if (GConfig) GConfig->Exit();
        TeardownStage(TEXT("pools"));
        for (FQueuedThreadPool* Pool : {GThreadPool, GIOThreadPool, GBackgroundPriorityThreadPool})
            if (Pool) Pool->Destroy();
#if STATS
        FThreadStats::StopThread();
#endif
        TeardownStage(TEXT("taskgraph"));
        FTaskGraphInterface::Shutdown();
        FPlatformApplicationMisc::TearDown();
        FPlatformMisc::PlatformTearDown();
        if (GConfig) { delete GConfig; GConfig = nullptr; }
        if (GLog) GLog->TearDown();
        TeardownStage(TEXT("complete"));
    };
    if (Mode == TEXT("render"))
    {
        if (!InitializeRenderer(ShaderArchive)) return 6;
        RendererStarted = true;
    }
    else
    {
        // Native non-rendering commandlets still initialize NullRHI for asset
        // resources. It is never used to produce or validate a screenshot.
        FShaderParametersMetadataRegistration::CommitAll();
        FShaderTypeRegistration::CommitAll();
        FShaderParametersMetadata::InitializeAllUniformBufferStructs();
        FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreRHIInit);
        RHIInit(false);
        if (!GUsingNullRHI) return 6;
        auto& NullSlate = FModuleManager::LoadModuleChecked<ISlateNullRendererModule>(TEXT("SlateNullRenderer"));
        FSlateApplication::InitializeAsStandaloneApplication(NullSlate.CreateSlateNullRenderer(),
            MakeShared<GenericApplication>(TSharedPtr<ICursor>()));
    }
    // Source Blueprint loading starts UMGEditor natively during regeneration.
    // Its startup expects these normal editor services to already be loaded.
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("EditorStyle"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("PropertyEditor"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("BlueprintGraph"));
    FKismetCompilerContext::RegisterCompilerForBP(UWidgetBlueprint::StaticClass(), &UWidgetBlueprint::GetCompilerForWidgetBP);
    FBlueprintCompilationManager::Initialize();
    // This short-lived Editor Program has no normal editor idle loop. Await
    // platform config futures while modules and task pools are still alive,
    // using Core's public synchronization path before any asset operation.
    FConfigCacheIni::PreInitializePlatformPlugins();
    if (Mode == TEXT("render"))
    {
        // Native texture compilation first touches the cache/build system from
        // worker threads. As in FEngineLoop, initialize both on the game thread.
        UE::DerivedData::GetCache();
        UE::DerivedData::GetBuild();
    }
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_WORKER_READY mode=%ls content=%ls", *Mode, *ContentDir);
    const double ReadyMs = (FPlatformTime::Seconds() - Started) * 1000.0;
    if (TextureOperation)
    {
        UTexture2D* Texture = Mode == TEXT("texture-import") ? ImportTextureAsset(Asset, InputPath,
            !FParse::Param(FCommandLine::Get(), TEXT("LinearTexture")), TextureFilter,
            FParse::Param(FCommandLine::Get(), TEXT("ReplaceTexture")),
            FParse::Param(FCommandLine::Get(), TEXT("DefaultTextureCompression"))) : LoadBrushTexture(Asset);
        if (!Texture) return 5;
        auto Metadata = DescribeTexture(Texture);
        Metadata->SetStringField(TEXT("mode"), Mode);
        Metadata->SetNumberField(TEXT("worker_ready_ms"), ReadyMs);
        Metadata->SetNumberField(TEXT("elapsed_ms"), (FPlatformTime::Seconds() - Started) * 1000.0);
        Metadata->SetNumberField(TEXT("pid"), FPlatformProcess::GetCurrentProcessId());
        if (!MetadataPath.IsEmpty() && !WriteJson(MetadataPath, Metadata)) return 8;
        UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_COMPLETE mode=%ls", *Mode);
        return 0;
    }
    UWidgetBlueprint* Blueprint = nullptr;
    if (Mode == TEXT("create"))
    {
        const FString Filename = FPackageName::LongPackageNameToFilename(Asset, FPackageName::GetAssetPackageExtension());
        if (IFileManager::Get().FileExists(*Filename))
        {
            UE_LOGF(LogUmgBlueprintWorker, Error, "Create refuses existing asset: %ls", *Filename);
            return 3;
        }
        Blueprint = SpecPath.IsEmpty() ? CreateFixture(Asset, FParse::Param(FCommandLine::Get(), TEXT("ModifiedFixture")))
                                      : CreateBlueprintFromSpec(Asset, SpecPath);
        if (!Blueprint || !SaveBlueprint(Blueprint)) return 3;
    }
    else
    {
        const FString ObjectPath = Asset + TEXT(".") + FPackageName::GetLongPackageAssetName(Asset);
        Blueprint = LoadObject<UWidgetBlueprint>(nullptr, *ObjectPath);
        if (!Blueprint || !Blueprint->WidgetTree || !Blueprint->GeneratedClass) return 4;
        UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_LOAD disk=1 asset=%ls class=%ls",
            *Blueprint->GetPathName(), *Blueprint->GetClass()->GetName());
        if (Mode == TEXT("patch") && !PatchBlueprint(Blueprint, PatchPath)) return 5;
        if (AnimationWrite && !WriteBlueprintAnimation(Blueprint,
            Mode == TEXT("animation-create") ? SpecPath : PatchPath, Mode == TEXT("animation-create"))) return 5;
    }
    TSharedRef<FJsonObject> Metadata = DescribeBlueprint(Blueprint, nullptr);
    if (Mode == TEXT("render"))
    {
        if (!RenderBlueprint(Blueprint, Output, {Width, Height}, Metadata)) return 7;
    }
    Metadata->SetStringField(TEXT("mode"), Mode);
    Metadata->SetNumberField(TEXT("worker_ready_ms"), ReadyMs);
    Metadata->SetNumberField(TEXT("elapsed_ms"), (FPlatformTime::Seconds() - Started) * 1000.0);
    Metadata->SetNumberField(TEXT("pid"), FPlatformProcess::GetCurrentProcessId());
    if (!MetadataPath.IsEmpty() && !WriteJson(MetadataPath, Metadata)) return 8;
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_COMPLETE mode=%ls elapsed_ms=%.3f",
        *Mode, (FPlatformTime::Seconds() - Started) * 1000.0);
    return 0;
}
