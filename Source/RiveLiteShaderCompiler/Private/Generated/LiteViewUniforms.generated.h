// Generated from Epic UE source; Copyright Epic Games, Inc. All Rights Reserved.
#pragma once
#include "CoreMinimal.h"
#include "ShaderParameterStruct.h"
#include "ShaderParameterMacros.h"
inline constexpr int TVC_MAX = 2; // SceneView.h ETranslucencyVolumeCascade
#define MAX_PHYSICS_FIELD_TARGETS 32
#define NUM_ATMOSPHERE_LIGHTS 2
#define SKY_IRRADIANCE_ENVIRONMENT_MAP_VEC4_COUNT 8
#define VIEW_UNIFORM_BUFFER_MEMBER_TABLE \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, TranslatedWorldToClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, RelativeWorldToClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ClipToRelativeWorld)  \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, TranslatedWorldToView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ViewToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, TranslatedWorldToCameraView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, CameraViewToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ViewToClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ViewToClipNoAA) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ClipToView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ClipToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, SVPositionToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ScreenToRelativeWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ScreenToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, MobileMultiviewShadowTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, MobileMultiviewDecalTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, FirstPersonTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevFirstPersonTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, InvFirstPersonTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, ViewOriginHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector3f, ViewForward, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector3f, ViewUp, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector3f, ViewRight, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(FVector3f, HMDViewNoRollUp, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(FVector3f, HMDViewNoRollRight, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, InvDeviceZToWorldZTransform) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(FVector4f, ScreenPositionScaleBias, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, ViewOriginLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, TranslatedWorldCameraOrigin) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, WorldViewOriginHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, WorldViewOriginLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PreViewTranslationHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PreViewTranslationLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevViewToClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevClipToView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevTranslatedWorldToClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevTranslatedWorldToView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevViewToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevTranslatedWorldToCameraView) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevCameraViewToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevTranslatedWorldCameraOrigin) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevWorldCameraOriginHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevWorldCameraOriginLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevWorldViewOriginHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevWorldViewOriginLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevPreViewTranslationHigh) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevPreViewTranslationLow) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, ViewTilePosition) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, RelativeWorldCameraOriginTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, RelativeWorldViewOriginTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, RelativePreViewTranslationTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevRelativeWorldCameraOriginTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, PrevRelativeWorldViewOriginTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, RelativePrevPreViewTranslationTO) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevClipToRelativeWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, PrevScreenToTranslatedWorld) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ClipToPrevClip) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FMatrix44f, ClipToPrevClipWithAA) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, TemporalAAJitter) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, TemporalLODTranslatedWorldViewOriginZero) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, TemporalLODTranslatedWorldViewOriginOne) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, TemporalLODTransitionAlpha) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, TemporalLODRandomRange) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, GlobalClippingPlane) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, FieldOfViewWideAngles) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, PrevFieldOfViewWideAngles) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, FirstPersonFieldOfViewWideAngles) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, PrevFirstPersonFieldOfViewWideAngles) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(FVector4f, ViewRectMin, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, ViewSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FUintVector4, ViewRectMinAndSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, LightProbeSizeRatioAndInvSizeRatio) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, BufferSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, BufferBilinearUVMinMax) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, ScreenToViewSpace) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, BufferToSceneTextureScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, ResolutionFractionAndInv) \
	VIEW_UNIFORM_BUFFER_MEMBER(int32, NumSceneColorMSAASamples) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(float, ProjectionDepthThicknessScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, PreExposure) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, OneOverPreExposure) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector4f, DiffuseOverrideParameter, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector4f, SpecularOverrideParameter, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector4f, NormalOverrideParameter, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector2f, RoughnessOverrideParameter, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector2f, AmbientOcclusionOverrideParameter, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, PrevFrameGameTime) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, PrevFrameRealTime) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, OutOfBoundsMask, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector3f, WorldCameraMovementSinceLastFrame) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, CullingSign) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(float, NearPlane, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(float, OrthoFarPlane) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GameTime) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, RealTime) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DeltaTime) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MaterialTextureMipBias) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MaterialTextureDerivativeMultiply) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, Random) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, FrameNumber) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, FrameCounter) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, StateFrameIndexMod8) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, StateFrameIndex) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, StateOutputFrameIndex) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, DebugViewModeMask) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, WorldIsPaused) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, CameraCut, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, UnlitViewmodeMask, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FLinearColor, DirectionalLightColor, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(FVector3f, DirectionalLightDirection, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, TranslucencyLightingVolumeMin, TVC_MAX) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, TranslucencyLightingVolumeInvSize, TVC_MAX) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, TemporalAAParams) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, CircleDOFParams) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldSensorWidth) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldFocalDistance) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldFocalLength) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldFocalRegion) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldNearTransitionRegion) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DepthOfFieldFarTransitionRegion) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MotionBlurNormalizedToPixel) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GeneralPurposeTweak) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GeneralPurposeTweak2) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, DemosaicVposOffset, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DecalDepthBias) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, SceneColorTextureFormatQuantizationError) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, IndirectLightingColorScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, PrecomputedIndirectLightingColorScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, PrecomputedIndirectSpecularColorScale) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, AtmosphereLightDirection, NUM_ATMOSPHERE_LIGHTS) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FLinearColor, AtmosphereLightIlluminanceOnGroundPostTransmittance, NUM_ATMOSPHERE_LIGHTS) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FLinearColor, AtmosphereLightIlluminanceOuterSpace, NUM_ATMOSPHERE_LIGHTS) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FLinearColor, AtmosphereLightDiscLuminance, NUM_ATMOSPHERE_LIGHTS) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, AtmosphereLightDiscCosHalfApexAngle_PPTrans, NUM_ATMOSPHERE_LIGHTS) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SkyViewLutSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, SkyCameraTranslatedWorldOrigin) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SkyPlanetTranslatedWorldCenterAndViewHeight) \
	VIEW_UNIFORM_BUFFER_MEMBER(FMatrix44f, SkyViewLutReferential) \
	VIEW_UNIFORM_BUFFER_MEMBER(FLinearColor, SkyAtmosphereSkyLuminanceFactor) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmospherePresentInScene) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereHeightFogContribution) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereBottomRadiusKm) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereTopRadiusKm) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SkyAtmosphereCameraAerialPerspectiveVolumeSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereAerialPerspectiveStartDepthKm) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereCameraAerialPerspectiveVolumeDepthResolution) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereCameraAerialPerspectiveVolumeDepthResolutionInv) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereCameraAerialPerspectiveVolumeDepthSliceLengthKm) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereCameraAerialPerspectiveVolumeDepthSliceLengthKmInv) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyAtmosphereApplyCameraAerialPerspectiveVolume) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, NormalCurvatureToRoughnessScaleBias) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, RenderingReflectionCaptureMask) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, RealTimeReflectionCapture) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, RealTimeReflectionCapturePreExposure) \
	VIEW_UNIFORM_BUFFER_MEMBER(FLinearColor, AmbientCubemapTint) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, AmbientCubemapIntensity) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyLightApplyPrecomputedBentNormalShadowingFlag) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyLightAffectReflectionFlag) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyLightAffectGlobalIlluminationFlag) \
	VIEW_UNIFORM_BUFFER_MEMBER(FLinearColor, SkyLightColor) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SkyLightVolumetricScatteringIntensity) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MobilePreviewMode) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(float, HMDEyePaddingOffset) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, ReflectionCubemapMaxMip, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER_EX(float, AmbientLightingVolumeDiffuseMipCount, EShaderPrecisionModifier::Half) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, ShowDecalsMask) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, DistanceFieldAOSpecularOcclusionMode) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, IndirectCapsuleSelfShadowingIntensity) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, ReflectionEnvironmentRoughnessMixingScaleBiasAndLargestWeight) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(int32, StereoPassIndex) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, GlobalVolumeTranslatedCenterAndExtent, 6) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, GlobalVolumeTranslatedWorldToUVAddAndMul, 6) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, GlobalDistanceFieldMipTranslatedWorldToUVScale, 6) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, GlobalDistanceFieldMipTranslatedWorldToUVBias, 6) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GlobalDistanceFieldMipFactor) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GlobalDistanceFieldMipTransition) \
	VIEW_UNIFORM_BUFFER_MEMBER(int32, GlobalDistanceFieldClipmapSizeInPages) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, GlobalDistanceFieldInvPageAtlasSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, GlobalDistanceFieldInvCoverageAtlasSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GlobalVolumeDimension) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, GlobalVolumeTexelSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MaxGlobalDFAOConeDistance) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, NumGlobalSDFClipmaps) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, CoveredExpandSurfaceScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, NotCoveredExpandSurfaceScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, NotCoveredMinStepScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DitheredTransparencyStepThreshold) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, DitheredTransparencyTraceThreshold) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, ViewportScaleUI) \
	VIEW_UNIFORM_BUFFER_MEMBER(FIntPoint, CursorPosition) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, bCheckerboardSubsurfaceProfileRendering) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricFogGridSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricFogInvGridSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricFogGridZParams) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogSVPosToVolumeUV) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogViewGridUVToPrevViewRectUV) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogPrevViewGridRectUVToResourceUV) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogPrevUVMax) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogPrevUVMaxForTemporalBlend) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricFogPrevResourceGridSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogScreenToResourceUV) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, VolumetricFogUVMax) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, VolumetricFogMaxDistance) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricLightmapWorldToUVScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricLightmapWorldToUVAdd) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricLightmapIndirectionTextureSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, VolumetricLightmapBrickSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, VolumetricLightmapBrickTexelSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, IndirectLightingCacheShowFlag) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, EyeToPixelSpreadAngle) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FVector4f, XRPassthroughCameraUVs, 2) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, GlobalVirtualTextureMipBias) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureFeedbackBufferSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureFeedbackShift) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureFeedbackMask) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureFeedbackJitterOffset) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureFeedbackSampleOffset) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, VirtualTextureExtendedDebugBufferSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(int32, FarShadowStaticMeshLODBias) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MinRoughness) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, HairRenderInfo) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, EnableSkyLight) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, HairRenderInfoBits) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, HairComponents) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, bSubsurfacePostprocessEnabled) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SSProfilesTextureSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SSProfilesPreIntegratedTextureSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SSProfilesPreIntegratedBRDFSliceIndex) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, SpecularProfileTextureSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector4f, ToonProfileTextureSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector2f, ToonProfileDitherPatternSizeAndInvSize) \
	VIEW_UNIFORM_BUFFER_MEMBER(FVector3f, PhysicsFieldClipmapCenter) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, PhysicsFieldClipmapDistance) \
	VIEW_UNIFORM_BUFFER_MEMBER(int, PhysicsFieldClipmapResolution) \
	VIEW_UNIFORM_BUFFER_MEMBER(int, PhysicsFieldClipmapExponent) \
	VIEW_UNIFORM_BUFFER_MEMBER(int, PhysicsFieldClipmapCount) \
	VIEW_UNIFORM_BUFFER_MEMBER(int, PhysicsFieldTargetCount) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FIntVector4, PhysicsFieldTargets, MAX_PHYSICS_FIELD_TARGETS) \
	VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(FIntVector4, PhysicsFieldTargetMappings, MAX_PHYSICS_FIELD_TARGETS) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(uint32, GPUSceneViewId) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, ViewResolutionFraction) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, SubSurfaceColorAsTransmittanceAtDistanceInMeters) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, TanAndInvTanHalfFOV) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, PrevTanAndInvTanHalfFOV) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, FirstPersonTanAndInvTanHalfFOV) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, PrevFirstPersonTanAndInvTanHalfFOV) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector2f, WorldDepthToPixelWorldRadius) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, ScreenRayLengthMultiplier) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, GlintLUTParameters0) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(FVector4f, GlintLUTParameters1) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(float, FirstPersonScale) \
	VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(float, PrevFirstPersonScale) \
	VIEW_UNIFORM_BUFFER_MEMBER(float, MaterialMaxEmissiveValue) \
	VIEW_UNIFORM_BUFFER_MEMBER(int32, PostVolumeUserFlags) \
	VIEW_UNIFORM_BUFFER_MEMBER(FIntVector4, EnvironmentComponentsFlags) \
	VIEW_UNIFORM_BUFFER_MEMBER(uint32, bPrimitiveAlphaHoldoutEnabled) \

