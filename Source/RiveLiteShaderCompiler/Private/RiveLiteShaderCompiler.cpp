// Offline-only compiler for the pinned UE RHI/RDG Rive prototype.
// Engine and Renderer are not linked. Scene View shader declarations are generated
// from the pinned source solely so unchanged RenderCore utility shaders can compile.
#include "RequiredProgramMainCPPInclude.h"

#include "DataDrivenShaderPlatformInfo.h"
#include "Dom/JsonObject.h"
#include "GlobalShader.h"
#include "HAL/IConsoleManager.h"
#include "Hash/xxhash.h"
#include "Interfaces/IShaderFormat.h"
#include "Interfaces/IShaderFormatModule.h"
#include "Interfaces/ITargetPlatform.h"
#include "Interfaces/ITargetPlatformManagerModule.h"
#include "IO/IoDispatcher.h"
#include "Misc/FileHelper.h"
#include "Misc/DelayedAutoRegister.h"
#include "Misc/LargeWorldRenderPosition.h"
#include "Misc/Paths.h"
#include "Serialization/ArchiveSavePackageDataBuffer.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryWriter.h"
#include "Serialization/MemoryReader.h"
#include "ShaderCompilerCore.h"
#include "ShaderCompilerJobTypes.h"
#include "ShaderCore.h"
#include "ShaderParameterMetadata.h"
#include "ShaderParameters.h"
#include "ShaderPlatformConfig.h"
#include "ShaderSymbolExport.h"
#include "RiveLiteRenderer.h"

#include "Generated/LiteViewUniforms.generated.h"
#include "Generated/LiteDrawRectangleUniforms.generated.h"

#if PLATFORM_LINUX
#include <execinfo.h>
#include <signal.h>
#include <unistd.h>
#endif

DEFINE_LOG_CATEGORY_STATIC(LogRiveLiteShaderCompiler, Log, All);
IMPLEMENT_APPLICATION(RiveLiteShaderCompiler, "RiveLiteShaderCompiler");

IMPLEMENT_STATIC_UNIFORM_BUFFER_SLOT(View);
IMPLEMENT_STATIC_UNIFORM_BUFFER_SLOT(InstancedView);
IMPLEMENT_STATIC_AND_SHADER_UNIFORM_BUFFER_STRUCT(FViewUniformShaderParameters, "View", View);
IMPLEMENT_STATIC_AND_SHADER_UNIFORM_BUFFER_STRUCT(FInstancedViewUniformShaderParameters, "InstancedView", InstancedView);
IMPLEMENT_GLOBAL_SHADER_PARAMETER_STRUCT(FDrawRectangleParameters, "DrawRectangleParameters");

#include "Generated/LiteInstancedStereo.generated.inl"

