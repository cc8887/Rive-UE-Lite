// Host-side adapter. Include after selecting exactly one Rive renderer backend.
#include "RiveUmgBridge.h"
#include "RenderGraphResources.h"
#include "rive/math/raw_path.hpp"

static bool CaptureUmgFrame(const TArray<uint8>& Bytes, const RivePlayback::FScenario& Scenario,
    float Seconds, int32 Width, int32 Height, bool HideRive,
    TArray<FColor>& Pixels, TSharedPtr<FJsonObject>& Metadata, FString& Error)
{
    FTextureRHIRef Texture;
    ENQUEUE_RENDER_COMMAND(CreateUmgOutput)([&](FRHICommandListImmediate& Cmd)
    {
        Texture = Cmd.CreateTexture(FRHITextureCreateDesc::Create2D(TEXT("UmgOutput"), Width, Height, PF_R8G8B8A8)
            .SetFlags(ETextureCreateFlags::RenderTargetable | ETextureCreateFlags::ShaderResource | ETextureCreateFlags::UAV)
            .SetInitialState(ERHIAccess::RTV).SetClearValue(FClearValueBinding(FLinearColor::Transparent)));
    });
    FlushRenderingCommands();
    FTextureBackedEngineRenderTarget Target(Texture);
    std::unique_ptr<rive::gpu::RenderContext> Context;
    rive::rcp<rive::File> File;
    std::unique_ptr<rive::ArtboardInstance> Artboard;
    int32 Draws = 0;
    bool DrawOK = false;
    auto Draw = [&](FRDGBuilder& Graph, FRDGTextureRef Output, const FSlateRect& Bounds, const FSlateRect& Clip)
    {
        FRHICommandListImmediate& Cmd = FRHICommandListExecutor::GetImmediateCommandList();
        RenderContextRHIImpl::RHICapabilitiesOverrides Overrides;
        Context = RenderContextRHIImpl::MakeContext(Cmd, Overrides);
        if (!Context) { Error = TEXT("Rive RHI context failed"); return; }
        rive::ImportResult Imported;
        File = rive::File::import({Bytes.GetData(), static_cast<size_t>(Bytes.Num())}, Context.get(), &Imported);
        if (!File || !RivePlayback::Execute(*File, Scenario, Seconds, Artboard, Metadata, Error)) return;
        auto RenderTarget = Context->static_impl_cast<RenderContextRHIImpl>()->makeRenderTarget(Output);
        Context->beginFrame({.renderTargetWidth = static_cast<uint32_t>(Width),
            .renderTargetHeight = static_cast<uint32_t>(Height),
            .loadAction = rive::gpu::LoadAction::preserveRenderTarget});
        rive::RiveRenderer Renderer(Context.get());
        Renderer.save();
        rive::RawPath Path;
        Path.addRect({Clip.Left, Clip.Top, Clip.Right, Clip.Bottom});
        auto Clipping = Context->makeRenderPath(Path, rive::FillRule::nonZero);
        Renderer.clipPath(Clipping.get());
        Renderer.align(rive::Fit::contain, rive::Alignment::center,
            {Bounds.Left, Bounds.Top, Bounds.Right, Bounds.Bottom}, Artboard->bounds());
        Artboard->draw(&Renderer);
        Renderer.restore();
        Context->flush({.renderTarget = RenderTarget.get(), .externalCommandBuffer = &Graph});
        ++Draws;
        DrawOK = true;
    };
    const bool WidgetOK = DrawRiveUmgDemo(&Target, FIntPoint(Width, Height), Draw, HideRive, Error);
    if (!WidgetOK || (!HideRive && (!DrawOK || Draws != 1)))
    {
        if (Error.IsEmpty()) Error = FString::Printf(TEXT("Rive custom draw count was %d"), Draws);
        return false;
    }
    ENQUEUE_RENDER_COMMAND(ReadUmgOutput)([&](FRHICommandListImmediate& Cmd)
    {
        Cmd.Transition(FRHITransitionInfo(Texture, ERHIAccess::Unknown, ERHIAccess::CopySrc));
        FReadSurfaceDataFlags Flags(RCM_UNorm);
        Flags.SetLinearToGamma(false);
        Cmd.ReadSurfaceData(Texture, FIntRect(0, 0, Width, Height), Pixels, Flags);
        Cmd.SubmitAndBlockUntilGPUIdle();
        Artboard.reset();
        File = nullptr;
        Context.reset();
    });
    FlushRenderingCommands();
    return Pixels.Num() == Width * Height;
}
