#include "RequiredProgramMainCPPInclude.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#if VERSE_COST_FRONTEND
#include "uLang/HostServices/CoreHelpers.h"
#include "uLang/Parser/ParserPass.h"
#include "uLang/SemanticAnalyzer/SemanticAnalyzerPass.h"
#include "uLang/SourceProject/SourceDataProject.h"
#include "uLang/Toolchain/ProgramBuildManager.h"
#endif

IMPLEMENT_APPLICATION(VerseCostProbe, "VerseCostProbe");

INT32_MAIN_INT32_ARGC_TCHAR_ARGV()
{
    const double Started = FPlatformTime::Seconds();
    FTaskTagScope Scope(ETaskTag::EGameThread);
    if (int32 Error = GEngineLoop.PreInit(ArgC, ArgV)) return Error;
    ON_SCOPE_EXIT
    {
        RequestEngineExit(TEXT("Verse frontend cost assessment complete"));
        FEngineLoop::AppPreExit();
        FModuleManager::Get().UnloadModulesAtShutdown();
        FEngineLoop::AppExit();
    };
    FString Output;
    FParse::Value(FCommandLine::Get(), TEXT("Report="), Output);
    int32 Iterations = 5, Functions = 1;
    FParse::Value(FCommandLine::Get(), TEXT("Iterations="), Iterations);
    FParse::Value(FCommandLine::Get(), TEXT("Functions="), Functions);
    if (Output.IsEmpty() || Iterations < 1 || Iterations > 1000 || Functions < 1 || Functions > 10000) return 2;
    const double CoreReady = FPlatformTime::Seconds();
    FString Timings;
    bool Valid = true;
    double FrontendReady = CoreReady;
#if VERSE_COST_FRONTEND
    uLang::SSystemParams Params = {ULANG_API_VERSION, &malloc, &realloc, &free,
        &uLang::DefaultAssertHandler, &uLang::DefaultLogMessage};
    if (uLang::Initialize(Params) != uLang::EResult::OK) return 3;
    {
        uLang::SBuildManagerParams ManagerParams = {
            ._ToolchainOverrides{
                .Parser = uLang::TSPtr<uLang::IParserPass>(uLang::TSPtr<uLang::CParserPass>::New()),
                .SemanticAnalyzer = uLang::TSPtr<uLang::ISemanticAnalyzerPass>(uLang::TSPtr<uLang::CSemanticAnalyzerPass>::New())
            }
        };
        auto Manager = uLang::TSPtr<uLang::CProgramBuildManager>::New(ManagerParams);
        FrontendReady = FPlatformTime::Seconds();
        for (int32 Pass = 0; Pass < Iterations; ++Pass)
        {
            FString Source;
            for (int32 Index = 0; Index < Functions; ++Index)
                Source += FString::Printf(TEXT("value_%d(X:int):int = X + %d\n"), Index, Index + Pass);
            const double CompileStarted = FPlatformTime::Seconds();
            Manager->ReleaseCompilationArtifacts();
            auto Project = uLang::TSRef<uLang::CSourceProject>::New("CostProbe");
            Manager->SetSourceProject(Project);
            const auto& Package = Manager->FindOrAddSourcePackage("CostProbe", "/CostProbe/Test");
            Package._Package->SetVerseScope(uLang::EVerseScope::InternalUser);
            Package._Package->SetRole(uLang::EPackageRole::Source);
            uLang::TSRef<uLang::ISourceSnippet> Snippet = uLang::TSRef<uLang::CSourceDataSnippet>::New(
                uLang::CUTF8String("cost.verse"), uLang::CUTF8String(TCHAR_TO_UTF8(*Source)));
            Manager->GetSourceProject()->AddSnippet(Snippet, "CostProbe", "/CostProbe/Test");
            auto Diagnostics = uLang::TSRef<uLang::CDiagnostics>::New();
            uLang::SBuildParams Build;
            Build._bSemanticAnalysisOnly = true;
            const auto Result = Manager->Build(Build, Diagnostics);
            const bool Passed = !Result.HasFailure() &&
                uLang::Enum_HasAnyFlags(Result._CompilerResult, uLang::ECompilerResult::Compile_RanSemanticPass);
            Valid &= Passed;
            Timings += FString::Printf(TEXT("%s%.6f"), Pass ? TEXT(",") : TEXT(""),
                (FPlatformTime::Seconds() - CompileStarted) * 1000.0);
            if (!Passed)
                for (auto Error : Diagnostics->GetGlitches())
                    fprintf(stderr, "%s\n", Error->AsFormattedString().AsCString());
        }
    }
    uLang::DeInitialize();
#endif
    const FString Json = FString::Printf(
        TEXT("{\"frontend\":%s,\"valid\":%s,\"core_ready_ms\":%.6f,\"frontend_ready_ms\":%.6f,\"function_count\":%d,\"semantic_ms\":[%s],\"bytecode_generated\":false,\"vm_executed\":false}\n"),
        VERSE_COST_FRONTEND ? TEXT("true") : TEXT("false"), Valid ? TEXT("true") : TEXT("false"),
        (CoreReady - Started) * 1000.0, (FrontendReady - Started) * 1000.0, Functions, *Timings);
    if (!FFileHelper::SaveStringToFile(Json, *Output, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)) return 4;
    return Valid ? 0 : 5;
}
