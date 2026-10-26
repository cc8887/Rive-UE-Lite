// Copyright Epic Games, Inc. All Rights Reserved.

#include "Script.h"
#include "AutoRTFM.h"
#include "Containers/UnrealString.h"
#include "EventLoop.h"
#include "ISolarisIde.h"
#include "ISolarisModule.h"
#include "IVerseModule.h"
#include "Misc/FileHelper.h"
#include "SolBuildDiagnostic.h"
#include "TestUtils/PlaceholderObjectForContentScope.h"
#include "ULangUEUtils.h"
#include "VerseComputationLimitControl.h"
#include "VerseContentScope.h"
#include "VerseString.h"
#include "VerseTask.h"
#include "VerseVM/VVMCoroutine.h"
#include "VerseVM/VVMNativeFunction.h"
#include "uLang/SourceProject/VerseVersion.h"
#include "uLang/Toolchain/ProgramBuildManager.h"
#include <stdio.h> // for fprintf

constexpr const char* ScriptPackageName = "SolIdeDataSources";
constexpr const char* ScriptVersePath = "/user@localhost";
constexpr const char* ScriptFunctionName = "Main(:[][]char,:[[]char][]char)";

namespace VerseCmd {
struct FScript
{
    using FMainFunction = TVerseFunction<FVerseResult(
        TVerseCall<void>, const TArray<verse::string>&, const TMap<verse::string, verse::string>&)>;

    FMainFunction MainFunction;
};
}

AUTORTFM_DISABLE static void ReportSolDiagnostic(const FSolDiagnostic& Diagnostic)
{
    // FDiagnosticLocus is 1-based; STextRange is 0-based and SGlitch::FormattedString re-adds +1.
    uLang::STextRange Range(FMath::Max(0, Diagnostic.Location.RowSpan.X - 1),
                            FMath::Max(0, Diagnostic.Location.ColSpan.X - 1),
                            FMath::Max(0, Diagnostic.Location.RowSpan.Y - 1),
                            FMath::Max(0, Diagnostic.Location.ColSpan.Y - 1));

    uLang::EDiagnosticSeverity Severity = uLang::EDiagnosticSeverity::Ok;

    PRAGMA_DISABLE_SWITCH_UNHANDLED_ENUM_CASE_WARNINGS;
    FILE* OutputFile = stdout;
    switch (Diagnostic.Info.Severity)
    {
    case ELogVerbosity::Error:
        OutputFile = stderr;
        Severity = uLang::EDiagnosticSeverity::Error;
        break;
    case ELogVerbosity::Warning:
        OutputFile = stderr;
        Severity = uLang::EDiagnosticSeverity::Warning;
        break;
    case ELogVerbosity::Display:
        Severity = uLang::EDiagnosticSeverity::Info;
        break;
    default:
        ULANG_ERRORF("Encountered an unexpected glitch severity level!");
    };
    PRAGMA_RESTORE_SWITCH_UNHANDLED_ENUM_CASE_WARNINGS;

    uLang::CUTF8String FormattedMsg =
        uLang::SGlitch::FormattedString(TCHAR_TO_UTF8(*Diagnostic.Info.Message),
                                        TCHAR_TO_UTF8(*Diagnostic.Location.FilePath),
                                        Range,
                                        Severity,
                                        uLang::GetDiagnosticFromReferenceCode(Diagnostic.Info.ReferenceCode));

    fprintf(OutputFile, "%s\n", FormattedMsg.AsCString());
}

