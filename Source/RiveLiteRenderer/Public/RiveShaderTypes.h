// Copyright 2024-2026 Rive, Inc. All rights reserved.

#pragma once
#include "CoreMinimal.h"
#include "ShaderParameterStruct.h"
#include "RenderResource.h"
#include "RHI.h"
#include "GlobalShader.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "ShaderCompilerCore.h"
#include "UniformBuffer.h"

#include "HLSLTypeAliases.h"
#include "rive/enums.hpp"
#include "rive/generated/shaders/rhi.glsl.exports.h"
#include "Misc/EngineVersionComparison.h"

#ifndef RIVE_FORCE_USE_GENERATED_UNIFORMS
#define RIVE_FORCE_USE_GENERATED_UNIFORMS 1
#endif

#ifndef FORCE_ATOMIC_BUFFER
#define FORCE_ATOMIC_BUFFER 0
#endif

DECLARE_LOG_CATEGORY_EXTERN(LogRiveShaderCompiler, Display, All);

#if UE_VERSION_OLDER_THAN(5, 4, 0)
#define CREATE_TEXTURE_ASYNC(RHICmdList, Desc) RHICreateTexture(Desc)
#define CREATE_TEXTURE(RHICmdList, Desc) RHICreateTexture(Desc)
#define RASTER_STATE(FillMode, CullMode, DepthClip)                            \
  TStaticRasterizerState<FillMode, CullMode, false, false, DepthClip>::GetRHI()
#define SET_PIPELINE_STATE(CommandList, GraphicsPSOInit)                       \
  SetGraphicsPipelineState(                                                    \
      CommandList,                                                             \
      GraphicsPSOInit,                                                         \
      0,                                                                       \
      EApplyRendertargetOption::CheckApply,                                    \
      true,                                                                    \
      EPSOPrecacheResult::Unknown)
#elif UE_VERSION_OLDER_THAN(5, 5, 0)
#define CREATE_TEXTURE_ASYNC(RHICmdList, Desc) RHICmdList->CreateTexture(Desc)
#define CREATE_TEXTURE(RHICmdList, Desc) RHICmdList.CreateTexture(Desc)
#define RASTER_STATE(FillMode, CullMode, DepthClip, EnableMSAA)                \
  TStaticRasterizerState<FillMode, CullMode, DepthClip, EnableMSAA>::GetRHI()
#define SET_PIPELINE_STATE(CommandList, GraphicsPSOInit)                       \
  SetGraphicsPipelineState(                                                    \
      CommandList,                                                             \
      GraphicsPSOInit,                                                         \
      0,                                                                       \
      EApplyRendertargetOption::CheckApply,                                    \
      true,                                                                    \
      EPSOPrecacheResult::Unknown)
#else // UE_VERSION_NEWER_OR_EQUAL_TO (5, 5,0)
#define CREATE_TEXTURE_ASYNC(RHICmdList, Desc) RHICmdList.CreateTexture(Desc)
#define CREATE_TEXTURE(RHICmdList, Desc) RHICmdList.CreateTexture(Desc)
#define RASTER_STATE(FillMode, CullMode, DepthClip, EnableMSAA)                \
  TStaticRasterizerState<FillMode, CullMode, DepthClip, EnableMSAA>::GetRHI()

#define SET_PIPELINE_STATE(CommandList, GraphicsPSOInit, StencilRef)           \
  SetGraphicsPipelineState(CommandList, GraphicsPSOInit, StencilRef)
#endif

namespace rive::gpu
{
struct DrawBatch;
struct FlushDescriptor;
} // namespace rive::gpu

// shader permutation params
// Whole
class FEnableClip : SHADER_PERMUTATION_BOOL("ENABLE_CLIPPING");
class FEnableClipRect : SHADER_PERMUTATION_BOOL("ENABLE_CLIP_RECT");
class FEnableAdvanceBlend : SHADER_PERMUTATION_BOOL("ENABLE_ADVANCED_BLEND");
class FEnableFeather : SHADER_PERMUTATION_BOOL("ENABLE_FEATHER");
class FEnableModulatedImage : SHADER_PERMUTATION_BOOL("ENABLE_MODULATED_IMAGE");
class FEnableAngularGradient
    : SHADER_PERMUTATION_BOOL("ENABLE_ANGULAR_GRADIENT");

// FragmentOnly
class FEnableFixedFunctionColorOutput
    : SHADER_PERMUTATION_BOOL("FIXED_FUNCTION_COLOR_OUTPUT");
