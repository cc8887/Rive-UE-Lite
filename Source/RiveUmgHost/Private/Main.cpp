#include "CoreMinimal.h"
#include "Async/TaskGraphInterfaces.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "DynamicRHI.h"
#include "Engine/TextureRenderTarget2D.h"
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
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/CoreDelegates.h"
#include "Misc/CoreMisc.h"
#include "Misc/DelayedAutoRegister.h"
#include "Misc/FileHelper.h"
#include "Misc/OutputDeviceRedirector.h"
#include "Misc/OutputDeviceStdOut.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/QueuedThreadPool.h"
#include "Misc/ScopeExit.h"
#include "Modules/ModuleManager.h"
#include "PipelineStateCache.h"
#include "RenderGraphBuilder.h"
#include "RenderResource.h"
#include "RenderingThread.h"
#include "RenderUtils.h"
#include "RHICommandList.h"
#include "RiveLiteRenderer.h"
#include "RivePlayback.h"
#include "Serialization/MemoryReader.h"
#include "ShaderCodeLibrary.h"
#include "ShaderCore.h"
#include "ShaderParameterMetadata.h"
#include "Stats/Stats.h"
#include "Styling/UMGCoreStyle.h"
#include "TextureResource.h"
#include "UObject/GCObject.h"
#include "UObject/Package.h"
#include "UObject/PackageResourceManager.h"
#include "UObject/ReferencerFinder.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectGlobals.h"
#include "UObject/UObjectBase.h"
#include "rive/artboard.hpp"
#include "rive/file.hpp"
#include "rive/renderer/rive_renderer.hpp"

// The standard IMPLEMENT_APPLICATION also instantiates FEngineLoop and requires
// including all of LaunchEngineLoop.cpp in a Program. Register the actual UE
// monolithic program/module globals directly; this host owns its core bootstrap.
#if !IS_PROGRAM || !IS_MONOLITHIC
#error RiveUmgHost requires a monolithic Program target.
#endif
TCHAR GInternalProjectName[64] = TEXT("RiveUmgHost");
IMPLEMENT_FOREIGN_ENGINE_DIR()
IMPLEMENT_SIGNING_KEY_REGISTRATION()
IMPLEMENT_ENCRYPTION_KEY_REGISTRATION()
IMPLEMENT_GAME_MODULE(FDefaultGameModuleImpl, RiveUmgHost)
PER_MODULE_BOILERPLATE
DEFINE_LOG_CATEGORY_STATIC(LogRiveUmgHost, Log, All);
#if UE_ALLOW_ENGINE_STDIO_OUTPUT
static TUniquePtr<FOutputDeviceStdOutput> GReferenceStdOut;
#endif

// A real subclass of Engine's FRenderTarget. Its RDG accessor is inherited
// unchanged from Engine and calls this virtual texture accessor. This is an
// offscreen target, not an Editor viewport or a substituted Engine asset.
class FTextureBackedEngineRenderTarget final : public FRenderTarget
{
public:
    explicit FTextureBackedEngineRenderTarget(FTextureRHIRef InTexture)
        : Texture(MoveTemp(InTexture)) {}

    using FRenderTarget::GetRenderTargetTexture;
    const FTextureRHIRef& GetRenderTargetTexture() const override { return Texture; }
    FIntPoint GetSizeXY() const override { return Texture->GetDesc().Extent; }

private:
    FTextureRHIRef Texture;
};

#include "RiveUmgCapture.inl"

static void CreateReferencePool(FQueuedThreadPool*& Pool, int32 Threads, EThreadPriority Priority, const TCHAR* Name)
{
    Pool = FQueuedThreadPool::Allocate();
    verify(Pool->Create(Threads, 128 * 1024, Priority, Name));
}

