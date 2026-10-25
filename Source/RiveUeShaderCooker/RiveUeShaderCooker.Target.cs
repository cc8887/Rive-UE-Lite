using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveUeShaderCookerTarget : TargetRules
{
    public RiveUeShaderCookerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveUeShaderCooker";
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
        bUsesSlate = false;
        bIsBuildingConsoleApplication = true;
        bUseUnityBuild = true;
        bCreateMapFile = true;
        GlobalDefinitions.Add("UE_WITH_TURNKEY_SUPPORT=0");
        // Native Programs/UnrealAssetStringify enables this same Core API override.
        GlobalDefinitions.Add("ALLOW_OTHER_PLATFORM_CONFIG=1");
        GlobalDefinitions.Add("UE_RIVE_STANDALONE_SHADER_COOKER=1");
    }
}
