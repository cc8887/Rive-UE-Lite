#include "CoreMinimal.h"
#include <cstdio>
#include <cstdlib>
#include "RequiredProgramMainCPPInclude.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "DynamicRHI.h"
#include "GlobalShader.h"
#include "IImageWrapperModule.h"
#include "ImageCore.h"
#include "IO/IoDispatcher.h"
#include "Misc/DelayedAutoRegister.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "PipelineStateCache.h"
#include "RenderGraphBuilder.h"
#include "RenderResource.h"
#include "RenderingThread.h"
#include "RenderUtils.h"
#include "RHICommandList.h"
#include "Serialization/MemoryReader.h"
#include "ShaderCodeLibrary.h"
#include "ShaderCore.h"
#include "ShaderParameterMetadata.h"
#include "ShaderPlatformConfig.h"
#include "UObject/UObjectGlobals.h"
#if RIVE_LITE_WITH_RIVE
#include "RiveLiteRenderer.h"
#include "RivePlayback.h"
#include "rive/artboard.hpp"
#include "rive/file.hpp"
#include "rive/renderer/rive_renderer.hpp"
#endif

#if WITH_ENGINE || RIVE_HOST_WITH_UMG
#error RiveRhiLite must remain an Engine-free, UMG-free Program.
#endif

IMPLEMENT_APPLICATION(RiveRhiLite, "RiveRhiLite");
DEFINE_LOG_CATEGORY_STATIC(LogRiveLiteHost, Log, All);

static bool LoadLiteShaderArchive(const FString& Path, EShaderPlatform Platform)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path))
    {
        UE_LOG(LogRiveLiteHost, Error, TEXT("Missing compatible cooked shader archive: %s"), *Path);
        return false;
    }
    FShaderCodeLibrary::InitForRuntime(Platform);
    FMemoryReader Reader(Bytes);
    GGlobalShaderMap[Platform] = new FGlobalShaderMap(Platform);
    GGlobalShaderMap[Platform]->LoadFromGlobalArchive(Reader);
    GGlobalShaderMap[Platform]->BeginCreateAllShaders();
    return !Reader.IsError();
}

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    const double StartSeconds = FPlatformTime::Seconds();
    FTaskTagScope Scope(ETaskTag::EGameThread);
    bool RenderingStarted = false;
    bool RHIStarted = false;
    bool BootstrapStarted = false;
    ON_SCOPE_EXIT
    {
        if (!BootstrapStarted) return;
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
        RequestEngineExit(TEXT("RiveLite complete"));
        FEngineLoop::AppPreExit();
        FIoDispatcher::Shutdown();
        FModuleManager::Get().UnloadModulesAtShutdown();
        FEngineLoop::AppExit();
    };
    // Program targets do not consume the game's ProjectDir flag themselves.
    // Select the package/config root before PreInit caches any project paths.
    FString ProjectDirectory;
    const FString BootstrapCommandLine = FCommandLine::BuildFromArgV(nullptr, ArgC, ArgV, nullptr);
    if (FParse::Param(*BootstrapCommandLine, TEXT("Capabilities")))
    {
        std::fputs("{\"rive\":true,\"umg\":false}\n", stdout);
        std::fflush(stdout);
#if PLATFORM_WINDOWS
        // CoreUObject has static listeners whose destructors require full engine
        // initialization. This CLI-only path has deliberately not initialized it.
        std::_Exit(0);
#endif
        return 0;
    }
    FString Ui = TEXT("rive");
    FParse::Value(*BootstrapCommandLine, TEXT("Ui="), Ui);
    if (Ui != TEXT("rive"))
    {
        std::fputs("UMG_NOT_COMPILED: rebuild with --with-umg to use -Ui=umg\n", stderr);
        std::fflush(stderr);
#if PLATFORM_WINDOWS
        std::_Exit(9);
#endif
        return 9;
    }
    if (FParse::Value(*BootstrapCommandLine, TEXT("ProjectDir="), ProjectDirectory))
    {
        FGenericPlatformMisc::SetOverrideProjectDir(ProjectDirectory);
    }
    BootstrapStarted = true;
    if (int32 Result = GEngineLoop.PreInit(ArgC, ArgV)) return Result;

    FString Input, Output, ShaderArchive, ShaderDirectory;
    int32 Width = 512, Height = 512;
    float Seconds = 0.0f;
    const TCHAR* Cmd = FCommandLine::Get();
    FParse::Value(Cmd, TEXT("Input="), Input);
    FParse::Value(Cmd, TEXT("Output="), Output);
    FParse::Value(Cmd, TEXT("ShaderArchive="), ShaderArchive);
    FParse::Value(Cmd, TEXT("ShaderDirectory="), ShaderDirectory);
    FParse::Value(Cmd, TEXT("Width="), Width);
    FParse::Value(Cmd, TEXT("Height="), Height);
    FParse::Value(Cmd, TEXT("Seconds="), Seconds);
    const bool ProbeOnly = FParse::Param(Cmd, TEXT("ProbeRHI")) || !RIVE_LITE_WITH_RIVE;