namespace
{
constexpr EShaderPlatform CompilePlatform = SP_VULKAN_SM5_LINUX;

#if PLATFORM_LINUX
void DumpFatalSignal(int Signal)
{
    constexpr char Message[] = "RiveLiteShaderCompiler fatal signal backtrace:\n";
    write(STDERR_FILENO, Message, sizeof(Message) - 1);
    void* Frames[40];
    const int Count = backtrace(Frames, UE_ARRAY_COUNT(Frames));
    backtrace_symbols_fd(Frames, Count, STDERR_FILENO);
    _exit(128 + Signal);
}
#endif

void EnsureIntCVar(const TCHAR* Name, int32 Value)
{
    if (!IConsoleManager::Get().FindConsoleVariable(Name))
    {
        IConsoleManager::Get().RegisterConsoleVariable(Name, Value,
            TEXT("Offline RiveLite shader compiler setting"), ECVF_ReadOnly);
    }
}

void RegisterOfflineCompilerCVars()
{
    // Pinned Engine/Private/ShaderCompiler/ShaderCompiler.cpp:419-515 defaults.
    // RenderCore's lazy symbol exporter consults these even for a symbol-free cook.
    for (const TCHAR* Name : {
        TEXT("r.Shaders.Symbols"), TEXT("r.Shaders.SymbolsInfo"),
        TEXT("r.Shaders.GenerateSymbols"), TEXT("r.Shaders.WriteSymbols"),
        TEXT("r.Shaders.AllowUniqueSymbols"), TEXT("r.Shaders.WriteSymbols.Zip"),
        TEXT("r.Shaders.ExtraData"), TEXT("r.Shaders.ForceOptimizeRaytracing")})
        EnsureIntCVar(Name, 0);
    EnsureIntCVar(TEXT("r.Shaders.Optimize"), 1);
    for (const TCHAR* Name : {
        TEXT("r.Shaders.SymbolPathOverride"), TEXT("r.Shaders.SymbolFileNameOverride"),
        TEXT("r.Shaders.ShaderTypeStatsFileNameOverride")})
    {
        if (!IConsoleManager::Get().FindConsoleVariable(Name))
            IConsoleManager::Get().RegisterConsoleVariable(Name, TEXT(""),
                TEXT("Pinned offline shader compiler symbol setting"), ECVF_ReadOnly);
    }
}

bool IsSelectedType(const FShaderType& Type, bool bAllRegistered)
{
    if (bAllRegistered) return true;
    const FString Filename(Type.GetShaderFilename());
    // Exact unchanged source files used by Rive and its RenderCore utility calls.
    static const TCHAR* UtilityFiles[] = {
        TEXT("/Engine/Private/Tools/FullscreenVertexShader.usf"),
        TEXT("/Engine/Private/Tools/DrawTexture.usf"),
        TEXT("/Engine/Private/ClearReplacementShaders.usf"),
        TEXT("/Engine/Private/NullPixelShader.usf"),
        TEXT("/Engine/Private/OneColorShader.usf"),
        TEXT("/Engine/Private/ScreenPass.usf"),
        TEXT("/Engine/Private/RenderGraphUtilities.usf"),
        TEXT("/Engine/Private/ResolvePixelShader.usf"),
    };
    if (Filename.StartsWith(TEXT("/Plugin/Rive/"))) return true;
    for (const TCHAR* Utility : UtilityFiles)
    {
        if (Filename == Utility) return true;
    }
    return false;
}

// Same referenced-UB discovery contract as ShaderCore's global initialization,
// restricted to files the standalone renderer actually uses.
void InitializeReferencedUniformBuffers(const TArray<FGlobalShaderType*>& Types)
{
    TSet<FString> SourceFiles;
    for (const FGlobalShaderType* Type : Types)
    {
        TArray<FString> Includes;
        GetShaderIncludes(Type->GetShaderFilename(), Type->GetShaderFilename(), Includes, CompilePlatform);
        SourceFiles.Add(Type->GetShaderFilename());
        for (FString& Include : Includes) SourceFiles.Add(MoveTemp(Include));
    }
    TMap<FString, TArray<const TCHAR*>> References;
    for (const FString& Filename : SourceFiles)
    {
        FString Contents;
        LoadShaderSourceFileChecked(*Filename, CompilePlatform, Contents);
        Contents.ToUpperInline();
        TArray<const TCHAR*>& Names = References.FindOrAdd(Filename);
        for (TLinkedList<FShaderParametersMetadata*>::TIterator It(FShaderParametersMetadata::GetStructList()); It; It.Next())
        {
            const TCHAR* Name = It->GetShaderVariableName();
            const FString Upper = FString(Name).ToUpper();
            if (Contents.Contains(Upper + TEXT("."), ESearchCase::CaseSensitive) ||
                Contents.Contains(Upper + TEXT(" ."), ESearchCase::CaseSensitive))
            {
                Names.Add(Name);
            }
        }
    }
    for (FGlobalShaderType* Type : Types) Type->UpdateReferencedUniformBufferNames(References);
}

void SetupInput(const FGlobalShaderType& Type, int32 PermutationId, FShaderCompilerInput& Input,
    const IShaderFormat& Format, const FString& StereoSource)
{
    Input.Target = FShaderTarget(Type.GetFrequency(), CompilePlatform);
    Input.ShaderPlatformName = FDataDrivenShaderPlatformInfo::GetName(CompilePlatform);
    Input.ShaderFormat = LegacyShaderPlatformToShaderFormat(CompilePlatform);
    Input.PreferredShaderCodeFormat = FDataDrivenShaderPlatformInfo::GetPreferredShaderCodeFormat(CompilePlatform);
    Input.CompressionFormat = NAME_None;
    Input.OodleCompressor = FOodleDataCompression::ECompressor::NotSet;
    Input.OodleLevel = FOodleDataCompression::ECompressionLevel::None;
    Input.VirtualSourceFilePath = Type.GetShaderFilename();
    Input.EntryPointName = Type.GetFunctionName();
    Input.ShaderName = Type.GetName();
    Input.DebugGroupName = TEXT("Global");
    Input.RootParametersStructure = Type.GetRootParametersMetadata();
    Input.bBindlessEnabled = false;

    Type.SetupCompileEnvironment(CompilePlatform, PermutationId, EShaderPermutationFlags::None, Input.Environment);
    auto& Env = Input.Environment;
    Env.SetDefine(TEXT("PIXELSHADER"), Type.GetFrequency() == SF_Pixel);
    Env.SetDefine(TEXT("VERTEXSHADER"), Type.GetFrequency() == SF_Vertex);
    Env.SetDefine(TEXT("GEOMETRYSHADER"), Type.GetFrequency() == SF_Geometry);
    Env.SetDefine(TEXT("COMPUTESHADER"), Type.GetFrequency() == SF_Compute);
    Env.SetDefine(TEXT("MESHSHADER"), 0);
    Env.SetDefine(TEXT("AMPLIFICATIONSHADER"), 0);
    Env.SetDefine(TEXT("FEATURE_LEVEL"), 5);
    Env.SetDefine(TEXT("SHADING_PATH_DEFERRED"), 1);
    Env.SetDefine(TEXT("COMPILER_DEFINE"), TEXT("#define"));
    // The Vulkan backend compiles with DXC; Rive uses this identity for front-face orientation.
    Env.SetDefine(TEXT("COMPILER_DXC"), 1);
    Env.SetDefineAndCompileArgument(TEXT("INSTANCED_STEREO"), false);
    Env.SetDefineAndCompileArgument(TEXT("MOBILE_MULTI_VIEW"), false);
    Env.SetDefineAndCompileArgument(TEXT("VIEW_HAS_TILEOFFSET_DATA"), false);
    Env.SetDefineAndCompileArgument(TEXT("PRIMITIVE_HAS_TILEOFFSET_DATA"), false);
    Env.SetDefineAndCompileArgument(TEXT("PLATFORM_SUPPORTS_UNIFORM_BUFFER_OBJECTS"),
        FDataDrivenShaderPlatformInfo::GetSupportsUniformBufferObjects(CompilePlatform));
    Env.SetDefine(TEXT("PLATFORM_SUPPORTS_BINDLESS"), FDataDrivenShaderPlatformInfo::GetSupportsBindless(CompilePlatform));
    Env.SetDefine(TEXT("UE_BINDLESS_ENABLED"), 0);
    Env.SetDefine(TEXT("PLATFORM_SUPPORTS_SPECIALIZATION_CONSTANTS"), FDataDrivenShaderPlatformInfo::GetSupportsSpecializationConstants(CompilePlatform));
    Env.SetDefine(TEXT("ENABLE_SPECIALIZATION_CONSTANTS"), Env.SpecializationConstantValues.Num() > 0);
    Env.SetDefine(TEXT("WORKING_COLOR_SPACE_IS_SRGB"), 1);
    Env.SetDefine(TEXT("UE_LEGACY_LUMINANCE_FACTORS"), 0);
    Env.SetDefine(TEXT("FORCE_MATERIAL_FLOAT_FULL_PRECISION"), 0);
    Env.SetDefine(TEXT("DO_CHECK"), 0);
    Env.SetDefine(TEXT("DO_GUARD_SLOW"), 0);
    Env.CompilerFlags.Add(CFLAG_RemoveDeadCode);
    const double TileSize = FLargeWorldRenderScalar::GetTileSize();
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE"), float(TileSize));
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE_SQRT"), float(FMath::Sqrt(TileSize)));
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE_RSQRT"), float(FMath::InvSqrt(TileSize)));
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE_RCP"), float(1.0 / TileSize));
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE_FMOD_PI"), float(FMath::Fmod(TileSize, UE_DOUBLE_PI)));
    Env.SetDefine(TEXT("UE_LWC_RENDER_TILE_SIZE_FMOD_2PI"), float(FMath::Fmod(TileSize, 2.0 * UE_DOUBLE_PI)));

    if (FDataDrivenShaderPlatformInfo::GetEnablesHLSL2021ByDefault(CompilePlatform) > 0)
        Env.CompilerFlags.Add(CFLAG_HLSL2021);

    Type.AddUniformBufferIncludesToEnvironment(Env, CompilePlatform);
    Env.IncludeVirtualPathToContentsMap.Add(TEXT("/Engine/Generated/GeneratedInstancedStereo.ush"), StereoSource);
    // Common.ush explicitly includes these even when references were stripped from the entrypoint.
    const FShaderParametersMetadata* View = FindUniformBufferStructByName(TEXT("View"));
    const FShaderParametersMetadata* Instanced = FindUniformBufferStructByName(TEXT("InstancedView"));
    check(View && Instanced);
    TSet<const FShaderParametersMetadata*> ViewStructs;
    ViewStructs.Add(View);
    ViewStructs.Add(Instanced);
    if (FStringView(Type.GetShaderFilename()).StartsWith(TEXT("/Plugin/Rive/")))
    {
        const FShaderParametersMetadata* Flush = FindUniformBufferStructByName(TEXT("uniforms"));
        check(Flush);
        ViewStructs.Add(Flush);
    }
    UE::ShaderParameters::AddUniformBufferIncludesToEnvironment(Env, ViewStructs);
    Format.ModifyShaderCompilerInput(Input);
}

bool WriteManifest(const FString& Path, const TSharedRef<FJsonObject>& Manifest)
{
    FString Text;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    FJsonSerializer::Serialize(Manifest, Writer);
    return FFileHelper::SaveStringToFile(Text, *Path);
}

bool LoadCompileOutput(const FString& Path, FShaderCompilerInputHash InputHash, FShaderCompileJob& Job)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Path, FILEREAD_Silent) || Bytes.Num() < 68) return false;
    FMemoryReader Reader(Bytes, true);
    // Validate the whole record before deserializing any variable-length containers.
    FBlake3Hash StoredDigest;
    const int64 PayloadSize = Bytes.Num() - sizeof(FBlake3Hash);
    Reader.Seek(PayloadSize);
    Reader << StoredDigest;
    if (StoredDigest != FBlake3::HashBuffer(Bytes.GetData(), PayloadSize)) return false;
    Reader.Seek(0);
    uint32 Magic = 0;
    FShaderCompilerInputHash StoredHash;
    Reader << Magic << StoredHash;
    if (Magic != 0x524c4332 || StoredHash != InputHash || Reader.IsError()) return false;
    FShaderCompilerOutput Output;
    Reader << Output;
    if (Reader.IsError() || !Output.bSucceeded || Output.bSerializingForCache ||
        Output.Target != Job.Input.Target || Output.ShaderCode.GetShaderCodeSize() == 0) return false;
    Job.Output = MoveTemp(Output);
    Job.bSucceeded = true;
    return true;
}