/** The uniform shader parameters associated with a view. */
#define VIEW_UNIFORM_BUFFER_MEMBER(type, identifier) \
	SHADER_PARAMETER(type, identifier)

#define VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(type, identifier) \
	SHADER_PARAMETER(type, identifier)

#define VIEW_UNIFORM_BUFFER_MEMBER_EX(type, identifier, precision) \
	SHADER_PARAMETER_EX(type, identifier, precision)

#define VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(type, identifier, precision) \
	SHADER_PARAMETER_EX(type, identifier, precision)

#define VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(type, identifier, dimension) \
	SHADER_PARAMETER_ARRAY(type, identifier, [dimension])

#define VIEW_UNIFORM_BUFFER_MEMBER_ARRAY_PER_VIEW(type, identifier, dimension) \
	SHADER_PARAMETER_ARRAY(type, identifier, [dimension])

BEGIN_GLOBAL_SHADER_PARAMETER_STRUCT_WITH_CONSTRUCTOR(FViewUniformShaderParameters, )

	VIEW_UNIFORM_BUFFER_MEMBER_TABLE

	// Same as Wrap_WorldGroupSettings and Clamp_WorldGroupSettings, but with mipbias=MaterialTextureMipBias.
	SHADER_PARAMETER_SAMPLER(SamplerState, MaterialTextureBilinearWrapedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, MaterialTextureBilinearClampedSampler)

	SHADER_PARAMETER_TEXTURE(Texture3D<uint4>, VolumetricLightmapIndirectionTexture) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickAmbientVector) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients0) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients1) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients2) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients3) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients4) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, VolumetricLightmapBrickSHCoefficients5) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, SkyBentNormalBrickTexture) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_TEXTURE(Texture3D, DirectionalLightShadowingBrickTexture) // FPrecomputedVolumetricLightmapLightingPolicy

	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapBrickAmbientVectorSampler) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler0) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler1) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler2) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler3) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler4) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, VolumetricLightmapTextureSampler5) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, SkyBentNormalTextureSampler) // FPrecomputedVolumetricLightmapLightingPolicy
	SHADER_PARAMETER_SAMPLER(SamplerState, DirectionalLightShadowingTextureSampler) // FPrecomputedVolumetricLightmapLightingPolicy

	SHADER_PARAMETER_TEXTURE(Texture3D, GlobalDistanceFieldPageAtlasTexture)
	SHADER_PARAMETER_TEXTURE(Texture3D, GlobalDistanceFieldCoverageAtlasTexture)
	SHADER_PARAMETER_TEXTURE(Texture3D<uint>, GlobalDistanceFieldPageTableTexture)
	SHADER_PARAMETER_TEXTURE(Texture3D, GlobalDistanceFieldMipTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, GlobalDistanceFieldPageAtlasTextureSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, GlobalDistanceFieldCoverageAtlasTextureSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, GlobalDistanceFieldMipTextureSampler)

	SHADER_PARAMETER_TEXTURE(Texture2D, AtmosphereTransmittanceTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, AtmosphereTransmittanceTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, AtmosphereIrradianceTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, AtmosphereIrradianceTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture3D, AtmosphereInscatterTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, AtmosphereInscatterTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, PerlinNoiseGradientTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, PerlinNoiseGradientTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture3D, PerlinNoise3DTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, PerlinNoise3DTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D<uint>, SobolSamplingTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedPointWrappedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedPointClampedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedBilinearWrappedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedBilinearClampedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedBilinearAnisoClampedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedTrilinearWrappedSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SharedTrilinearClampedSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, PreIntegratedBRDF)
	SHADER_PARAMETER_SAMPLER(SamplerState, PreIntegratedBRDFSampler)
	SHADER_PARAMETER_UNIFORM_BLOCK(float4, SkyIrradianceEnvironmentMap, SKY_IRRADIANCE_ENVIRONMENT_MAP_VEC4_COUNT)
	// Atmosphere
	SHADER_PARAMETER_TEXTURE(Texture2D, TransmittanceLutTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, TransmittanceLutTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, SkyViewLutTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SkyViewLutTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture3D, CameraAerialPerspectiveVolume)
	SHADER_PARAMETER_SAMPLER(SamplerState, CameraAerialPerspectiveVolumeSampler)
	SHADER_PARAMETER_TEXTURE(Texture3D, CameraAerialPerspectiveVolumeMieOnly)
	SHADER_PARAMETER_SAMPLER(SamplerState, CameraAerialPerspectiveVolumeMieOnlySampler)
	SHADER_PARAMETER_TEXTURE(Texture3D, CameraAerialPerspectiveVolumeRayOnly)
	SHADER_PARAMETER_SAMPLER(SamplerState, CameraAerialPerspectiveVolumeRayOnlySampler)
	SHADER_PARAMETER_UNIFORM_BLOCK(float4, DistantSkyLightLutBufferSRV, 1)
	// Hair
	SHADER_PARAMETER_TEXTURE(Texture3D, HairScatteringLUTTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, HairScatteringLUTSampler)
	// GGX/Sheen LTC textures
	SHADER_PARAMETER_TEXTURE(Texture2D, GGXLTCMatTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, GGXLTCMatSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, GGXLTCAmpTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, GGXLTCAmpSampler)
	SHADER_PARAMETER_TEXTURE(Texture2D, SheenLTCTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SheenLTCSampler)
	// Energy conservation
	SHADER_PARAMETER(uint32, bShadingEnergyConservation)
	SHADER_PARAMETER(uint32, bShadingEnergyPreservation)
	SHADER_PARAMETER_TEXTURE(Texture2D<float2>, ShadingEnergyGGXSpecTexture)
	SHADER_PARAMETER_TEXTURE(Texture2D<float4>,  ShadingEnergyGGXMaxSpecTexture)
	SHADER_PARAMETER_TEXTURE(Texture3D<float2>, ShadingEnergyGGXGlassTexture)
	SHADER_PARAMETER_TEXTURE(Texture2D<float2>, ShadingEnergyClothSpecTexture)
	SHADER_PARAMETER_TEXTURE(Texture2D<float>, ShadingEnergyDiffuseTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, ShadingEnergySampler)
	// Glints
	SHADER_PARAMETER_TEXTURE(Texture2DArray<float4>, GlintTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, GlintSampler)
	// Simple volume texture
	SHADER_PARAMETER_TEXTURE(Texture3D<float>, SimpleVolumeTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SimpleVolumeTextureSampler)
	SHADER_PARAMETER_TEXTURE(Texture3D<float>, SimpleVolumeEnvTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SimpleVolumeEnvTextureSampler)
	// SSS
	SHADER_PARAMETER_TEXTURE(Texture2D, SSProfilesTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SSProfilesSampler)
	SHADER_PARAMETER_SAMPLER(SamplerState, SSProfilesTransmissionSampler)
	SHADER_PARAMETER_TEXTURE(Texture2DArray, SSProfilesPreIntegratedTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SSProfilesPreIntegratedSampler)
	// Specular Profile
	SHADER_PARAMETER_TEXTURE(Texture2DArray, SpecularProfileTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, SpecularProfileSampler)
	// Toon Profile texture
	SHADER_PARAMETER_TEXTURE(Texture2DArray, ToonProfileTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, ToonProfileSampler)
	// Water
	SHADER_PARAMETER_SRV(Buffer<float4>, WaterIndirection)
	SHADER_PARAMETER_SRV(Buffer<float4>, WaterData)
	SHADER_PARAMETER(int32, WaterInfoTextureViewIndex)
	// Rect light atlas
	SHADER_PARAMETER(FVector2f, RectLightAtlasSize)
	SHADER_PARAMETER(FUintVector2, RectLightAtlasSizeUint)
	SHADER_PARAMETER(float, RectLightAtlasMaxMipLevel)
	SHADER_PARAMETER_TEXTURE(Texture2D<float4>, RectLightAtlasTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, RectLightAtlasSampler)
	// IES atlas
	SHADER_PARAMETER(FVector4f, IESAtlasSizeAndInvSize)
	SHADER_PARAMETER_TEXTURE(Texture2DArray<float>, IESAtlasTexture)
	SHADER_PARAMETER_SAMPLER(SamplerState, IESAtlasSampler)
	// Landscape
	SHADER_PARAMETER_SAMPLER(SamplerState, LandscapeWeightmapSampler)
	SHADER_PARAMETER_SRV(Buffer<uint>, LandscapeIndirection)
	SHADER_PARAMETER_SRV(Buffer<float>, LandscapePerComponentData)

	SHADER_PARAMETER_UAV(RWStructuredBuffer<uint>, VTFeedbackBuffer)

	// Physics Field
	SHADER_PARAMETER_SRV(Buffer<float>, PhysicsFieldClipmapBuffer)
	SHADER_PARAMETER_SRV(Buffer<float>, PhysicsFieldNodesParams)
	SHADER_PARAMETER_SRV(Buffer<int>, PhysicsFieldNodesOffsets)
	SHADER_PARAMETER_SRV(Buffer<int>, PhysicsFieldTargetsOffsets)

	// Blue noise texture
	SHADER_PARAMETER_TEXTURE(Texture2D<float>, BlueNoiseScalarTexture)
	SHADER_PARAMETER(FIntVector, BlueNoiseDimensions)
	SHADER_PARAMETER(FIntVector, BlueNoiseModuloMasks)

	// Ray tracing
	SHADER_PARAMETER(FVector3f, TLASPreViewTranslationHigh)
	SHADER_PARAMETER(FVector3f, TLASPreViewTranslationLow)

