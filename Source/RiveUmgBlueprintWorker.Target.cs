using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveUmgBlueprintWorkerTarget : TargetRules
{
    public RiveUmgBlueprintWorkerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveUmgBlueprintWorker";
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        bCompileAgainstEngine = true;
        bCompileAgainstEditor = true;
        bCompileAgainstCoreUObject = true;
        bCompileAgainstApplicationCore = true;
        bBuildWithEditorOnlyData = true;
        bBuildDeveloperTools = false;
        bForceDisableAutomationTests = true;
        bCompileICU = false;
        bCompileCEF3 = false;
        OptedInModulePlatforms = new[] { Target.Platform };
        bUsesSlate = true;
        bIsBuildingConsoleApplication = true;
        bUseUnityBuild = true;
        bCreateMapFile = true;
        GlobalDefinitions.Add("UE_WITH_TURNKEY_SUPPORT=0");
        GlobalDefinitions.Add("ALLOW_OTHER_PLATFORM_CONFIG=1");
        // Reuse the isolated Program's existing Engine by-name dependency gate.
        // Actual blueprint/Slate compiler dependencies are explicit below.
        GlobalDefinitions.Add("UE_RIVE_STANDALONE_SHADER_COOKER=1");
    }
}
