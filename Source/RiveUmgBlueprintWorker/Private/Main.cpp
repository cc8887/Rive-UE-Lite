// Native UE source-asset worker; deliberately separate from the runtime hosts.
#include "CoreMinimal.h"
#include "Async/TaskGraphInterfaces.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Blueprint/WidgetTree.h"
#include "Slate/WidgetRenderer.h"
#include "BlueprintCompilationManager.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "DeviceProfiles/DeviceProfileManager.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "GlobalShader.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformOutputDevices.h"
#include "HAL/PlatformTLS.h"
#include "IImageWrapperModule.h"
#include "ImageCore.h"
#include "Internationalization/EnginePackageLocalizationCache.h"
#include "Internationalization/PackageLocalizationManager.h"
#include "IO/IoDispatcher.h"
#include "Interfaces/ISlateRHIRendererModule.h"
#include "Interfaces/ISlateNullRendererModule.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "KismetCompiler.h"
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
#include "BlueprintAssets.inl"
#include "BlueprintCapture.inl"

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    const double Started = FPlatformTime::Seconds();
    FTaskTagScope Scope(ETaskTag::EGameThread);
    FCommandLine::Set(*FCommandLine::BuildFromArgV(nullptr, ArgC, ArgV, nullptr));
    FString Mode, ContentDir, Asset, PatchPath, Output, MetadataPath, ShaderArchive, ProjectDirectory;
    FParse::Value(FCommandLine::Get(), TEXT("Mode="), Mode);
    FParse::Value(FCommandLine::Get(), TEXT("ContentDir="), ContentDir);
    FParse::Value(FCommandLine::Get(), TEXT("Asset="), Asset);
    FParse::Value(FCommandLine::Get(), TEXT("Patch="), PatchPath);
    FParse::Value(FCommandLine::Get(), TEXT("Output="), Output);
    FParse::Value(FCommandLine::Get(), TEXT("Metadata="), MetadataPath);
    FParse::Value(FCommandLine::Get(), TEXT("ShaderArchive="), ShaderArchive);
    FParse::Value(FCommandLine::Get(), TEXT("ProjectDir="), ProjectDirectory);
    if ((Mode != TEXT("create") && Mode != TEXT("patch") && Mode != TEXT("render") && Mode != TEXT("inspect")) ||
        ContentDir.IsEmpty() || !Asset.StartsWith(TEXT("/Game/")) || Asset.Contains(TEXT("..")) ||
        (Mode == TEXT("patch") && PatchPath.IsEmpty()) ||
        (Mode == TEXT("render") && (Output.IsEmpty() || ShaderArchive.IsEmpty()))) return 2;
    if (!ProjectDirectory.IsEmpty())
    {
        FPaths::SetProjectFilePath(ProjectDirectory / TEXT("RiveRhiLite.uproject"));
        FPlatformMisc::SetOverrideProjectDir(*FPaths::ConvertRelativePathToFull(ProjectDirectory));
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
        RequestEngineExit(TEXT("UMG Blueprint worker complete"));
        // Editor shader setup owns event-backed symbol exporters. Release them
        // before native event pools are torn down (not at C++ static shutdown).
        if (GMaxRHIShaderPlatform < SP_NumPlatforms)
            FShaderSymbolExport::Shutdown(LegacyShaderPlatformToShaderFormat(GMaxRHIShaderPlatform));
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
        FBlueprintCompilationManager::Shutdown();
        FCoreDelegates::OnPreExit.Broadcast();
        FCoreDelegates::OnExit.Broadcast();
        IPackageResourceManager::Shutdown();
        FIoDispatcher::Shutdown();
        FModuleManager::Get().UnloadModulesAtShutdown();
        // Editor config loading uses asynchronous platform futures. Drain them
        // while their task workers still exist; otherwise a short job can wait
        // forever in ConfigCacheIni::Exit after the pools have been destroyed.
        if (GConfig) GConfig->Exit();
        for (FQueuedThreadPool* Pool : {GThreadPool, GIOThreadPool, GBackgroundPriorityThreadPool})
            if (Pool) Pool->Destroy();
#if STATS
        FThreadStats::StopThread();
#endif
        FTaskGraphInterface::Shutdown();
        FPlatformApplicationMisc::TearDown();
        FPlatformMisc::PlatformTearDown();
        if (GConfig) { delete GConfig; GConfig = nullptr; }
        if (GLog) GLog->TearDown();
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
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_WORKER_READY mode=%ls content=%ls", *Mode, *ContentDir);
    UWidgetBlueprint* Blueprint = nullptr;
    if (Mode == TEXT("create"))
    {
        Blueprint = CreateFixture(Asset, FParse::Param(FCommandLine::Get(), TEXT("ModifiedFixture")));
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
    }
    TSharedRef<FJsonObject> Metadata = DescribeBlueprint(Blueprint, nullptr);
    if (Mode == TEXT("render"))
    {
        if (!RenderBlueprint(Blueprint, Output, {640, 400}, Metadata)) return 7;
    }
    Metadata->SetStringField(TEXT("mode"), Mode);
    Metadata->SetNumberField(TEXT("elapsed_ms"), (FPlatformTime::Seconds() - Started) * 1000.0);
    Metadata->SetNumberField(TEXT("pid"), FPlatformProcess::GetCurrentProcessId());
    if (!MetadataPath.IsEmpty() && !WriteJson(MetadataPath, Metadata)) return 8;
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_COMPLETE mode=%ls elapsed_ms=%.3f",
        *Mode, (FPlatformTime::Seconds() - Started) * 1000.0);
    return 0;
}