END_GLOBAL_SHADER_PARAMETER_STRUCT()

#undef VIEW_UNIFORM_BUFFER_MEMBER
#undef VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW
#undef VIEW_UNIFORM_BUFFER_MEMBER_EX
#undef VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX
#undef VIEW_UNIFORM_BUFFER_MEMBER_ARRAY
#undef VIEW_UNIFORM_BUFFER_MEMBER_ARRAY_PER_VIEW

/** Copy of the view uniform shader parameters associated with a view for instanced stereo. */
#define INSTANCED_VIEW_COUNT 2

#define VIEW_UNIFORM_BUFFER_MEMBER(type, identifier) \
	SHADER_PARAMETER(type, identifier)

#define VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW(type, identifier) \
	SHADER_PARAMETER_ARRAY(TShaderParameterTypeInfo<type>::TInstancedType, identifier, [INSTANCED_VIEW_COUNT])

#define VIEW_UNIFORM_BUFFER_MEMBER_EX(type, identifier, precision) \
	SHADER_PARAMETER_EX(type, identifier, precision)

#define VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX(type, identifier, precision) \
	SHADER_PARAMETER_ARRAY_EX(TShaderParameterTypeInfo<type>::TInstancedType, identifier, [INSTANCED_VIEW_COUNT], precision)

#define VIEW_UNIFORM_BUFFER_MEMBER_ARRAY(type, identifier, dimension) \
	SHADER_PARAMETER_ARRAY(type, identifier, [dimension])

#define VIEW_UNIFORM_BUFFER_MEMBER_ARRAY_PER_VIEW(type, identifier, dimension) \
	SHADER_PARAMETER_ARRAY(type, identifier, [dimension * INSTANCED_VIEW_COUNT])

BEGIN_GLOBAL_SHADER_PARAMETER_STRUCT_WITH_CONSTRUCTOR(FInstancedViewUniformShaderParameters, )
	VIEW_UNIFORM_BUFFER_MEMBER_TABLE
END_GLOBAL_SHADER_PARAMETER_STRUCT()

#undef VIEW_UNIFORM_BUFFER_MEMBER
#undef VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW
#undef VIEW_UNIFORM_BUFFER_MEMBER_EX
#undef VIEW_UNIFORM_BUFFER_MEMBER_PER_VIEW_EX
#undef VIEW_UNIFORM_BUFFER_MEMBER_ARRAY
#undef VIEW_UNIFORM_BUFFER_MEMBER_ARRAY_PER_VIEW
#undef VIEW_UNIFORM_BUFFER_MEMBER_TABLE
