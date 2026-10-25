using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveUeReferenceTarget : TargetRules
{
    public RiveUeReferenceTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveUeReference";
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        bCompileAgainstEngine = true;
        bCompileAgainstEditor = false;
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
    }
}
