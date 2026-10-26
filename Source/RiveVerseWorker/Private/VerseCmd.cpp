// Copyright Epic Games, Inc. All Rights Reserved.

#include "AutoRTFM.h"
#include "AutoRTFM/AutoRTFMTestingUE.h"
#include "Containers/Map.h"
#include "Containers/StringView.h"
#include "Containers/UnrealString.h"
#include "Env.h"
#include "EventLoop.h"
#include "GenericPlatform/GenericPlatformMisc.h"
#include "ISolarisModule.h"
#include "Misc/CString.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "RequiredProgramMainCPPInclude.h"
#include "Script.h"
#include "Templates/SharedPointer.h"
#include "Templates/UnrealTemplate.h"
#include "VerseString.h"
#include "VerseVM/VVMSocketDebugger.h"
#include <stdio.h>  // for fprintf
#include <string.h> // for strchr

IMPLEMENT_APPLICATION(RiveVerseWorker, "RiveVerseWorker");
static_assert(WITH_VERSE_VM && !WITH_VERSE_BPVM && !WITH_ENGINE,
              "This optional worker must use VerseVM without Engine.");

namespace {
struct FVerseCmdCommandLine
{
    bool bHelp{false};
    bool bWaitForDebugger{false};
    bool bEnableDebugger{false};
    TArray<VerseCmd::FMount> Mounts;
    FUtf8String ScriptFilePath;
    TArray<FUtf8String> ScriptArguments;
};
}

AUTORTFM_DISABLE static void PrintHelp()
{
    fprintf(stdout,
            "Usage: verse [options] <script file> [script arguments]\n"
            "\n"
            "Arguments before <script file> are processed by verse.\n"
            "Arguments after <script file> are passed through to the script.\n"
            "\n"
            "Options:\n"
            "--help                                    Shows this message.\n"
            "--mount|-m <verse path>:<directory>       Makes the Verse module in <directory>\n"
            "                                            available for the script to import as\n"
            "                                            <verse path>.\n"
            "--wait-for-debugger                       Before running the script, starts a\n"
            "                                            debug server and waits for a debugger\n"
            "                                            to attach to it.\n"
            "--enable-debugger                         Starts a debug server, then runs the\n"
            "                                            script without waiting for a debugger\n"
            "                                            to attach.\n");
}

AUTORTFM_DISABLE static bool ParseCommandLine(int argc, char* argv[], FVerseCmdCommandLine& OutCommandLine)
{
    for (int i = 1; i < argc; ++i)
    {
        if (argv[i][0] == '-')
        {
            if (!strcmp(argv[i], "--help"))
            {
                OutCommandLine.bHelp = true;
            }
            else if (!strcmp(argv[i], "--wait-for-debugger"))
            {
                OutCommandLine.bWaitForDebugger = true;
            }
            else if (!strcmp(argv[i], "--enable-debugger"))
            {
                OutCommandLine.bEnableDebugger = true;
            }
            else if (!strcmp(argv[i], "-m") || !strcmp(argv[i], "--mount"))
            {
                if (i + 1 >= argc)
                {
                    fprintf(stderr, "Error: Expected argument following %s\n", argv[i]);
                    return false;
                }
                ++i;

                const char* Colon = TCString<ANSICHAR>::Strchr(argv[i], ':');
                if (!Colon)
                {
                    fprintf(
                        stderr,
                        "Error: Expected '<verse path>:<directory>' as mount specification after '%s', but got '%s'\n",
                        argv[i - 1],
                        argv[i]);
                    return false;
                }

                FUtf8StringView VersePath(argv[i], Colon - argv[i]);
                FUtf8StringView Directory(Colon + 1);
                OutCommandLine.Mounts.Add(
                    VerseCmd::FMount{.VersePath = FUtf8String(VersePath), .Directory = FUtf8String(Directory)});
            }
            else
            {
                fprintf(stderr, "Error: Unrecognized flag '%s'\n", argv[i]);
                return false;
            }
        }
        else
        {
            OutCommandLine.ScriptFilePath = FUtf8String(argv[i]);

            // Interpret the rest of the arguments as arguments to the script.
            for (++i; i < argc; ++i)
            {
                OutCommandLine.ScriptArguments.Add(FUtf8String(argv[i]));
            }

            return true;
        }
    }

    if (OutCommandLine.bHelp)
    {
        return true;
    }

    fprintf(stderr, "Error: Did not find script file path on command line.\n");
    return false;
}

