using UnrealBuildTool;

// Optional language process. Never selected by the default Rive build.
[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveVerseWorkerTarget : TargetRules
{
    public RiveVerseWorkerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveVerseWorker";
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        bCompileAgainstEngine = false;
        bCompileAgainstCoreUObject = true;
        bCompileAgainstApplicationCore = true;
        bBuildWithEditorOnlyData = true;
        bBuildDeveloperTools = false;
        bForceDisableAutomationTests = true;
        bCompileICU = false;
        bUsesSlate = false;
        bIsBuildingConsoleApplication = true;
        bUseLoggingInShipping = true;
        bUseUnityBuild = true;
        bCreateMapFile = true;
        bUseVerseBPVM = false;
        bUseAutoRTFMCompiler = true;
        AutoRTFM.EnableModuleDefaults = true;
        GlobalDefinitions.Add("ALLOW_LOG_FILE=0");
        GlobalDefinitions.Add("NOINITCRASHREPORTER=1");
    }
}