#if RIVE_LITE_WITH_RIVE
    RivePlayback::FScenario Scenario;
    FString PlaybackError, PlaybackMetadataPath;
    FParse::Value(Cmd, TEXT("PlaybackMetadata="), PlaybackMetadataPath);
    if (!RivePlayback::LoadScenario(Cmd, Scenario, PlaybackError))
    {
        UE_LOG(LogRiveLiteHost, Error, TEXT("Invalid playback scenario: %s"), *PlaybackError);
        return 2;
    }
    TSharedPtr<FJsonObject> PlaybackMetadata;
#endif
    if (Output.IsEmpty() || Width <= 0 || Height <= 0 || Width > 8192 || Height > 8192)
    {
        UE_LOG(LogRiveLiteHost, Error, TEXT("Require -Output=... and valid dimensions"));
        return 2;
    }

    ProcessNewlyLoadedUObjects();
    FModuleManager::Get().StartProcessingNewlyLoadedObjects();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RenderCore"));
#if RIVE_LITE_WITH_RIVE
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RiveLiteRenderer"));
    if (ShaderDirectory.IsEmpty()) ShaderDirectory = FPaths::Combine(FPaths::ProjectDir(), TEXT("Shaders"));
    RegisterRiveLiteShaderDirectory(FPaths::ConvertRelativePathToFull(ShaderDirectory));