// Mirrors LowLevelTestsRunner/TestCommon/Initialization.cpp and its Core /
// CoreUObject helpers, using the real filesystem and real Engine defaults.
// No FEngineLoop::PreInit, UEngine::Init, UWorld, file stubs or mock assets.
static void BootstrapReferenceCore(bool InitializeObjects)
{
    GGameThreadId = FPlatformTLS::GetCurrentThreadId();
    GIsGameThreadIdInitialized = true;
    FApp::SetProjectName(TEXT("RiveUmgHost"));
    GIsClient = true;
    GIsServer = false;
    FPlatformMisc::PlatformPreInit();
    FPlatformApplicationMisc::PreInit();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::StartOfEnginePreInit);

    GError = FPlatformApplicationMisc::GetErrorOutputDevice();
    GWarn = FPlatformApplicationMisc::GetFeedbackContext();
    FPlatformOutputDevices::SetupOutputDevices();
#if UE_ALLOW_ENGINE_STDIO_OUTPUT
    GReferenceStdOut = MakeUnique<FOutputDeviceStdOutput>();
    GLog->AddOutputDevice(GReferenceStdOut.Get());
#endif
    if (!FIoDispatcher::IsInitialized())
    {
        const FIoStatus Status = FIoDispatcher::Initialize();
        if (!Status.IsOk())
            UE_LOG(LogRiveUmgHost, Fatal, TEXT("Real I/O dispatcher initialization failed: %s"), *Status.ToString());
    }
    FPlatformFileManager::Get().InitializeNewAsyncIO();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::FileSystemReady);
    FTaskGraphInterface::Startup(4);
    FTaskGraphInterface::Get().AttachToThread(ENamedThreads::GameThread);
    CreateReferencePool(GIOThreadPool, 2, TPri_AboveNormal, TEXT("ReferenceIO"));
    CreateReferencePool(GThreadPool, 4, TPri_SlightlyBelowNormal, TEXT("ReferenceWorkers"));
    CreateReferencePool(GBackgroundPriorityThreadPool, 1, TPri_Lowest, TEXT("ReferenceBackground"));
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::TaskGraphSystemReady);
#if STATS
    FThreadStats::StartThread();
#endif
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::StatSystemReady);
    FConfigCacheIni::InitializeConfigSystem();
    FConfigCacheIni::LoadConsoleVariablesFromINI();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::IniSystemReady);
    FIoDispatcher::InitializePostSettings();
    FPlatformMisc::PlatformInit();
    RegisterModularObjectsProcessing();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("CoreUObject"));
    FCoreDelegates::OnInit.Broadcast();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("Engine"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("Renderer"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RenderCore"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RiveLiteRenderer"));
    FPackageLocalizationManager::Get().InitializeFromLazyCallback([](FPackageLocalizationManager& Manager)
    {
        Manager.InitializeFromCache(MakeShareable(new FEnginePackageLocalizationCache()));
    });
    FPackageName::RegisterShortPackageNamesForUObjectModules();
    IPackageResourceManager::Initialize();
    if (InitializeObjects)
    {
        FUMGCoreStyle::ResetToDefault();
        FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreObjectSystemReady);
        // Only the stronger UTexture mode requests all Engine CDOs explicitly.
        // A genuine/default-asset failure remains a failed baseline. Native
        // module startup may also construct CDOs in raw-target mode; those
        // side effects are left intact and may fail without real assets.
        ProcessNewlyLoadedUObjects();
        FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ObjectSystemReady);
        FModuleManager::Get().StartProcessingNewlyLoadedObjects();
        FGCObject::StaticInit();
        if (GUObjectArray.IsOpenForDisregardForGC()) GUObjectArray.CloseDisregardForGC();
        FReferencerFinder::NotifyRegistrationComplete();
    }
    GIsRunning = true;
}

