#include "RiveUmgBridge.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/NativeWidgetHost.h"
#include "Brushes/SlateColorBrush.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "Interfaces/ISlateRHIRendererModule.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Rendering/DrawElements.h"
#include "RenderingThread.h"
#include "Slate/WidgetRenderer.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectBase.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
class FRiveUmgElement final : public ICustomSlateElement
{
public:
    FRiveUmgDraw Draw;
    FSlateRect Bounds, Clip;
    void Draw_RenderThread(FRDGBuilder& Graph, const FDrawPassInputs& Inputs) override
    {
        if (Inputs.OutputTexture) Draw(Graph, Inputs.OutputTexture, Bounds, Clip);
    }
};

class SRiveUmgLeaf final : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SRiveUmgLeaf) {} SLATE_END_ARGS()
    void Construct(const FArguments&, FRiveUmgDraw Draw)
    {
        Element = MakeShared<FRiveUmgElement, ESPMode::ThreadSafe>();
        Element->Draw = MoveTemp(Draw);
    }
    FVector2D ComputeDesiredSize(float) const override { return FVector2D(320, 300); }
    int32 OnPaint(const FPaintArgs&, const FGeometry& Geometry, const FSlateRect& Culling,
        FSlateWindowElementList& List, int32 Layer, const FWidgetStyle&, bool) const override
    {
        Element->Bounds = Geometry.GetLayoutBoundingRect();
        Element->Clip = Element->Bounds.IntersectionWith(Culling);
        FSlateDrawElement::MakeCustom(List, Layer, Element);
        return Layer;
    }
private:
    TSharedPtr<FRiveUmgElement, ESPMode::ThreadSafe> Element;
};

void Place(UCanvasPanel* Root, UWidget* Widget, FVector2D Position, FVector2D Size)
{
    UCanvasPanelSlot* Slot = Root->AddChildToCanvas(Widget);
    Slot->SetPosition(Position);
    Slot->SetSize(Size);
}
}

bool DrawRiveUmgDemo(FRenderTarget* Target, FIntPoint Size, FRiveUmgDraw Draw, bool bHideRive, FString& Error)
{
    if (Size.X < 320 || Size.Y < 320) { Error = TEXT("UMG demo requires at least 320x320"); return false; }
#if UE_WITH_CONSTINIT_UOBJECT
    // UE6's native reflection-only startup step links config property chains
    // without eagerly creating every Engine CDO or requiring a World.
    UE::CoreUObject::ConstructCompiledInObjects();
#else
    // Pinned UE6 exposes a native lazy-CDO Program startup mode. Register/link
    // reflected properties before any Slate config object is first requested.
    // Classes actually used below still construct their real CDOs normally.
    SetPreCreateCompiledInClassDefaultObjects(false);
    ProcessNewlyLoadedUObjects();
    FModuleManager::Get().StartProcessingNewlyLoadedObjects();
#endif
    if (!FSlateApplication::IsInitialized())
    {
        auto& Module = FModuleManager::LoadModuleChecked<ISlateRHIRendererModule>(TEXT("SlateRHIRenderer"));
        FSlateApplication::InitializeAsStandaloneApplication(Module.CreateSlateRHIRenderer(),
            MakeShared<GenericApplication>(TSharedPtr<ICursor>()));
    }
    TStrongObjectPtr<UCanvasPanel> Root(NewObject<UCanvasPanel>());
    const FVector2D Extent(Size.X, Size.Y);
    UBorder* Background = NewObject<UBorder>(Root.Get());
    FSlateColorBrush BackgroundBrush(FLinearColor(0.025f, 0.045f, 0.08f, 1.f));
    Background->SetBrush(BackgroundBrush);
    Place(Root.Get(), Background, FVector2D::ZeroVector, Extent);

    // Use a file-backed native Slate font; no fake UFont/default Engine asset.
    const FString Font = FPaths::EngineContentDir() / TEXT("Slate/Fonts/Roboto-Regular.ttf");
    UNativeWidgetHost* Heading = NewObject<UNativeWidgetHost>(Root.Get());
    Heading->SetContent(SNew(STextBlock).Text(FText::FromString(TEXT("Rive + UMG")))
        .Font(FSlateFontInfo(Font, 24)).ColorAndOpacity(FLinearColor(0.9f, 0.95f, 1.f, 1.f)));
    Place(Root.Get(), Heading, FVector2D(28, 20), FVector2D(Extent.X - 56, 40));

    UNativeWidgetHost* Leaf = NewObject<UNativeWidgetHost>(Root.Get());
    Leaf->SetContent(SNew(SRiveUmgLeaf, MoveTemp(Draw)));
    if (bHideRive) Leaf->SetVisibility(ESlateVisibility::Hidden);
    Place(Root.Get(), Leaf, FVector2D(28, 76), FVector2D(Extent.X - 56, Extent.Y - 160));

    UButton* Button = NewObject<UButton>(Root.Get());
    UNativeWidgetHost* ButtonLabel = NewObject<UNativeWidgetHost>(Root.Get());
    ButtonLabel->SetContent(SNew(STextBlock).Text(FText::FromString(TEXT("CPU Vulkan preview")))
        .Font(FSlateFontInfo(Font, 17)).ColorAndOpacity(FLinearColor::White));
    Button->AddChild(ButtonLabel);
    Place(Root.Get(), Button, FVector2D(28, Extent.Y - 64), FVector2D(Extent.X - 56, 40));

    {
        FWidgetRenderer Renderer(false, true);
        Renderer.DrawWidget(Target, Root->TakeWidget(), Extent, 0.f, false);
        FlushRenderingCommands();
    }
    Root->ReleaseSlateResources(true);
    FlushRenderingCommands();
    UE_LOGF(LogTemp, Display, "RIVE_UMG_TREE root=%ls button=%ls rive_host=%ls rive_visible=%d",
        *Root->GetClass()->GetName(), *Button->GetClass()->GetName(), *Leaf->GetClass()->GetName(), !bHideRive);
    return true;
}

void ShutdownRiveUmg()
{
    if (FSlateApplication::IsInitialized())
    {
        FlushRenderingCommands();
        FSlateApplication::Shutdown();
    }
}

IMPLEMENT_MODULE(FDefaultModuleImpl, RiveUmgBridge)