struct FVerseCmdMainInitScope
{
    AUTORTFM_DISABLE bool Init(int argc, char* argv[])
    {
        check(!bInitialized);

        AutoRTFM::Testing::PrintCallstackOnCrash(/* 30 min timeout */ 60 * 30);

        // Causes FApp:IsUnattended()=true, which prevents the crash reporter from popping up a dialog.
        GIsAutomationTesting = true;

        GIsEditor = true;

        // Suppress AssetRegistry file system scan on init.
        const char* ExtraUECommandLine = "-NOCONSOLE -AssetGatherAll=0 -LogCmds=\"global Warning\"";

        if (GEngineLoop.PreInit(*FCommandLine::BuildFromArgV(nullptr, 1, argv, ExtraUECommandLine)) != 0)
        {
            fprintf(stderr, "Failed to initialize the engine (PreInit failed).\n"); // uLang not initialized yet here
            return false;
        }

        // Initialize the garbage collector. (Otherwise, if no active test uses garbage collection,
        // `CollectGarbage` can potentially fail.)
        FGCObject::StaticInit();

        // Loading the Solaris module initializes the uLang system params for UE integration.
        ISolarisModule::Get();

        bInitialized = true;
        return true;
    }

    AUTORTFM_DISABLE ~FVerseCmdMainInitScope()
    {
        if (bInitialized)
        {
            // Shut the engine down gracefully.
            FCoreDelegates::OnEnginePreExit.Broadcast();
            FCoreDelegates::OnPreExit.Broadcast();
            FCoreDelegates::OnExit.Broadcast();
            FModuleManager::Get().UnloadModulesAtShutdown();
            FEngineLoop::AppPreExit();
            RequestEngineExit(TEXT("verse completed."));
            FEngineLoop::AppExit();
            bInitialized = false;
        }
    }

private:
    bool bInitialized{false};
};

AUTORTFM_DISABLE int main(int argc, char* argv[])
{
    const double WorkerStarted = FPlatformTime::Seconds();
    FVerseCmdMainInitScope UEInitScope;
    if (!UEInitScope.Init(argc, argv))
    {
        return 1;
    }
    fprintf(stderr, "RIVE_VERSE_PHASE core_ready_ms=%.6f vm=VerseVM\n", (FPlatformTime::Seconds() - WorkerStarted) * 1000.0);

    FVerseCmdCommandLine CommandLine;
    if (!ParseCommandLine(argc, argv, CommandLine))
    {
        PrintHelp();
        return 1;
    }

    if (CommandLine.bHelp)
    {
        PrintHelp();
        return 0;
    }

    Verse::SocketDebugger::FDebuggerScope DebuggerScope;
    if (CommandLine.bWaitForDebugger)
    {
        DebuggerScope = Verse::SocketDebugger::WaitForAttach();
    }
    else if (CommandLine.bEnableDebugger)
    {
        DebuggerScope = Verse::SocketDebugger::Listen();
    }

    // Resolve the script path to absolute for BuildScript, which uses UE file APIs
    // that don't respect the process CWD (UE changes it to the engine base dir).
    FUtf8String AbsScriptPath = CommandLine.ScriptFilePath;
    if (FPaths::IsRelative(FString(AbsScriptPath)))
    {
        AbsScriptPath = FUtf8String(
            StringCast<UTF8CHAR>(*FPaths::Combine(FPlatformMisc::LaunchDir(), FString(AbsScriptPath))).Get());
    }

    const double CompileStarted = FPlatformTime::Seconds();
    TSharedPtr<VerseCmd::FScript> Script = VerseCmd::BuildScript(AbsScriptPath, CommandLine.Mounts);
    if (!Script)
    {
        return 1;
    }
    fprintf(stderr, "RIVE_VERSE_PHASE compile_load_ms=%.6f ready_ms=%.6f\n", (FPlatformTime::Seconds() - CompileStarted) * 1000.0, (FPlatformTime::Seconds() - WorkerStarted) * 1000.0);

    TArray<verse::string> CombinedScriptArguments;
    CombinedScriptArguments.Add(verse::string(CommandLine.ScriptFilePath));
    for (const FUtf8String& Arg : CommandLine.ScriptArguments)
    {
        CombinedScriptArguments.Add(verse::string(Arg));
    }

    TMap<verse::string, verse::string> ScriptEnvironment = VerseCmd::GetProcessEnvironment();

    const double ExecuteStarted = FPlatformTime::Seconds();
    VerseCmd::FEventLoopExit Exit = VerseCmd::RunScript(Script, CombinedScriptArguments, ScriptEnvironment);
    fprintf(stderr, "RIVE_VERSE_PHASE execute_ms=%.6f exit_code=%lld\n", (FPlatformTime::Seconds() - ExecuteStarted) * 1000.0, static_cast<long long>(Exit.ExitCode));
    if (Exit.Reason == VerseCmd::FEventLoopExit::EReason::Error)
    {
        fprintf(stderr, "Error: error encountered while executing script.\n");
    }

    return Exit.ExitCode;
}