bool SaveCompileOutput(const FString& Path, FShaderCompilerInputHash InputHash, FShaderCompileJob& Job)
{
    TArray<uint8> Bytes;
    FMemoryWriter Writer(Bytes, true);
    uint32 Magic = 0x524c4332; // RLC2: full worker output plus record checksum.
    Writer << Magic << InputHash;
    Job.Output.bSerializingForCache = false;
    Writer << Job.Output;
    FBlake3Hash Digest = FBlake3::HashBuffer(Bytes.GetData(), Bytes.Num());
    Writer << Digest;
    const FString Temp = Path + TEXT(".tmp");
    if (Writer.IsError() || !FFileHelper::SaveArrayToFile(Bytes, *Temp)) return false;
    return IFileManager::Get().Move(*Path, *Temp, true, true, false, true);
}

int32 RunMacroRegression(const IShaderFormat& Format, const FString& OutputPath)
{
    // Matches the Rive attribute macro, including newlines around both pasted operands.
    const TCHAR* Source = TEXT(
        "#include \"/Engine/Public/Platform.ush\"\n"
        "#define CONCAT(A, B) A##B\n"
        "#define ATTR(IDX, TYPE, NAME) TYPE NAME : CONCAT(ATTRIBUTE, IDX)\n"
        "#define MATRIX_IDX 3\n"
        "#define EXPAND_PASTE(A, B) CONCAT(A, B)\n"
        "struct Attributes {\n"
        "ATTR(2, float4, singleLine);\n"
        "ATTR(\n MATRIX_IDX,\n float4,\n multiLine);\n"
        "};\n"
        "int EXPAND_PASTE(\n joinedLeft,\n Right\n );\n");
    FShaderCompilerInput Input;
    Input.Target = FShaderTarget(SF_Vertex, CompilePlatform);
    Input.ShaderFormat = LegacyShaderPlatformToShaderFormat(CompilePlatform);
    Input.ShaderPlatformName = FDataDrivenShaderPlatformInfo::GetName(CompilePlatform);
    Input.VirtualSourceFilePath = TEXT("/Engine/Private/RiveLiteMacroRegression.usf");
    Input.EntryPointName = TEXT("Main");
    Input.Environment.SetDefine(TEXT("VERTEXSHADER"), 1);
    Input.Environment.SetDefine(TEXT("PIXELSHADER"), 0);
    Input.Environment.IncludeVirtualPathToContentsMap.Add(Input.VirtualSourceFilePath, Source);
    Format.ModifyShaderCompilerInput(Input);
    FShaderPreprocessOutput Output;
    const bool bPreprocessed = Format.PreprocessShader(Input, Input.Environment, Output);
    const FString Result(Output.GetUnstrippedSourceView());
    FFileHelper::SaveStringToFile(Source, *(OutputPath + TEXT(".macro.source.usf")));
    FFileHelper::SaveStringToFile(Result, *(OutputPath + TEXT(".macro.preprocessed.usf")));
    const bool bPassed = bPreprocessed && Result.Contains(TEXT("ATTRIBUTE2")) &&
        Result.Contains(TEXT("ATTRIBUTE3")) && Result.Contains(TEXT("joinedLeftRight"));
    auto Manifest = MakeShared<FJsonObject>();
    Manifest->SetBoolField(TEXT("preprocessed"), bPreprocessed);
    Manifest->SetBoolField(TEXT("multiline_token_paste_passed"), bPassed);
    Manifest->SetStringField(TEXT("scope"), TEXT("UE IShaderFormat/stb preprocess: unchanged Rive ATTR pattern and newline on both ## operands"));
    WriteManifest(OutputPath + TEXT(".macro.json"), Manifest);
    UE_LOGF(LogRiveLiteShaderCompiler, Display, "Multiline token-paste regression passed=%d", bPassed);
    return bPassed ? 0 : 6;
}

