// Independent native Engine compiler; no lite shader environment or archive input.
#include "CoreMinimal.h"
#include "Async/TaskGraphInterfaces.h"
#include "AssetCompilingManager.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "DerivedDataCache.h"
#include "DeviceProfiles/DeviceProfileManager.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "GlobalShader.h"
#include "Hash/Blake3.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformOutputDevices.h"
#include "HAL/PlatformTLS.h"
#include "Internationalization/EnginePackageLocalizationCache.h"
#include "Internationalization/PackageLocalizationManager.h"
#include "Interfaces/ITargetPlatform.h"
#include "Interfaces/ITargetPlatformManagerModule.h"
#include "IO/IoDispatcher.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/ConfigUtilities.h"
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
#include "RenderResource.h"
#include "RenderUtils.h"
#include "RHICommandList.h"
#include "RiveUeReferenceRenderer.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryWriter.h"
#include "Scalability.h"
#include "ShaderCodeLibrary.h"
#include "ShaderCompiler.h"
#include "ShaderParameterMetadata.h"
#include "ShaderSymbolExport.h"
#include "Stats/Stats.h"
#include "UObject/PackageResourceManager.h"
#include "UObject/UObjectBase.h"

#if !WITH_ENGINE || !WITH_EDITOR || !IS_PROGRAM || !IS_MONOLITHIC
#error The native cooker requires a monolithic Engine Program with editor compiler code.
#endif
TCHAR GInternalProjectName[64] = TEXT("RiveUeShaderCooker");
IMPLEMENT_FOREIGN_ENGINE_DIR()
IMPLEMENT_SIGNING_KEY_REGISTRATION()
IMPLEMENT_ENCRYPTION_KEY_REGISTRATION()
IMPLEMENT_GAME_MODULE(FDefaultGameModuleImpl, RiveUeShaderCooker)
PER_MODULE_BOILERPLATE
DEFINE_LOG_CATEGORY_STATIC(LogRiveUeShaderCooker, Log, All);
#if UE_ALLOW_ENGINE_STDIO_OUTPUT
static TUniquePtr<FOutputDeviceStdOutput> GCookerStdOut;
#endif
// Pinned monolithic Engine state declared in ShaderCompilerPrivate.h.
extern const ITargetPlatform* GGlobalShaderTargetPlatform[SP_NumPlatforms];
extern ENGINE_API void InitializeRenderingCVarsCaching();
#include "CanonicalBootstrap.inl"