AUTORTFM_DISABLE TSharedPtr<VerseCmd::FScript> VerseCmd::BuildScript(const FUtf8String& ScriptFilePath,
                                                                     const TArray<FMount>& Mounts)
{
    ISolarisModule& SolarisModule = ISolarisModule::Get();

    // Create the source project
    TOptional<TSharedRef<ISolIdeSourceProject>> MaybeSourceProject = ISolarisModule::Get().CreateProjectSource(
        TEXT("VerseCmd"), ISolarisModule::EBuildMode::Incremental, MakeIdeDiagnostics(ReportSolDiagnostic));
    if (!MaybeSourceProject.IsSet())
    {
        fprintf(stderr, "Error: Failed to compile VerseCmd Verse code.\n");
        return {};
    }
    TSharedRef<ISolIdeSourceProject> SourceProject = *MaybeSourceProject;

    // Create a new SolarisIde from the given source project
    const FSolIdeConfig IdeConfig{.Flags = ESolIdeFlags::WithPackageUsage,
                                  .VersePath = ScriptVersePath,
                                  .VerseScope = uLang::EVerseScope::PublicUser,
                                  .VerseVersion = Verse::Version::LatestUnstable,
                                  .bAllowExperimental = true};
    TSharedRef<ISolarisIde> SolarisIde = SolarisModule.MakeDevEnvironment(IdeConfig);
    SolarisIde->SetSourceProject(SourceProject);

    if (Mounts.Num())
    {
        fprintf(stderr, "Error: Mounts are not yet implemented.\n");
        return {};
    }

    // Load the script file. We don't actually use the loaded string except to produce an error if the file is missing.
    // SolarisIde->AddDataSource below will silently do nothing if there isn't a file with that name.
    FString SourceTextAsFString;
    if (!FFileHelper::LoadFileToString(SourceTextAsFString, *FString(ScriptFilePath)))
    {
        fprintf(stderr, "Error: Failed to open file '%s'\n", *FAnsiString(ScriptFilePath));
        return {};
    }

    // Add the source snippet to the IDE
    TSharedRef<ISolIdeDataSource> Script =
        SolarisIde->AddDataSource(FULangConversionUtils::FUtf8StringToULangStr(ScriptFilePath));

    FSolIdeBuildSettings Settings{.LinkSettings = uLang::SBuildParams::ELinkParam::RequireComplete};
    if (!SolarisIde->BuildAll(Settings, MakeIdeDiagnostics(ReportSolDiagnostic)))
    {
        fprintf(stderr, "Error: Failed to compile script.\n");
        return {};
    }

    IVerseModule::Get(); // To run VerseModule::StartupModule(). TODO: this is hacky.

    // Find the Main function in the script module.
    FScript::FMainFunction MainFunction{FVerseFunction(
        verse::FExecutionContext::GetActiveContext(), ScriptPackageName, ScriptVersePath, ScriptFunctionName)};
    if (!MainFunction.IsValid())
    {
        fprintf(stderr, "Error: Couldn't find %s function in script.\n", ScriptFunctionName);
        return {};
    }

    return MakeShared<FScript>(FScript{.MainFunction = MoveTemp(MainFunction)});
}

static void OnScriptTaskFinished(FVerseTask Task)
{
    // Only exit the event loop when the script task completes normally.
    // Await callbacks also fire on termination (e.g. ContentScope cleanup after Exit()),
    // but in that case ExitEventLoop has already been called.
    if (Task.Completed())
    {
        VerseCmd::ExitEventLoop(VerseCmd::FEventLoopExit::ScriptCompleted());
    }
}

AUTORTFM_DISABLE VerseCmd::FEventLoopExit VerseCmd::RunScript(const TSharedPtr<VerseCmd::FScript>& Script,
                                                              const TArray<verse::string>& Args,
                                                              const TMap<verse::string, verse::string>& Env)
{
    // Disable computation limits.
    VerseComputationLimitControl::SetComputationLimits(false);

    // Enqueue a job for the event loop to run that calls the script Main function.
    EnqueueAsyncJob([Script, Args, Env](const verse::FExecutionContext& ExecContext) {
        const AutoRTFM::ETransactionResult TransactionResult = AutoRTFM::Transact([&] {
            FVerseTask ScriptTask = Script->MainFunction(ExecContext, Args, Env);
            // Use Await to get a notification when the Main function returns.
            ScriptTask.Await(ExecContext, OnScriptTaskFinished);
        });
        // Use the transaction not committing as a proxy for Main raising a runtime error before it yields.
        if (TransactionResult != AutoRTFM::ETransactionResult::Committed)
        {
            ExitEventLoop(FEventLoopExit::Error());
        }
    });

    // We don't have a UWorld to use as the outer for our content scope, so we synthesize an empty placeholder object.
    UPlaceholderObjectForContentScope* PlaceholderObject = UPlaceholderObjectForContentScope::MakeRooted();
    TSharedRef<verse::FContentScope> ContentScope = verse::MakeContentScope(PlaceholderObject);

    // Run the event loop until termination.
    verse::FContentScopeGuard ContentScopeGuard(ContentScope);
    return RunEventLoop(verse::FExecutionContext::GetActiveContext());
}