int32 CompileSelectedShaders()
{
    FString ShaderDir;
    FString OutputPath;
    if (!FParse::Value(FCommandLine::Get(), TEXT("RiveShaderDir="), ShaderDir) ||
        !FParse::Value(FCommandLine::Get(), TEXT("Output="), OutputPath))
    {
        UE_LOGF(LogRiveLiteShaderCompiler, Error, "Required: -RiveShaderDir=<Shaders> -Output=<archive.bin> -nullrhi");
        return 2;
    }
    ShaderDir = FPaths::ConvertRelativePathToFull(ShaderDir);
    OutputPath = FPaths::ConvertRelativePathToFull(OutputPath);
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath), true);
    if (!AllShaderSourceDirectoryMappings().Contains(TEXT("/Engine")))
        AddShaderSourceDirectoryMapping(TEXT("/Engine"), FPlatformProcess::ShaderDir());
    const FString AutogenDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectIntermediateDir() / TEXT("ShaderAutogen"));
    IFileManager::Get().MakeDirectory(*AutogenDir, true);
    if (!AllShaderSourceDirectoryMappings().Contains(TEXT("/ShaderAutogen")))
        AddShaderSourceDirectoryMapping(TEXT("/ShaderAutogen"), AutogenDir);
    RegisterRiveLiteShaderDirectory(ShaderDir);
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RenderCore"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RiveLiteRenderer"));
    // ShaderCompileWorker explicitly loads this module before invoking pp_define.
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("ShaderPreprocessor"));
    IShaderFormatModule& FormatModule = FModuleManager::LoadModuleChecked<IShaderFormatModule>(TEXT("VulkanShaderFormat"));
    IShaderFormat* Format = FormatModule.GetShaderFormat();
    if (!Format) return 3;

    EnsureIntCVar(TEXT("vr.InstancedStereo"), 0);
    EnsureIntCVar(TEXT("vr.MobileMultiView"), 0);
    EnsureIntCVar(TEXT("r.MobileHDR"), 1);
    EnsureIntCVar(TEXT("r.ViewHasTileOffsetData"), 0);
    RegisterOfflineCompilerCVars();
    FGenericDataDrivenShaderPlatformInfo::Initialize();
    GMaxRHIShaderPlatform = CompilePlatform;
    GMaxRHIFeatureLevel = ERHIFeatureLevel::SM5;
    GShaderPlatformForFeatureLevel[ERHIFeatureLevel::SM5] = CompilePlatform;
    FShaderPlatformConfig::Initialize();
    FShaderParametersMetadataRegistration::CommitAll();
    FShaderTypeRegistration::CommitAll();
    FShaderParametersMetadata::InitializeAllUniformBufferStructs();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ShaderTypesReady);
    InitializeShaderHashCache();
    if (FParse::Param(FCommandLine::Get(), TEXT("MacroRegression")))
        return RunMacroRegression(*Format, OutputPath);

    const bool bAllRegistered = FParse::Param(FCommandLine::Get(), TEXT("AllRegistered"));
    FString TypeFilter;
    FParse::Value(FCommandLine::Get(), TEXT("Type="), TypeFilter);
    TArray<FGlobalShaderType*> Types;
    for (FShaderType* Type : FShaderType::GetSortedTypes(FShaderType::EShaderTypeForDynamicCast::Global))
        if (IsSelectedType(*Type, bAllRegistered) && (TypeFilter.IsEmpty() || TypeFilter == Type->GetName()))
            Types.Add(static_cast<FGlobalShaderType*>(Type));
    if (Types.IsEmpty())
    {
        UE_LOGF(LogRiveLiteShaderCompiler, Error, "No matching shader types: %ls", *TypeFilter);
        return 4;
    }
    InitializeReferencedUniformBuffers(Types);
    FString StereoSource;
    GenerateInstancedStereoCode(StereoSource, CompilePlatform);

    ITargetPlatform* TargetPlatform = GetTargetPlatformManagerRef().FindTargetPlatform(TEXT("Linux"));
    if (!TargetPlatform || TargetPlatform->HasEditorOnlyData())
    {
        UE_LOGF(LogRiveLiteShaderCompiler, Error, "Linux cooked target platform unavailable; refusing an editor-layout archive.");
        return 4;
    }

    FGlobalShaderMap ShaderMap(CompilePlatform);
    TArray<TSharedPtr<FJsonValue>> Jobs;
    TSet<FGlobalShaderMapSection*> Sections;
    int32 CompiledCount = 0;
    int32 Limit = MAX_int32;
    FParse::Value(FCommandLine::Get(), TEXT("Limit="), Limit);
    const bool bListOnly = FParse::Param(FCommandLine::Get(), TEXT("ListOnly"));
    FString CacheDir = FPaths::GetPath(OutputPath) / TEXT("shader-jobs");
    FParse::Value(FCommandLine::Get(), TEXT("CacheDir="), CacheDir);
    IFileManager::Get().MakeDirectory(*CacheDir, true);
    int32 CacheHits = 0;
    bool bSucceeded = true;
    const double StartTime = FPlatformTime::Seconds();
    const TArray<const IShaderFormat*> Formats{Format};
    for (FGlobalShaderType* Type : Types)
    {
        bSucceeded = Type->ForEachCompiledPermutation(CompilePlatform, EShaderPermutationFlags::None,
            [&](int32 PermutationId)
            {
                if (CompiledCount >= Limit) return false;
                auto Entry = MakeShared<FJsonObject>();
                Entry->SetStringField(TEXT("type"), Type->GetName());
                Entry->SetStringField(TEXT("source"), Type->GetShaderFilename());
                Entry->SetNumberField(TEXT("permutation"), PermutationId);
                Jobs.Add(MakeShared<FJsonValueObject>(Entry));
                if (bListOnly) { ++CompiledCount; return true; }
                FShaderCompileJob Job;
                Job.bIsGlobalShader = true;
                Job.bErrorsAreLikelyToBeCode = true;
                Job.Key = FShaderCompileJobKey(Type, CompilePlatform, nullptr, PermutationId);
                SetupInput(*Type, PermutationId, Job.Input, *Format, StereoSource);
                UE_LOGF(LogRiveLiteShaderCompiler, Display, "Compiling %ls permutation %d", Type->GetName(), PermutationId);
                const double JobStart = FPlatformTime::Seconds();
                if (!PreprocessShader(&Job))
                {
                    for (const FShaderCompilerError& Error : Job.Output.Errors)
                        UE_LOGF(LogRiveLiteShaderCompiler, Error, "%ls", *Error.GetErrorString());
                    Entry->SetBoolField(TEXT("preprocess_passed"), false);
                    return false;
                }
                const FShaderCompilerInputHash InputHash = Job.GetInputHash();
                const FString CachePath = CacheDir / (LexToString(InputHash) + TEXT(".bin"));
                const bool bCacheHit = LoadCompileOutput(CachePath, InputHash, Job);
                if (bCacheHit) ++CacheHits;
                else CompileShader(Formats, Job);
                Entry->SetNumberField(TEXT("seconds"), FPlatformTime::Seconds() - JobStart);
                Entry->SetBoolField(TEXT("compiled"), Job.Output.bSucceeded);
                Entry->SetBoolField(TEXT("cache_hit"), bCacheHit);
                if (!Job.Output.bSucceeded)
                {
                    FFileHelper::SaveStringToFile(FString(Job.PreprocessOutput.GetUnstrippedSourceView()),
                        *(OutputPath + TEXT(".failed.preprocessed.usf")));
                    for (const FShaderCompilerError& Error : Job.Output.Errors)
                        UE_LOGF(LogRiveLiteShaderCompiler, Error, "%ls", *Error.GetErrorString());
                    return false;
                }
                if (!bCacheHit && !SaveCompileOutput(CachePath, InputHash, Job))
                    UE_LOGF(LogRiveLiteShaderCompiler, Warning, "Could not persist compile output: %ls", *CachePath);
                FGlobalShaderMapSection* Section = ShaderMap.FindOrAddSection(Type);
                Section->GetResourceCode()->AddShaderCompilerOutput(Job.Output, Job.Key);
                const FStringView GlobalName = TEXTVIEW("GlobalShaderMap");
                const uint64 Hash = FXxHash64::HashBuffer(GlobalName.GetData(), GlobalName.NumBytes()).Hash;
                FShader* Shader = Type->ConstructCompiled(FGlobalShaderType::CompiledShaderInitializerType(
                    Type, nullptr, PermutationId, Job.Output, Hash, nullptr, nullptr));
                ShaderMap.FindOrAddShader(Type, PermutationId, Shader);
                Job.Output.ParameterMap.VerifyBindingsAreComplete(Type->GetName(), Job.Output.Target, nullptr);
                Sections.Add(Section);
                ++CompiledCount;
                return true;
            });
        if (!bSucceeded) break;
    }
    auto Manifest = MakeShared<FJsonObject>();
    Manifest->SetStringField(TEXT("shader_platform"), FDataDrivenShaderPlatformInfo::GetName(CompilePlatform).ToString());
    Manifest->SetStringField(TEXT("scope"), TEXT("Rive plus selected unchanged RenderCore utility shaders; headless offline compiler"));
    Manifest->SetStringField(TEXT("environment_status"), TEXT("Prototype SM5 environment; UE screenshot comparison remains required before parity acceptance"));
    Manifest->SetBoolField(TEXT("with_engine"), WITH_ENGINE != 0);
    Manifest->SetBoolField(TEXT("with_editor"), WITH_EDITOR != 0);
    Manifest->SetBoolField(TEXT("list_only"), bListOnly);
    Manifest->SetStringField(TEXT("type_filter"), TypeFilter);
    Manifest->SetBoolField(TEXT("complete"), bSucceeded);
    Manifest->SetNumberField(TEXT("compiled_permutations"), CompiledCount);
    Manifest->SetNumberField(TEXT("cache_hits"), CacheHits);
    Manifest->SetStringField(TEXT("cache_dir"), CacheDir);
    Manifest->SetNumberField(TEXT("elapsed_seconds"), FPlatformTime::Seconds() - StartTime);
    Manifest->SetArrayField(TEXT("jobs"), Jobs);
    // Publish diagnostics before freezing so a layout failure does not discard compile evidence.
    WriteManifest(OutputPath + TEXT(".manifest.json"), Manifest);
    if (bSucceeded && !bListOnly)
    {
        for (FGlobalShaderMapSection* Section : Sections) Section->FinalizeContent();
        TArray64<uint8> Bytes;
        FMemoryWriter64 Archive(Bytes, true);
        FArchiveSavePackageDataBuffer CookData(TargetPlatform);
        Archive.SetSavePackageData(&CookData);
        ShaderMap.SaveToGlobalArchive(Archive);
        bSucceeded = FFileHelper::SaveArrayToFile(Bytes, *OutputPath);
        Manifest->SetBoolField(TEXT("complete"), bSucceeded);
        Manifest->SetNumberField(TEXT("archive_bytes"), Bytes.Num());
    }
    WriteManifest(OutputPath + TEXT(".manifest.json"), Manifest);
    return bSucceeded ? 0 : 5;
}
}

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    FTaskTagScope Scope(ETaskTag::EGameThread);
    ON_SCOPE_EXIT
    {
        RequestEngineExit(TEXT("RiveLite shader compilation completed"));
        // SaveToGlobalArchive creates the exporter even with symbols disabled.
        // Its event must return to the pool before AppExit tears that pool down.
        FShaderSymbolExport::Shutdown(LegacyShaderPlatformToShaderFormat(CompilePlatform));
        UE_LOGF(LogRiveLiteShaderCompiler, Display, "Shutdown: AppPreExit");
        FEngineLoop::AppPreExit();
        // EngineLoop::Exit normally tears this down before thread/event pools.
        // This Program deliberately uses only the no-Engine AppPreExit/AppExit path.
        FIoDispatcher::Shutdown();
        UE_LOGF(LogRiveLiteShaderCompiler, Display, "Shutdown: UnloadModules");
        FModuleManager::Get().UnloadModulesAtShutdown();
        UE_LOGF(LogRiveLiteShaderCompiler, Display, "Shutdown: AppExit");
        FEngineLoop::AppExit();
    };
    if (int32 Result = GEngineLoop.PreInit(ArgC, ArgV)) return Result;
#if PLATFORM_LINUX
    if (FParse::Param(FCommandLine::Get(), TEXT("CrashTrace")))
    {
        signal(SIGSEGV, &DumpFatalSignal);
        signal(SIGABRT, &DumpFatalSignal);
    }
#endif
    ProcessNewlyLoadedUObjects();
    FModuleManager::Get().StartProcessingNewlyLoadedObjects();
    return CompileSelectedShaders();
}
