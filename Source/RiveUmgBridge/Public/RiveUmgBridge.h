#pragma once

#include "CoreMinimal.h"
#include "RenderGraphFwd.h"
#include "RHIResources.h"
#include "Layout/SlateRect.h"

class FRenderTarget;
using FRiveUmgDraw = TFunction<void(FRDGBuilder&, FRDGTextureRef, const FSlateRect&, const FSlateRect&)>;

// True native UMG controls; only the embedded Rive leaf has a custom Slate draw.
RIVEUMGBRIDGE_API bool DrawRiveUmgDemo(
    FRenderTarget* Target, FIntPoint Size, FRiveUmgDraw Draw, bool bHideRive, FString& Error);
RIVEUMGBRIDGE_API void ShutdownRiveUmg();