class FEnableHSLBlendMode : SHADER_PERMUTATION_BOOL("ENABLE_HSL_BLEND_MODES");
class FEnableNestedClip : SHADER_PERMUTATION_BOOL("ENABLE_NESTED_CLIPPING");
class FEnableEvenOdd : SHADER_PERMUTATION_BOOL("ENABLE_EVEN_ODD");
class FEnableTypedUAVLoads
    : SHADER_PERMUTATION_BOOL("ENABLE_TYPED_UAV_LOAD_STORE");
class FEnableClockwiseFill : SHADER_PERMUTATION_BOOL("CLOCKWISE_FILL");
class FCoalescedPlsResolveAndTransfer
    : SHADER_PERMUTATION_BOOL("COALESCED_PLS_RESOLVE_AND_TRANSFER");

typedef TShaderPermutationDomain<
    FEnableClip,
    FEnableClipRect,
    FEnableNestedClip,
    FEnableFixedFunctionColorOutput,
    FCoalescedPlsResolveAndTransfer,
    FEnableAdvanceBlend,
    FEnableEvenOdd,
    FEnableHSLBlendMode,
    FEnableFeather,
    FEnableClockwiseFill,
    FEnableModulatedImage,
    FEnableAngularGradient>

    AtomicPixelPermutationDomain;
typedef TShaderPermutationDomain<
    FEnableClip,
    FEnableClipRect,
    FEnableAdvanceBlend,
    FEnableFeather,
    FEnableModulatedImage,
    FEnableAngularGradient>
    AtomicVertexPermutationDomain;

#define USE_ATOMIC_PIXEL_PERMUTATIONS                                          \
  using FPermutationDomain = AtomicPixelPermutationDomain;

#define USE_ATOMIC_VERTEX_PERMUTATIONS                                         \
  using FPermutationDomain = AtomicVertexPermutationDomain;

#define DECLARE_UNIFORM_FLOAT(param) SHADER_PARAMETER(float, param)
#define DECLARE_UNIFORM_UINT(param) SHADER_PARAMETER(UE::HLSL::uint, param)
#define DECLARE_UNIFORM_INT4(param) SHADER_PARAMETER(UE::HLSL::int4, param)
#define DECLARE_UNIFORM_FLOAT2(param) SHADER_PARAMETER(UE::HLSL::float2, param)
#define DECLARE_UNIFORM_FLOAT4(param) SHADER_PARAMETER(UE::HLSL::float4, param)

#define UNIFORM_BLOCK_BEGIN(IDX, NAME)                                         \
  BEGIN_UNIFORM_BUFFER_STRUCT(NAME, RIVELITERENDERER_API)

#define UNIFORM_BLOCK_END(NAME) END_UNIFORM_BUFFER_STRUCT();

#define FLUSH_UNIFORMS_NAME FFlushUniforms

#include "rive/shaders/flush_uniforms.glsl"

RIVELITERENDERER_API void BindStaticFlushUniforms(
    FRHICommandList&,
    FUniformBufferRHIRef);

// One shared uniform struct used for all atomic frament shaders besides
// gradient and tesselation. Params not used will be marked null
BEGIN_SHADER_PARAMETER_STRUCT(FRivePixelDrawUniforms, RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0)
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif

SHADER_PARAMETER_RDG_TEXTURE(
    Texture2DArray<float>,
    GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D<float>, GLSL_featherAtlasTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_gradTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_imageTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2DMS, GLSL_dstColorTexture_raw)

SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<uint>, coverageCountBuffer)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<uint>, coverageAtomicBuffer)

SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<uint>, clipBuffer)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, colorBuffer)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, scratchColorBuffer)
SHADER_PARAMETER_SAMPLER(SamplerState, gradSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, imageSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, featherAtlasSampler)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GLSL_paintBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(
    StructuredBuffer<float4>,
    GLSL_paintAuxBuffer_raw)

END_SHADER_PARAMETER_STRUCT()

BEGIN_SHADER_PARAMETER_STRUCT(
    FRivePixelDrawUniformsAtomicBuffers,
    RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0)
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif

SHADER_PARAMETER_RDG_TEXTURE(
    Texture2DArray<float>,
    GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D<float>, GLSL_featherAtlasTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_gradTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_imageTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2DMS, GLSL_dstColorTexture_raw)

SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<uint>, coverageCountBuffer)
SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<uint>, coverageAtomicBuffer)

SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<uint>, clipBuffer)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, colorBuffer)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, scratchColorBuffer)
SHADER_PARAMETER_SAMPLER(SamplerState, gradSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, imageSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, featherAtlasSampler)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GLSL_paintBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(
    StructuredBuffer<float4>,
    GLSL_paintAuxBuffer_raw)