static bool LoadReferenceShaderArchive(const FString& Path)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path))
    {
        UE_LOG(LogRiveUmgHost, Error, TEXT("Missing compatible Rive/RenderCore shader archive: %s"), *Path);
        return false;
    }
    FShaderCodeLibrary::InitForRuntime(GMaxRHIShaderPlatform);
    FMemoryReader Reader(Bytes);
    GGlobalShaderMap[GMaxRHIShaderPlatform] = new FGlobalShaderMap(GMaxRHIShaderPlatform);
    GGlobalShaderMap[GMaxRHIShaderPlatform]->LoadFromGlobalArchive(Reader);
    if (Reader.IsError()) return false;
    GGlobalShaderMap[GMaxRHIShaderPlatform]->BeginCreateAllShaders();
    return true;
}

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    const double StartSeconds = FPlatformTime::Seconds();
    FTaskTagScope GameThreadScope(ETaskTag::EGameThread);
    FCommandLine::Set(*FCommandLine::BuildFromArgV(nullptr, ArgC, ArgV, nullptr));
    FString Input, Output, ShaderArchive, ShaderDirectory, ProjectDirectory;
    int32 Width = 512, Height = 512;
    float Seconds = 0;
    FParse::Value(FCommandLine::Get(), TEXT("Input="), Input);
    FParse::Value(FCommandLine::Get(), TEXT("Output="), Output);
    FParse::Value(FCommandLine::Get(), TEXT("ShaderArchive="), ShaderArchive);
    FParse::Value(FCommandLine::Get(), TEXT("ShaderDirectory="), ShaderDirectory);
    FParse::Value(FCommandLine::Get(), TEXT("ProjectDir="), ProjectDirectory);
    FParse::Value(FCommandLine::Get(), TEXT("Width="), Width);
    FParse::Value(FCommandLine::Get(), TEXT("Height="), Height);
    FParse::Value(FCommandLine::Get(), TEXT("Seconds="), Seconds);
    RivePlayback::FScenario Scenario;
    FString PlaybackError, PlaybackMetadataPath;
    FParse::Value(FCommandLine::Get(), TEXT("PlaybackMetadata="), PlaybackMetadataPath);
    if (!RivePlayback::LoadScenario(FCommandLine::Get(), Scenario, PlaybackError))
    {
        FPlatformMisc::LowLevelOutputDebugString(*FString::Printf(TEXT("Invalid playback scenario: %s\n"), *PlaybackError));
        return 2;
    }
    TSharedPtr<FJsonObject> PlaybackMetadata;
    FString Ui = TEXT("umg");
    FParse::Value(FCommandLine::Get(), TEXT("Ui="), Ui);
    if (FParse::Param(FCommandLine::Get(), TEXT("Capabilities")))
    {
        FPlatformMisc::LowLevelOutputDebugString(TEXT("{\"rive\":true,\"umg\":true}\n"));
        return 0;
    }
    const bool UseUmg = Ui == TEXT("umg");
    if (!UseUmg && Ui != TEXT("rive")) return 2;
    const bool UseUTextureTarget = FParse::Param(FCommandLine::Get(), TEXT("UTextureTarget"));
    if (Input.IsEmpty() || Output.IsEmpty() || ShaderArchive.IsEmpty() || ShaderDirectory.IsEmpty() ||
        Width <= 0 || Height <= 0 || Width > 8192 || Height > 8192)
    {
        FPlatformMisc::LowLevelOutputDebugString(TEXT("Require Input, Output, ShaderArchive, ShaderDirectory and valid dimensions.\n"));
        return 2;
    }
    if (!ProjectDirectory.IsEmpty()) FGenericPlatformMisc::SetOverrideProjectDir(ProjectDirectory);
    BootstrapReferenceCore(UseUTextureTarget);
    bool RHIStarted = false, RenderingStarted = false;
    ON_SCOPE_EXIT
    {
        RequestEngineExit(TEXT("Rive Engine Program reference complete"));
        ShutdownRiveUmg();
        if (RenderingStarted) ShutdownRenderingThread();
        if (RHIStarted)
        {
            for (int32 Platform = 0; Platform < SP_NumPlatforms; ++Platform)
            {
                delete GGlobalShaderMap[Platform];
                GGlobalShaderMap[Platform] = nullptr;
            }
            FShaderCodeLibrary::Shutdown();
            FRenderResource::ReleaseRHIForAllResources();
            RHIExit();
        }
        FCoreDelegates::OnPreExit.Broadcast();
        FCoreDelegates::OnExit.Broadcast();
        IPackageResourceManager::Shutdown();
        // As in FEngineLoop::Exit: shader library/file requests are released
        // before the dispatcher and before module/thread-pool teardown.
        FIoDispatcher::Shutdown();
        FModuleManager::Get().UnloadModulesAtShutdown();
        for (FQueuedThreadPool* Pool : {GThreadPool, GIOThreadPool, GBackgroundPriorityThreadPool})
            if (Pool) Pool->Destroy();
#if STATS
        FThreadStats::StopThread();
#endif
        FTaskGraphInterface::Shutdown();
        FPlatformApplicationMisc::TearDown();
        FPlatformMisc::PlatformTearDown();
        if (GConfig)
        {
            GConfig->Exit();
            delete GConfig;
            GConfig = nullptr;
        }
        if (GLog) GLog->TearDown();
    };

    RegisterRiveLiteShaderDirectory(FPaths::ConvertRelativePathToFull(ShaderDirectory));
    FGenericDataDrivenShaderPlatformInfo::Initialize();
    FShaderParametersMetadataRegistration::CommitAll();
    FShaderTypeRegistration::CommitAll();
    FShaderParametersMetadata::InitializeAllUniformBufferStructs();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreRHIInit);
    RHIInit(false);
    RHIStarted = true;
    if (GUsingNullRHI) return 7;
    PipelineStateCache::Init();
    RenderUtilsInit();
    InitializeShaderTypes();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ShaderTypesReady);
    if (!LoadReferenceShaderArchive(ShaderArchive)) return 3;
    TArray<uint32> PixelBytes;
    PixelBytes.SetNum(PF_MAX);
    for (int32 Index = 0; Index < PF_MAX; ++Index) PixelBytes[Index] = GPixelFormats[Index].BlockBytes;
    RHIPostInit(PixelBytes);
    InitRenderingThread();
    RenderingStarted = true;

    TArray<uint8> RiveBytes;
    if (!FFileHelper::LoadFileToArray(RiveBytes, *Input)) return 4;
    TStrongObjectPtr<UTextureRenderTarget2D> RenderTexture;
    FTextureRenderTargetResource* UTextureEngineTarget = nullptr;
    if (UseUTextureTarget)
    {
        RenderTexture.Reset(NewObject<UTextureRenderTarget2D>(GetTransientPackage()));
        RenderTexture->bCanCreateUAV = true;
        RenderTexture->bAutoGenerateMips = false;
        RenderTexture->ClearColor = FLinearColor::Transparent;
        RenderTexture->InitCustomFormat(Width, Height, PF_R8G8B8A8, true);
        RenderTexture->UpdateResourceImmediate(true);
        UTextureEngineTarget = RenderTexture->GameThread_GetRenderTargetResource();
    }
    ON_SCOPE_EXIT
    {
        if (RenderTexture.IsValid())
        {
            RenderTexture->ReleaseResource();
            FlushRenderingCommands();
        }
    };
    TArray<FColor> Pixels;
    bool RenderOK = false;
    if (UseUmg)
    {
        RenderOK = CaptureUmgFrame(RiveBytes, Scenario, Seconds, Width, Height,
            FParse::Param(FCommandLine::Get(), TEXT("HideRive")), Pixels, PlaybackMetadata, PlaybackError);
        if (!RenderOK) UE_LOG(LogRiveUmgHost, Error, TEXT("UMG capture failed: %s"), *PlaybackError);
    }
    else
    {
    ENQUEUE_RENDER_COMMAND(RiveUmgHostCapture)([&](FRHICommandListImmediate& RHICmdList)
    {
        FTextureRHIRef Texture;
        TUniquePtr<FTextureBackedEngineRenderTarget> TextureBackedTarget;
        FRenderTarget* EngineTarget = UTextureEngineTarget;
        if (UseUTextureTarget)
        {
            Texture = EngineTarget->GetRenderTargetTexture();
        }
        else
        {
            const auto Desc = FRHITextureCreateDesc::Create2D(TEXT("RiveUmgHostOutput"), Width, Height, PF_R8G8B8A8)
                .SetFlags(ETextureCreateFlags::RenderTargetable | ETextureCreateFlags::ShaderResource | ETextureCreateFlags::UAV)
                .SetInitialState(ERHIAccess::RTV).SetClearValue(FClearValueBinding(FLinearColor::Transparent));
            Texture = RHICmdList.CreateTexture(Desc);
            TextureBackedTarget = MakeUnique<FTextureBackedEngineRenderTarget>(Texture);
            EngineTarget = TextureBackedTarget.Get();
        }
        if (!Texture || Texture->GetFormat() != PF_R8G8B8A8 || Texture->GetDesc().NumSamples != 1 ||
            EnumHasAnyFlags(Texture->GetDesc().Flags, ETextureCreateFlags::SRGB))
        {
            UE_LOG(LogRiveUmgHost, Error, TEXT("Reference target must be linear RGBA8 with one sample"));
            return;
        }
        RenderContextRHIImpl::RHICapabilitiesOverrides Overrides;
        auto Context = RenderContextRHIImpl::MakeContext(RHICmdList, Overrides);
        if (!Context) return;
        rive::ImportResult ImportResult;
        auto File = rive::File::import({RiveBytes.GetData(), static_cast<size_t>(RiveBytes.Num())}, Context.get(), &ImportResult);
        if (!File) { UE_LOG(LogRiveUmgHost, Error, TEXT("Rive file import failed")); return; }
        std::unique_ptr<rive::ArtboardInstance> Artboard;
        if (!RivePlayback::Execute(*File, Scenario, Seconds, Artboard, PlaybackMetadata, PlaybackError))
        {
            UE_LOG(LogRiveUmgHost, Error, TEXT("Rive playback failed: %s"), *PlaybackError);
            return;
        }
        auto Target = Context->static_impl_cast<RenderContextRHIImpl>()->makeRenderTarget(RHICmdList, Texture);
        Context->beginFrame({.renderTargetWidth = static_cast<uint32_t>(Width), .renderTargetHeight = static_cast<uint32_t>(Height),
                            .loadAction = rive::gpu::LoadAction::clear, .clearColor = 0x00000000});
        rive::RiveRenderer Renderer(Context.get());
        Renderer.save();
        Renderer.align(rive::Fit::contain, rive::Alignment::center,
                       {0, 0, static_cast<float>(Width), static_cast<float>(Height)}, Artboard->bounds());
        Artboard->draw(&Renderer);
        Renderer.restore();
        FRDGBuilder Graph(RHICmdList);
        Context->flush({.renderTarget = Target.get(), .externalCommandBuffer = &Graph});
        Graph.Execute();
        RHICmdList.Transition(FRHITransitionInfo(Texture, ERHIAccess::Unknown, ERHIAccess::CopySrc));
        FReadSurfaceDataFlags Flags(RCM_UNorm);
        Flags.SetLinearToGamma(false);
        RHICmdList.ReadSurfaceData(Texture, FIntRect(0, 0, Width, Height), Pixels, Flags);
        RHICmdList.SubmitAndBlockUntilGPUIdle();
        RenderOK = Pixels.Num() == Width * Height;
    });
    }
    FlushRenderingCommands();
    if (!RenderOK) return 5;
    auto& ImageWrapper = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    TArray64<uint8> PNG;
    FImageView View(Pixels.GetData(), Width, Height, EGammaSpace::Linear);
    if (!ImageWrapper.CompressImage(PNG, EImageFormat::PNG, View) || !FFileHelper::SaveArrayToFile(PNG, *Output)) return 6;
    if (!PlaybackMetadataPath.IsEmpty() &&
        (!PlaybackMetadata.IsValid() || !RivePlayback::SaveMetadata(*PlaybackMetadata, PlaybackMetadataPath, PlaybackError)))
    {
        UE_LOG(LogRiveUmgHost, Error, TEXT("Cannot save playback metadata: %s"), *PlaybackError);
        return 8;
    }
    UE_LOG(LogRiveUmgHost, Display,
           TEXT("RIVE_UE_REFERENCE_CAPTURE path=\"%s\" width=%d height=%d seconds=%.3f first_image_ms=%.3f adapter=\"%s\" render_path=UE_RHI_RDG rive_backend=lite_rhi engine_linked=1 renderer_linked=1 engine_frender_target=%d utexture_target=%d editor_viewport=0 umg_composite=%d"),
           *Output, Width, Height, Scenario.bEnabled ? Scenario.TargetTime : static_cast<double>(Seconds),
           (FPlatformTime::Seconds() - StartSeconds) * 1000.0, *GRHIAdapterName, UseUmg, UseUTextureTarget, UseUmg);
    return 0;
}