#endif
    FGenericDataDrivenShaderPlatformInfo::Initialize();
    FShaderParametersMetadataRegistration::CommitAll();
    FShaderTypeRegistration::CommitAll();
    FShaderParametersMetadata::InitializeAllUniformBufferStructs();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreRHIInit);
    RHIInit(false);
    RHIStarted = true;
    if (GUsingNullRHI)
    {
        UE_LOG(LogRiveLiteHost, Error, TEXT("A real platform RHI (Vulkan/Metal) is required; NullRHI cannot produce validation pixels"));
        return 7;
    }
    PipelineStateCache::Init();
    // Rive consumes hardware/platform capabilities, not scene/mobile renderer CVars.
    // RenderUtilsInit() also initializes Engine/Renderer's scene CVar cache.
    FShaderPlatformConfig::Initialize();
    if (!ProbeOnly)
    {
        InitializeShaderTypes();
        FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ShaderTypesReady);
        if (!LoadLiteShaderArchive(ShaderArchive, GMaxRHIShaderPlatform)) return 3;
    }
    TArray<uint32> PixelBytes;
    PixelBytes.SetNum(PF_MAX);
    for (int32 i = 0; i < PF_MAX; ++i) PixelBytes[i] = GPixelFormats[i].BlockBytes;
    RHIPostInit(PixelBytes);
    InitRenderingThread();
    RenderingStarted = true;

    TArray<uint8> RiveBytes;
    if (!ProbeOnly && !FFileHelper::LoadFileToArray(RiveBytes, *Input)) return 4;
    TArray<FColor> Pixels;
    bool RenderOK = false;
    ENQUEUE_RENDER_COMMAND(RiveLiteCapture)([&](FRHICommandListImmediate& RHICmdList)
    {
        auto Desc = FRHITextureCreateDesc::Create2D(TEXT("RiveLiteOutput"), Width, Height, PF_R8G8B8A8)
            .SetFlags(ETextureCreateFlags::RenderTargetable | ETextureCreateFlags::ShaderResource | ETextureCreateFlags::UAV)
            .SetInitialState(ERHIAccess::RTV)
            .SetClearValue(FClearValueBinding(ProbeOnly ? FLinearColor(0.1f, 0.2f, 0.3f, 1.0f) : FLinearColor::Transparent));
        FTextureRHIRef Texture = RHICmdList.CreateTexture(Desc);
        if (ProbeOnly)
        {
            FRHIRenderPassInfo Pass(Texture, ERenderTargetActions::Clear_Store);
            RHICmdList.BeginRenderPass(Pass, TEXT("RhiBootstrapProbeOnly"));
            RHICmdList.EndRenderPass();
        }
#if RIVE_LITE_WITH_RIVE
        else
        {
            RenderContextRHIImpl::RHICapabilitiesOverrides Overrides;
            auto Context = RenderContextRHIImpl::MakeContext(RHICmdList, Overrides);
            if (!Context) return;
            rive::ImportResult ImportResult;
            auto File = rive::File::import({RiveBytes.GetData(), static_cast<size_t>(RiveBytes.Num())}, Context.get(), &ImportResult);
            if (!File) return;
            std::unique_ptr<rive::ArtboardInstance> Artboard;
            if (!RivePlayback::Execute(*File, Scenario, Seconds, Artboard, PlaybackMetadata, PlaybackError))
            {
                UE_LOG(LogRiveLiteHost, Error, TEXT("Rive playback failed: %s"), *PlaybackError);
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
        }
#endif
        RHICmdList.Transition(FRHITransitionInfo(Texture, ERHIAccess::Unknown, ERHIAccess::CopySrc));
        FReadSurfaceDataFlags Flags(RCM_UNorm);
        Flags.SetLinearToGamma(false);
        RHICmdList.ReadSurfaceData(Texture, FIntRect(0, 0, Width, Height), Pixels, Flags);
        RHICmdList.SubmitAndBlockUntilGPUIdle();
        RenderOK = Pixels.Num() == Width * Height;
    });
    FlushRenderingCommands();
    if (!RenderOK) return 5;
    auto& ImageWrapper = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    TArray64<uint8> PNG;
    FImageView View(Pixels.GetData(), Width, Height, EGammaSpace::Linear);
    if (!ImageWrapper.CompressImage(PNG, EImageFormat::PNG, View) || !FFileHelper::SaveArrayToFile(PNG, *Output)) return 6;
#if RIVE_LITE_WITH_RIVE
    if (!ProbeOnly && !PlaybackMetadataPath.IsEmpty() &&
        (!PlaybackMetadata.IsValid() || !RivePlayback::SaveMetadata(*PlaybackMetadata, PlaybackMetadataPath, PlaybackError)))
    {
        UE_LOG(LogRiveLiteHost, Error, TEXT("Cannot save playback metadata: %s"), *PlaybackError);
        return 8;
    }
#endif
    UE_LOG(LogRiveLiteHost, Display, TEXT("RIVE_LITE_CAPTURE path=\"%s\" width=%d height=%d first_image_ms=%.3f adapter=\"%s\" probe_only=%d render_path=UE_RHI_RDG RiveDrawCompleted=%d"),
           *Output, Width, Height, (FPlatformTime::Seconds() - StartSeconds) * 1000.0, *GRHIAdapterName, ProbeOnly, !ProbeOnly);
    return 0;
}