namespace
{
#if PLATFORM_MAC
constexpr EShaderPlatform CookPlatform = SP_METAL_SM5;
constexpr const TCHAR* CookTarget = TEXT("Mac");
constexpr const TCHAR* CookEditorTarget = TEXT("MacEditor");
#elif PLATFORM_WINDOWS
constexpr EShaderPlatform CookPlatform = SP_VULKAN_SM5;
constexpr const TCHAR* CookTarget = TEXT("Windows");
constexpr const TCHAR* CookEditorTarget = TEXT("WindowsEditor");
#else
constexpr EShaderPlatform CookPlatform = SP_VULKAN_SM5_LINUX;
constexpr const TCHAR* CookTarget = TEXT("Linux");
constexpr const TCHAR* CookEditorTarget = TEXT("LinuxEditor");
#endif

bool IsSelectedType(const FShaderType& Type)
{
    const FString Filename(Type.GetShaderFilename());
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
    // Source-Blueprint worker has no Rive shader types linked. Cook a separate
    // native Slate/utility archive instead of loading unrelated Rive sections.
    if (Filename.StartsWith(TEXT("/Plugin/Rive/")))
        return !FParse::Param(FCommandLine::Get(), TEXT("SlateOnly"));
    if (FParse::Param(FCommandLine::Get(), TEXT("IncludeSlate")) && Filename.StartsWith(TEXT("/Engine/Private/Slate"))) return true;
    for (const TCHAR* Utility : UtilityFiles) if (Filename == Utility) return true;
    return false;
}

void WriteManifest(const FString& Path, const TSharedRef<FJsonObject>& Manifest)
{
    FString Text;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    FJsonSerializer::Serialize(Manifest, Writer);
    verify(FFileHelper::SaveStringToFile(Text, *Path));
}

int32 Cook(const FString& Output, const FString& ShaderDirectory)
{
    const double Started = FPlatformTime::Seconds();
    // The ordinary Launch bootstrap installs these mappings before shader setup.
    AddShaderSourceDirectoryMapping(TEXT("/Engine"), FPlatformProcess::ShaderDir());
    const FString AutogenDirectory = FPaths::ConvertRelativePathToFull(FPaths::ProjectIntermediateDir() / TEXT("ShaderAutogen"));
    IFileManager::Get().MakeDirectory(*AutogenDirectory, true);
    AddShaderSourceDirectoryMapping(TEXT("/ShaderAutogen"), AutogenDirectory);
    RegisterRiveUeReferenceShaderDirectory(ShaderDirectory);
    FGenericDataDrivenShaderPlatformInfo::Initialize();
    FShaderParametersMetadataRegistration::CommitAll();
    FShaderTypeRegistration::CommitAll();
    FShaderParametersMetadata::InitializeAllUniformBufferStructs();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreRHIInit);
    RHIInit(false);
    GMaxRHIShaderPlatform = CookPlatform;
    GMaxRHIFeatureLevel = ERHIFeatureLevel::SM5;
    GShaderPlatformForFeatureLevel[ERHIFeatureLevel::SM5] = CookPlatform;
    RenderUtilsInit();
    const bool EditorShaders = FParse::Param(FCommandLine::Get(), TEXT("EditorShaders"));
    ITargetPlatform* TargetPlatform = GetTargetPlatformManagerRef().FindTargetPlatform(EditorShaders ? CookEditorTarget : CookTarget);
    if (!TargetPlatform || TargetPlatform->HasEditorOnlyData() != EditorShaders) return 3;
    FPlatformTypeLayoutParameters TargetLayout;
    TargetLayout.InitializeForPlatform(TargetPlatform);
    const EShaderPermutationFlags PermutationFlags = GetShaderPermutationFlags(TargetLayout);
    UE::DerivedData::GetCache();
    check(!GShaderCompilerStats && !GShaderCompilingManager);
    GShaderCompilerStats = new FShaderCompilerStats();
    GShaderCompilingManager = new FShaderCompilingManager();
    GShaderCompilingManager->SetAllowForIncompleteShaderMaps(true);
    InitializeShaderHashCache();
    FShaderCompileUtilities::GenerateBrdfHeaders(CookPlatform);
    InitializeShaderTypes();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ShaderTypesReady);
    GGlobalShaderTargetPlatform[CookPlatform] = TargetPlatform;
    GGlobalShaderMap[CookPlatform] = new FGlobalShaderMap(CookPlatform);

    FString TypeFilter;
    FParse::Value(FCommandLine::Get(), TEXT("Type="), TypeFilter);
    TArray<FShaderCommonCompileJobPtr> Jobs;
    TSharedPtr<FJsonObject> FirstRiveInput;
    TArray<TPair<FGlobalShaderType*, int32>> Selected;
    TArray<TSharedPtr<FJsonValue>> Types;
    for (TLinkedList<FShaderType*>::TIterator It(FShaderType::GetTypeList()); It; It.Next())
    {
        if ((*It)->GetTypeForDynamicCast() != FShaderType::EShaderTypeForDynamicCast::Global) continue;
        FGlobalShaderType* Type = const_cast<FGlobalShaderType*>((*It)->AsGlobalShaderType());
        if (!Type || !IsSelectedType(*Type) || (!TypeFilter.IsEmpty() && TypeFilter != Type->GetName())) continue;
        int32 Count = 0;
        TArray<TSharedPtr<FJsonValue>> PermutationIds;
        Type->ForEachCompiledPermutation(CookPlatform, PermutationFlags, [&](int32 Permutation)
        {
            // Engine prepares the complete canonical input and compiles via its manager.
            FGlobalShaderTypeCompiler::BeginCompileShader(Type, Permutation, CookPlatform,
                PermutationFlags, Jobs);
            if (!FirstRiveInput && FStringView(Type->GetShaderFilename()).StartsWith(TEXT("/Plugin/Rive/")) && !Jobs.IsEmpty())
            {
                FShaderCompileJob* Job = Jobs.Last()->GetSingleShaderJob();
                FirstRiveInput = MakeShared<FJsonObject>();
                FirstRiveInput->SetStringField(TEXT("type"), Type->GetName());
                FirstRiveInput->SetNumberField(TEXT("permutation"), Permutation);
                FirstRiveInput->SetStringField(TEXT("shader_format"), Job->Input.ShaderFormat.ToString());
                FirstRiveInput->SetStringField(TEXT("compression_format"), Job->Input.CompressionFormat.ToString());
                FirstRiveInput->SetStringField(TEXT("compiler_flags_hex"), FString::Printf(TEXT("%016llx"), static_cast<unsigned long long>(Job->Input.Environment.CompilerFlags.GetData())));
                TArray<uint8> EnvironmentBytes;
                FMemoryWriter Writer(EnvironmentBytes);
                Job->Input.Environment.SerializeEverythingButFiles(Writer);
                FirstRiveInput->SetStringField(TEXT("environment_without_files_blake3"), LexToString(FBlake3::HashBuffer(EnvironmentBytes.GetData(), EnvironmentBytes.Num())));
                Job->Input.Environment.DumpDefinitionsAsCsv(Output + TEXT(".first-rive-defines.csv"));
            }
            Selected.Emplace(Type, Permutation);
            PermutationIds.Add(MakeShared<FJsonValueNumber>(Permutation));
            ++Count;
            return true;
        });
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("type"), Type->GetName());
        Entry->SetStringField(TEXT("source"), Type->GetShaderFilename());
        Entry->SetNumberField(TEXT("permutations"), Count);
        Entry->SetArrayField(TEXT("permutation_ids"), PermutationIds);
        Types.Add(MakeShared<FJsonValueObject>(Entry));
    }
    auto Manifest = MakeShared<FJsonObject>();
    Manifest->SetStringField(TEXT("kind"), TEXT("ue_engine_canonical"));
    Manifest->SetStringField(TEXT("scope"), TEXT("Native Engine environment for Rive and selected RenderCore utilities; not the entire UE global map or Editor viewport"));
    Manifest->SetStringField(TEXT("type_filter"), TypeFilter);
    Manifest->SetStringField(TEXT("target_platform"), TargetPlatform->PlatformName());
    Manifest->SetBoolField(TEXT("target_has_editor_only_data"), TargetPlatform->HasEditorOnlyData());
    Manifest->SetNumberField(TEXT("permutation_flags"), static_cast<uint32>(PermutationFlags));
    Manifest->SetStringField(TEXT("shader_platform"), FDataDrivenShaderPlatformInfo::GetName(CookPlatform).ToString());
    if (FirstRiveInput) Manifest->SetObjectField(TEXT("first_rive_native_input"), FirstRiveInput);
    Manifest->SetStringField(TEXT("entrypoint"), TEXT("FGlobalShaderTypeCompiler::BeginCompileShader -> GlobalBeginCompileShader -> FShaderCompilingManager"));
    Manifest->SetBoolField(TEXT("complete"), false);
    Manifest->SetBoolField(TEXT("with_engine"), true);
    Manifest->SetBoolField(TEXT("with_editor"), true);
    Manifest->SetBoolField(TEXT("allow_other_platform_config"), ALLOW_OTHER_PLATFORM_CONFIG != 0);
    Manifest->SetBoolField(TEXT("loads_lite_archive"), false);
    Manifest->SetNumberField(TEXT("selected_permutations"), Selected.Num());
    Manifest->SetNumberField(TEXT("submitted_jobs"), Jobs.Num());
    Manifest->SetArrayField(TEXT("types"), Types);
    WriteManifest(Output + TEXT(".manifest.json"), Manifest);
    if (Jobs.IsEmpty()) return 4;
    UE_LOGF(LogRiveUeShaderCooker, Display, "Native canonical jobs submitted: %d for %d permutations", Jobs.Num(), Selected.Num());
    GShaderCompilingManager->SubmitJobs(Jobs, TEXT("RiveCanonical"));
    const TArray<int32> ShaderMapIds{GlobalShaderMapId};
    GShaderCompilingManager->FinishCompilation(TEXT("Rive canonical global shaders"), ShaderMapIds);
    int32 SucceededJobs = 0;
    for (const FShaderCommonCompileJobPtr& Job : Jobs)
        if (Job->bSucceeded) ++SucceededJobs;
    Manifest->SetNumberField(TEXT("succeeded_jobs"), SucceededJobs);
    Manifest->SetNumberField(TEXT("failed_jobs"), Jobs.Num() - SucceededJobs);
    if (SucceededJobs != Jobs.Num())
    {
        WriteManifest(Output + TEXT(".manifest.json"), Manifest);
        return 5;
    }
    TSet<FGlobalShaderMapSection*> Sections;
    for (const auto& Selection : Selected)
    {
        if (!GGlobalShaderMap[CookPlatform]->HasShader(Selection.Key, Selection.Value)) return 5;
        Sections.Add(GGlobalShaderMap[CookPlatform]->FindOrAddSection(Selection.Key));
    }
    for (FGlobalShaderMapSection* Section : Sections) Section->FinalizeContent();
    const FString NativeSaveRoot = FPaths::GetPath(Output) / (TEXT("native-save-") + FGuid::NewGuid().ToString(EGuidFormats::Digits));
    IFileManager::Get().MakeDirectory(*(NativeSaveRoot / TEXT("Engine")), true);
    const FString NativeOutput = SaveGlobalShaderFile(CookPlatform, NativeSaveRoot, TargetPlatform);
    if (!IFileManager::Get().Move(*Output, *NativeOutput, false, true, false, true)) return 6;
    Manifest->SetBoolField(TEXT("complete"), true);
    Manifest->SetNumberField(TEXT("archive_bytes"), IFileManager::Get().FileSize(*Output));
    Manifest->SetNumberField(TEXT("elapsed_seconds"), FPlatformTime::Seconds() - Started);
    WriteManifest(Output + TEXT(".manifest.json"), Manifest);
    UE_LOGF(LogRiveUeShaderCooker, Display, "RIVE_UE_CANONICAL_COOK_COMPLETE path=\"%ls\" permutations=%d", *Output, Selected.Num());
    return 0;
}
}

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    FTaskTagScope Scope(ETaskTag::EGameThread);
    FCommandLine::Set(*FCommandLine::BuildFromArgV(nullptr, ArgC, ArgV, nullptr));
    FString Output, ShaderDirectory, ProjectDirectory;
    FParse::Value(FCommandLine::Get(), TEXT("Output="), Output);
    FParse::Value(FCommandLine::Get(), TEXT("RiveShaderDir="), ShaderDirectory);
    FParse::Value(FCommandLine::Get(), TEXT("ProjectDir="), ProjectDirectory);
    if (Output.IsEmpty() || ShaderDirectory.IsEmpty() || IFileManager::Get().FileExists(*Output)) return 2;
    if (!ProjectDirectory.IsEmpty()) FGenericPlatformMisc::SetOverrideProjectDir(ProjectDirectory);
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Output), true);
    BootstrapCore();
    ON_SCOPE_EXIT
    {
        RequestEngineExit(TEXT("Native canonical shader cook completed"));
        FAssetCompilingManager::Get().Shutdown();
        delete GShaderCompilingManager; GShaderCompilingManager = nullptr;
        delete GShaderCompilerStats; GShaderCompilerStats = nullptr;
        FShaderSymbolExport::Shutdown(LegacyShaderPlatformToShaderFormat(CookPlatform));
        delete GGlobalShaderMap[CookPlatform]; GGlobalShaderMap[CookPlatform] = nullptr;
        FShaderCodeLibrary::Shutdown();
        if (GIsRHIInitialized) { FRenderResource::ReleaseRHIForAllResources(); RHIExit(); }
        FCoreDelegates::OnPreExit.Broadcast();
        FCoreDelegates::OnExit.Broadcast();
        IPackageResourceManager::Shutdown();
        FIoDispatcher::Shutdown();
        FModuleManager::Get().UnloadModulesAtShutdown();
        for (FQueuedThreadPool* Pool : {GThreadPool, GLargeThreadPool, GIOThreadPool, GBackgroundPriorityThreadPool}) if (Pool) Pool->Destroy();
#if STATS
        FThreadStats::StopThread();
#endif
        FTaskGraphInterface::Shutdown();
        FPlatformApplicationMisc::TearDown();
        FPlatformMisc::PlatformTearDown();
        if (GConfig) { GConfig->Exit(); delete GConfig; GConfig = nullptr; }
        if (GLog) GLog->TearDown();
    };
    return Cook(Output, FPaths::ConvertRelativePathToFull(ShaderDirectory));
}