END_SHADER_PARAMETER_STRUCT()

// One shared uniform struct used for all atomic vertex shaders besides gradient
// and tesselation. Params not used will be marked null

BEGIN_SHADER_PARAMETER_STRUCT(FRiveVertexDrawUniforms, RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
SHADER_PARAMETER_RDG_TEXTURE(
    Texture2DArray<float>,
    GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D<uint4>, GLSL_tessVertexTexture_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, GLSL_pathBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, GLSL_contourBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GLSL_paintBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(
    StructuredBuffer<float4>,
    GLSL_paintAuxBuffer_raw)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
SHADER_PARAMETER(unsigned int, baseInstance)
END_SHADER_PARAMETER_STRUCT()

BEGIN_SHADER_PARAMETER_STRUCT(FRiveMSAAPixelDrawUniforms, RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif

SHADER_PARAMETER_RDG_TEXTURE(
    Texture2DArray<float>,
    GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D<float>, GLSL_featherAtlasTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_gradTexture_raw)
SHADER_PARAMETER_TEXTURE(Texture2D, GLSL_imageTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_dstColorTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<float4>, GLSL_dstColorUav_raw)

SHADER_PARAMETER_SAMPLER(SamplerState, gradSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, imageSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
SHADER_PARAMETER_SAMPLER(SamplerState, featherAtlasSampler)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GLSL_paintBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(
    StructuredBuffer<float4>,
    GLSL_paintAuxBuffer_raw)

END_SHADER_PARAMETER_STRUCT()

BEGIN_SHADER_PARAMETER_STRUCT(FRiveMSAAVertexDrawUniforms, RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0)
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
SHADER_PARAMETER_RDG_TEXTURE(
    Texture2DArray<float>,
    GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D<uint4>, GLSL_tessVertexTexture_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, GLSL_pathBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, GLSL_contourBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GLSL_paintBuffer_raw)
SHADER_PARAMETER_RDG_BUFFER_SRV(
    StructuredBuffer<float4>,
    GLSL_paintAuxBuffer_raw)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
SHADER_PARAMETER(unsigned int, baseInstance)
SHADER_PARAMETER(unsigned int, baseVertex)
END_SHADER_PARAMETER_STRUCT()

// Data driven so platforms added after this code was written are classified
// without touching it. Both answer the shader language the platform compiles
// to, which is what decides the variants below.
static bool IsTargetVulkan(const FShaderPermutationParameters& Parameters)
{
  return FDataDrivenShaderPlatformInfo::GetIsLanguageVulkan(
      Parameters.Platform);
}

static bool IsTargetMetal(const FShaderPermutationParameters& Parameters)
{
  return FDataDrivenShaderPlatformInfo::GetIsLanguageMetal(Parameters.Platform);
}

// Driver workarounds and platform quirks, named for what they do rather than
// for the platform that needs them. Each reads a cvar the target platform sets
// in its own config, so adding a platform never means editing this file.
RIVELITERENDERER_API bool RivePlatformForcesAtomicBuffer(
    const FShaderPermutationParameters& Params);
RIVELITERENDERER_API bool RivePlatformNeedsPathIdClampWorkaround(
    const FShaderPermutationParameters& Params);
RIVELITERENDERER_API bool RivePlatformNeedsUshortDefine(
    const FShaderPermutationParameters& Params);

namespace rive
{
// This enum lives in the rive namespace so it can discover the flag operators.
enum class PixelPermutationFlags
{
  none = 0x00,
  isResolve = 0x01,
  isAtomicBuffer = 0x02,
  allowModulatedImage = 0x04,
  allowAngularGradient = 0x08,
};
} // namespace rive

template <typename ShaderClass>
static bool RiveShouldCompilePixelPermutation(
    const FShaderPermutationParameters& Parameters,
    rive::PixelPermutationFlags flags)
{
  bool isResolve = rive::enums::is_flag_set(
      flags,
      rive::PixelPermutationFlags::isResolve);
  bool isAtomicBuffer = rive::enums::is_flag_set(
      flags,
      rive::PixelPermutationFlags::isAtomicBuffer);
  bool allowModulatedImage = rive::enums::is_flag_set(
      flags,
      rive::PixelPermutationFlags::allowModulatedImage);
  bool allowAngularGradient = rive::enums::is_flag_set(
      flags,
      rive::PixelPermutationFlags::allowAngularGradient);

  typename ShaderClass::FPermutationDomain PermutationVector(
      Parameters.PermutationId);

  if (PermutationVector.template Get<FEnableModulatedImage>() &&
      !allowModulatedImage)
    return false;

  if (PermutationVector.template Get<FEnableAngularGradient>() &&
      !allowAngularGradient)
    return false;
  const bool bAtomicBufferOnly = IsTargetMetal(Parameters) ||
                                 RivePlatformForcesAtomicBuffer(Parameters);

  if (isAtomicBuffer && !bAtomicBufferOnly)
    return false;

  if (!isAtomicBuffer && bAtomicBufferOnly)
    return false;

  if (PermutationVector.template Get<FCoalescedPlsResolveAndTransfer>() &&
      !isResolve)
    return false;

  if (PermutationVector.template Get<FEnableHSLBlendMode>() &&
      !PermutationVector.template Get<FEnableAdvanceBlend>())
  {
    return false;
  }

  if (PermutationVector.template Get<FEnableEvenOdd>() &&
      PermutationVector.template Get<FEnableClockwiseFill>())
  {
    return false;
  }

  if (PermutationVector.template Get<FEnableFixedFunctionColorOutput>() &&
      PermutationVector.template Get<FEnableAdvanceBlend>())
  {
    return false;
  }

  if (PermutationVector.template Get<FCoalescedPlsResolveAndTransfer>() &&
      PermutationVector.template Get<FEnableFixedFunctionColorOutput>())
  {
    return false;
  }

  UE_LOG(
      LogRiveShaderCompiler,
      VeryVerbose,
      TEXT("Building Permutation %i for FRiveRDGPathPixelShader"),
      Parameters.PermutationId)
  return true;
}

template <typename ShaderClass>
bool ShouldCompilePixelMSAAPermutation(
    const FShaderPermutationParameters& Parameters)
{
  return RiveShouldCompilePixelPermutation<ShaderClass>(
      Parameters,
      rive::PixelPermutationFlags::allowModulatedImage |
          rive::PixelPermutationFlags::allowAngularGradient);
}

class FRiveBasePixelShader : public FGlobalShader
{
public:
  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);
};

class FRiveBaseVertexShader : public FGlobalShader
{
public:
  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);
};

RIVELITERENDERER_API bool RivePlatformWantsBindless(EShaderPlatform Platform);

RIVELITERENDERER_API void ModifyMSAAPathVertexShaderEnvironment(
    const FShaderPermutationParameters& Parameters,
    FShaderCompilerEnvironment& Environment);

class FRiveRDGGradientPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGGradientPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGGradientPixelShader,
      FRiveBasePixelShader);
  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
  SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
  END_SHADER_PARAMETER_STRUCT()
};

class FRiveRDGGradientVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGGradientVertexShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGGradientVertexShader,
      FRiveBaseVertexShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
  SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
  END_SHADER_PARAMETER_STRUCT()
};

class FRiveRDGTessPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGTessPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGTessPixelShader, FRiveBasePixelShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
  SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
  END_SHADER_PARAMETER_STRUCT()

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);
};

class FRiveRDGTessVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGTessVertexShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGTessVertexShader, FRiveBaseVertexShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
#if !UE_VERSION_OLDER_THAN(5, 5, 0) && !RIVE_FORCE_USE_GENERATED_UNIFORMS
  SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
  SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, GLSL_pathBuffer_raw)
  SHADER_PARAMETER_RDG_BUFFER_SRV(
      StructuredBuffer<uint4>,
      GLSL_contourBuffer_raw)
  SHADER_PARAMETER_RDG_TEXTURE(
      Texture2DArray<float>,
      GLSL_gaussianIntegralTexture_raw)
  SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)

  END_SHADER_PARAMETER_STRUCT()
};

// Atomic Shaders

class FRiveRDGPathPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGPathPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGPathPixelShader, FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGPathPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveABRDGPathPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveABRDGPathPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveABRDGPathPixelShader, FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGPathPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isAtomicBuffer |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGPathVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGPathVertexShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGPathVertexShader, FRiveBaseVertexShader);
  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGInteriorTrianglesPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGInteriorTrianglesPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGInteriorTrianglesPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGInteriorTrianglesPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveABRDGInteriorTrianglesPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveABRDGInteriorTrianglesPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveABRDGInteriorTrianglesPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGInteriorTrianglesPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isAtomicBuffer |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGInteriorTrianglesVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGInteriorTrianglesVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGInteriorTrianglesVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGAtlasBlitPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGAtlasBlitPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtlasBlitPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGInteriorTrianglesPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveABRDGAtlasBlitPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveABRDGAtlasBlitPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveABRDGAtlasBlitPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGInteriorTrianglesPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isAtomicBuffer |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGAtlasBlitVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGAtlasBlitVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtlasBlitVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGImageRectPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGImageRectPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageRectPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGImageRectPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveABRDGImageRectPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveABRDGImageRectPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveABRDGImageRectPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGImageRectPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isAtomicBuffer |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGImageRectVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGImageRectVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageRectVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGImageMeshPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGImageMeshPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageMeshPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGImageMeshPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::none);
  }
};

class FRiveABRDGImageMeshPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveABRDGImageMeshPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveABRDGImageMeshPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGImageMeshPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isAtomicBuffer);
  }
};

class FRiveRDGImageMeshVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGImageMeshVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageMeshVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGAtomicResolvePixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGAtomicResolvePixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtomicResolvePixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGAtomicResolvePixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isResolve);
  }
};

class FRiveABRDGAtomicResolvePixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveABRDGAtomicResolvePixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveABRDGAtomicResolvePixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniformsAtomicBuffers;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<FRiveRDGAtomicResolvePixelShader>(
        Parameters,
        rive::PixelPermutationFlags::isResolve |
            rive::PixelPermutationFlags::isAtomicBuffer);
  }
};

class FRiveRDGAtomicResolveVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGAtomicResolveVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtomicResolveVertexShader,
      FRiveBaseVertexShader);

  USE_ATOMIC_VERTEX_PERMUTATIONS

  using FParameters = FRiveVertexDrawUniforms;
};

// Raster Ordered Shaders

class FRiveRDGRasterOrderPathPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderPathPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderPathPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGRasterOrderPathPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowModulatedImage |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGRasterOrderPathVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderPathVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderPathVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGRasterOrderInteriorTrianglesPixelShader
    : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderInteriorTrianglesPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderInteriorTrianglesPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGRasterOrderInteriorTrianglesPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowModulatedImage |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGRasterOrderInteriorTrianglesVertexShader
    : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderInteriorTrianglesVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderInteriorTrianglesVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGRasterOrderImageMeshPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderImageMeshPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderImageMeshPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGRasterOrderImageMeshPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::none);
  }
};

class FRiveRDGRasterOrderImageMeshVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderImageMeshVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderImageMeshVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGRasterOrderAtlasBlitPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderAtlasBlitPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderAtlasBlitPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRivePixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return RiveShouldCompilePixelPermutation<
        FRiveRDGRasterOrderAtlasBlitPixelShader>(
        Parameters,
        rive::PixelPermutationFlags::allowModulatedImage |
            rive::PixelPermutationFlags::allowAngularGradient);
  }
};

class FRiveRDGRasterOrderAtlasBlitVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGRasterOrderAtlasBlitVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGRasterOrderAtlasBlitVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

// MSAA Shaders

class FRiveRDGAtlasBlitMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGAtlasBlitMSAAVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtlasBlitMSAAVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGAtlasBlitMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGAtlasBlitMSAAPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGAtlasBlitMSAAPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRiveMSAAPixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return ShouldCompilePixelMSAAPermutation<FRiveRDGAtlasBlitMSAAPixelShader>(
        Parameters);
  }
};

class FRiveRDGImageMeshMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGImageMeshMSAAVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageMeshMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS
};

class FRiveRDGImageMeshMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGImageMeshMSAAPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGImageMeshMSAAPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRiveMSAAPixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return ShouldCompilePixelMSAAPermutation<FRiveRDGImageMeshMSAAPixelShader>(
        Parameters);
  }
};

class FRiveRDGPathMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGPathMSAAVertexShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGPathMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters& Parameters,
      FShaderCompilerEnvironment& Environment)
  {
    ModifyMSAAPathVertexShaderEnvironment(Parameters, Environment);
  }
};

class FRiveRDGFillMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGFillMSAAVertexShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGFillMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters& Parameters,
      FShaderCompilerEnvironment& Environment)
  {
    ModifyMSAAPathVertexShaderEnvironment(Parameters, Environment);
  }
};

class FRiveRDGPathMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(FRiveRDGPathMSAAPixelShader, RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGPathMSAAPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRiveMSAAPixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return ShouldCompilePixelMSAAPermutation<FRiveRDGPathMSAAPixelShader>(
        Parameters);
  }
};

class FRiveRDGPolarStrokeMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGPolarStrokeMSAAVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGPolarStrokeMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters& Parameters,
      FShaderCompilerEnvironment& Environment)
  {
    ModifyMSAAPathVertexShaderEnvironment(Parameters, Environment);
  }
};

class FRiveRDGHairlineStrokeMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGHairlineStrokeMSAAVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGHairlineStrokeMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;

  USE_ATOMIC_VERTEX_PERMUTATIONS

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters& Parameters,
      FShaderCompilerEnvironment& Environment)
  {
    ModifyMSAAPathVertexShaderEnvironment(Parameters, Environment);
  }
};

class FRiveRDGPolarStrokeMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGPolarStrokeMSAAPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGPolarStrokeMSAAPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRiveMSAAPixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return ShouldCompilePixelMSAAPermutation<
        FRiveRDGPolarStrokeMSAAPixelShader>(Parameters);
  }
};

class FRiveRDGHairlineStrokeMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGHairlineStrokeMSAAPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGHairlineStrokeMSAAPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRiveMSAAPixelDrawUniforms;

  USE_ATOMIC_PIXEL_PERMUTATIONS

  static bool ShouldCompilePermutation(
      const FShaderPermutationParameters& Parameters)
  {
    return ShouldCompilePixelMSAAPermutation<
        FRiveRDGHairlineStrokeMSAAPixelShader>(Parameters);
  }
};

class FRiveRDGStencilMSAAVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGStencilMSAAVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGStencilMSAAVertexShader,
      FRiveBaseVertexShader);
  using FParameters = FRiveMSAAVertexDrawUniforms;
};

class FRiveRDGStencilMSAAPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGStencilMSAAPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGStencilMSAAPixelShader,
      FRiveBasePixelShader);
  using FParameters = FRiveMSAAPixelDrawUniforms;
};

// Subpass read variants of the msaa pixel shaders. These are separate shader
// types rather than a permutation, because a permutation bit here pushes the
// msaa shaders past unreal's permutation limit.

// True where the msaa shaders were cooked to texel-fetch the live target.
RIVELITERENDERER_API bool RiveCookedReadAttachmentInPlace();

// r.rive.ReadAttachmentInPlace. Owned here so it is registered before the
// global shader map compiles.
RIVELITERENDERER_API int32 RiveGetReadAttachmentInPlace();

RIVELITERENDERER_API bool RivePlatformSupportsSubpassLoad(
    const FShaderPermutationParameters& Parameters);

RIVELITERENDERER_API void ModifyMSAASubpassShaderEnvironment(
    const FShaderPermutationParameters& Parameters,
    FShaderCompilerEnvironment& Environment);

#define RIVE_MSAA_SUBPASS_PIXEL_SHADER(NAME, BASE)                             \
  class NAME : public FRiveBasePixelShader                                     \
  {                                                                            \
  public:                                                                      \
    DECLARE_EXPORTED_GLOBAL_SHADER(NAME, RIVELITERENDERER_API);                     \
    SHADER_USE_PARAMETER_STRUCT(NAME, FRiveBasePixelShader);                   \
    using FParameters = FRiveMSAAPixelDrawUniforms;                            \
                                                                               \
    USE_ATOMIC_PIXEL_PERMUTATIONS                                              \
                                                                               \
    static bool ShouldCompilePermutation(                                      \
        const FShaderPermutationParameters& Parameters)                        \
    {                                                                          \
      /* The dst color read only exists under advanced blend with a non        \
         fixed function color output, so every other permutation would         \
         compile to exactly the base shader.*/                                 \
      FPermutationDomain Permutation(Parameters.PermutationId);                \
      if (!Permutation.template Get<FEnableAdvanceBlend>() ||                  \
          Permutation.template Get<FEnableFixedFunctionColorOutput>())         \
      {                                                                        \
        return false;                                                          \
      }                                                                        \
      return RivePlatformSupportsSubpassLoad(Parameters) &&                    \
             ShouldCompilePixelMSAAPermutation<BASE>(Parameters);              \
    }                                                                          \
                                                                               \
    static void ModifyCompilationEnvironment(                                  \
        const FShaderPermutationParameters& Parameters,                        \
        FShaderCompilerEnvironment& Environment)                               \
    {                                                                          \
      ModifyMSAASubpassShaderEnvironment(Parameters, Environment);             \
    }                                                                          \
  };

RIVE_MSAA_SUBPASS_PIXEL_SHADER(
    FRiveRDGPathMSAASubpassPixelShader,
    FRiveRDGPathMSAAPixelShader)
RIVE_MSAA_SUBPASS_PIXEL_SHADER(
    FRiveRDGAtlasBlitMSAASubpassPixelShader,
    FRiveRDGAtlasBlitMSAAPixelShader)
