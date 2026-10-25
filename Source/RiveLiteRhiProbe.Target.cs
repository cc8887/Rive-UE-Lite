using UnrealBuildTool;

// Intermediate graphics-bootstrap probe. Its clear image is not Rive evidence.
[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveLiteRhiProbeTarget : TargetRules
{
    public RiveLiteRhiProbeTarget(TargetInfo Target) : base(Target)
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
        bCreateMapFile = true;
        GlobalDefinitions.Add("RIVE_LITE_WITH_RIVE=0");
    }
}
