#pragma once

#include "CoreMinimal.h"
#include "Platform/RenderContextRHIImpl.hpp"

// Call before InitializeShaderTypes / loading the cooked global shader map.
// The caller supplies the deployed Shaders directory explicitly.
RIVELITERENDERER_API void RegisterRiveLiteShaderDirectory(const FString& Directory);

// This first prototype supports ordinary Rive 2D artboards only. GPU Canvas,
// Ore and Unreal UTexture/UWidget resource wrappers are not provided.
inline constexpr bool RiveLiteSupportsOre = false;
