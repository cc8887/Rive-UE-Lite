using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveUmgHostTarget : TargetRules
{
    public RiveUmgHostTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveUmgHost";
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        bCompileAgainstEngine = true;
        bCompileAgainstEditor = false;
        bCompileAgainstCoreUObject = true;
        bCompileAgainstApplicationCore = true;
        bBuildWithEditorOnlyData = false;
        bBuildDeveloperTools = false;
        bForceDisableAutomationTests = true;
        bCompileICU = false;
        bUsesSlate = true;
        bIsBuildingConsoleApplication = true;
        bUseLoggingInShipping = true;
        bUseUnityBuild = true;
        bCreateMapFile = true;
    }
}
