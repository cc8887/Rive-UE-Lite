using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveRhiLiteTarget : TargetRules
{
    public RiveRhiLiteTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveRhiLite";
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        bCompileAgainstEngine = false;
        bCompileAgainstCoreUObject = true;
        bCompileAgainstApplicationCore = true;
        bBuildWithEditorOnlyData = false;
        bBuildDeveloperTools = false;
        bForceDisableAutomationTests = true;
        bCompileICU = false;
        bUsesSlate = false;
        bIsBuildingConsoleApplication = true;
        bUseLoggingInShipping = true;
        bUseUnityBuild = true;
        bCreateMapFile = true;
        GlobalDefinitions.Add("RIVE_LITE_WITH_RIVE=1");
    }
}