RIVE_MSAA_SUBPASS_PIXEL_SHADER(
    FRiveRDGImageMeshMSAASubpassPixelShader,
    FRiveRDGImageMeshMSAAPixelShader)
RIVE_MSAA_SUBPASS_PIXEL_SHADER(
    FRiveRDGPolarStrokeMSAASubpassPixelShader,
    FRiveRDGPolarStrokeMSAAPixelShader)
RIVE_MSAA_SUBPASS_PIXEL_SHADER(
    FRiveRDGHairlineStrokeMSAASubpassPixelShader,
    FRiveRDGHairlineStrokeMSAAPixelShader)

RIVELITERENDERER_API bool RivePlatformSupportsPixelShaderUAVs(
    const FShaderPermutationParameters& Parameters);

RIVELITERENDERER_API void ModifyMSAAUavShaderEnvironment(
    const FShaderPermutationParameters& Parameters,
    FShaderCompilerEnvironment& Environment);

#define RIVE_MSAA_UAV_PIXEL_SHADER(NAME, BASE)                                 \
  class NAME : public FRiveBasePixelShader                                     \
  {                                                                            \
  public:                                                                      \
    DECLARE_EXPORTED_GLOBAL_SHADER(NAME, RIVELITERENDERER_API);                     \
    SHADER_USE_PARAMETER_STRUCT(NAME, FRiveBasePixelShader);                   \
    using FParameters = FRiveMSAAPixelDrawUniforms;                            \
                                                                               \
    USE_ATOMIC_PIXEL_PERMUTATIONS                                              \
                                                                               \
    static bool ShouldCompilePermutation(                                      \
        const FShaderPermutationParameters& Parameters)                        \
    {                                                                          \
      /* Same dst color read set as the subpass variants: only advanced        \
         blend with a non fixed function color output reads dst. */            \
      FPermutationDomain Permutation(Parameters.PermutationId);                \
      if (!Permutation.template Get<FEnableAdvanceBlend>() ||                  \
          Permutation.template Get<FEnableFixedFunctionColorOutput>())         \
      {                                                                        \
        return false;                                                          \
      }                                                                        \
      return RivePlatformSupportsPixelShaderUAVs(Parameters) &&                \
             ShouldCompilePixelMSAAPermutation<BASE>(Parameters);              \
    }                                                                          \
                                                                               \
    static void ModifyCompilationEnvironment(                                  \
        const FShaderPermutationParameters& Parameters,                        \
        FShaderCompilerEnvironment& Environment)                               \
    {                                                                          \
      ModifyMSAAUavShaderEnvironment(Parameters, Environment);                 \
    }                                                                          \
  };

RIVE_MSAA_UAV_PIXEL_SHADER(
    FRiveRDGPathMSAAUavPixelShader,
    FRiveRDGPathMSAAPixelShader)
RIVE_MSAA_UAV_PIXEL_SHADER(
    FRiveRDGAtlasBlitMSAAUavPixelShader,
    FRiveRDGAtlasBlitMSAAPixelShader)
RIVE_MSAA_UAV_PIXEL_SHADER(
    FRiveRDGImageMeshMSAAUavPixelShader,
    FRiveRDGImageMeshMSAAPixelShader)
RIVE_MSAA_UAV_PIXEL_SHADER(
    FRiveRDGPolarStrokeMSAAUavPixelShader,
    FRiveRDGPolarStrokeMSAAPixelShader)
RIVE_MSAA_UAV_PIXEL_SHADER(
    FRiveRDGHairlineStrokeMSAAUavPixelShader,
    FRiveRDGHairlineStrokeMSAAPixelShader)

// Atlas Render

class FRiveRDGDrawAtlasVertexShader : public FRiveBaseVertexShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGDrawAtlasVertexShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGDrawAtlasVertexShader,
      FRiveBaseVertexShader);

  using FParameters = FRiveVertexDrawUniforms;
};

BEGIN_SHADER_PARAMETER_STRUCT(FAtlasDrawUniforms, RIVELITERENDERER_API)
#if !UE_VERSION_OLDER_THAN(5, 5, 0)
SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FFlushUniforms, GLSL_FlushUniforms_raw)
#endif
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_gaussianIntegralTexture_raw)
SHADER_PARAMETER_SAMPLER(SamplerState, gaussianIntegralSampler)
END_SHADER_PARAMETER_STRUCT()

class FRiveRDGDrawAtlasFillPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGDrawAtlasFillPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGDrawAtlasFillPixelShader,
      FRiveBasePixelShader);

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);

  using FParameters = FAtlasDrawUniforms;
};

class FRiveRDGDrawAtlasStrokePixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGDrawAtlasStrokePixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGDrawAtlasStrokePixelShader,
      FRiveBasePixelShader);

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);

  using FParameters = FAtlasDrawUniforms;
};

class FRiveBltTextureAsDrawVertexShader : public FGlobalShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveBltTextureAsDrawVertexShader,
      RIVELITERENDERER_API);

  static void ModifyCompilationEnvironment(
      const FShaderPermutationParameters&,
      FShaderCompilerEnvironment&);
};
class FEnableMSAASourceTexture : SHADER_PERMUTATION_BOOL("SOURCE_TEXTURE_MSAA");

BEGIN_SHADER_PARAMETER_STRUCT(FRiveBltTextureDrawUniforms, RIVELITERENDERER_API)
SHADER_PARAMETER_RDG_TEXTURE(Texture2D, GLSL_sourceTexture_raw)
END_SHADER_PARAMETER_STRUCT()

class FRiveBltTextureAsDrawPixelShader : public FRiveBasePixelShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveBltTextureAsDrawPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveBltTextureAsDrawPixelShader,
      FRiveBasePixelShader);

  using FParameters = FRiveBltTextureDrawUniforms;
  using FPermutationDomain = TShaderPermutationDomain<FEnableMSAASourceTexture>;
};

/*
 * The shader will convert a PF_R32 texture to PF_R8G8B8A8 in order to visualize
 * it. It does so by writing SourceTexture to the current rendertarget color
 * float4(value, 0, 0, 1)
 */
class FRiveRDGBltU32AsF4PixelShader : public FGlobalShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGBltU32AsF4PixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGBltU32AsF4PixelShader, FGlobalShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
  SHADER_PARAMETER_RDG_TEXTURE(Texture2D, SourceTexture)
  RENDER_TARGET_BINDING_SLOTS()
  END_SHADER_PARAMETER_STRUCT()
};

/*
 * The shader will convert a PF_R32G32B32A32_UINT texture to PF_R8G8B8A8 in
 * order to visualize it. It does so by writing SourceTexture to the current
 * rendertarget color float4( float(val.r), float(val.g), float(val.b), 1.0 );
 */
class FRiveRDGBltU324AsF4PixelShader : public FGlobalShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGBltU324AsF4PixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGBltU324AsF4PixelShader, FGlobalShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
  SHADER_PARAMETER_RDG_TEXTURE(Texture2D, SourceTexture)
  RENDER_TARGET_BINDING_SLOTS()
  END_SHADER_PARAMETER_STRUCT()
};

/*
 * The shader will convert a PF_R32G32B32A32_UINT texture to PF_R8G8B8A8 in
 * order to visualize it. It does so by writing SourceTexture to the current
 * rendertarget color float4( float(val.r), float(val.g), float(val.b), 1.0 );
 */
class FRiveRDGBltR16FAsF4PixelShader : public FGlobalShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGBltR16FAsF4PixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(FRiveRDGBltR16FAsF4PixelShader, FGlobalShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
  SHADER_PARAMETER_RDG_TEXTURE(Texture2D, SourceTexture)
  SHADER_PARAMETER_SAMPLER(SamplerState, SourceSampler)
  SHADER_PARAMETER(UE::HLSL::uint2, ViewSize)
  RENDER_TARGET_BINDING_SLOTS()
  END_SHADER_PARAMETER_STRUCT()
};

/*
 * The shader will convert a uint2 buffer to PF_R8G8B8A8 in order to visualize
 * it. it does so in a slightly more intelligent way by passing the values of
 * buffer through sin and cos when writing it to the bound render target
 */
class FRiveRDGVisualizeBufferPixelShader : public FGlobalShader
{
public:
  DECLARE_EXPORTED_GLOBAL_SHADER(
      FRiveRDGVisualizeBufferPixelShader,
      RIVELITERENDERER_API);
  SHADER_USE_PARAMETER_STRUCT(
      FRiveRDGVisualizeBufferPixelShader,
      FGlobalShader);

  BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
  SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<uint2>, SourceBuffer)
  SHADER_PARAMETER(UE::HLSL::uint2, ViewSize)
  SHADER_PARAMETER(UE::HLSL::uint, BufferSize)
  RENDER_TARGET_BINDING_SLOTS()
  END_SHADER_PARAMETER_STRUCT()
};
