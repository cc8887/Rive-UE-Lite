using UnrealBuildTool;

// Assessment worker only. Not selected by build_ui.sh and not a Verse runtime.
[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class VerseFrontendCostProbeTarget : TargetRules
{
    public VerseFrontendCostProbeTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "VerseCostProbe";
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        bCompileAgainstEngine = false;
        bCompileAgainstCoreUObject = false;
        bCompileAgainstApplicationCore = false;
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
