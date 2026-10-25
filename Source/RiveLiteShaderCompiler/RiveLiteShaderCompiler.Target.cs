using UnrealBuildTool;

[SupportedPlatforms(UnrealPlatformClass.Desktop)]
public class RiveLiteShaderCompilerTarget : TargetRules
{
    public RiveLiteShaderCompilerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Program;
        LinkType = TargetLinkType.Monolithic;
        LaunchModuleName = "RiveLiteShaderCompiler";
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        BuildEnvironment = TargetBuildEnvironment.Unique;
        bCompileAgainstEngine = false;
        bCompileAgainstCoreUObject = true;
        bCompileAgainstApplicationCore = true;
        // Compilation-environment callbacks are WITH_EDITOR, rather than WITH_EDITORONLY_DATA.
        // This is an offline tool; neither Engine nor UnrealEd is a module dependency.
        bCompileAgainstEditor = true;
        bBuildWithEditorOnlyData = true;
        bBuildDeveloperTools = false;
        bForceDisableAutomationTests = true;
        bUsesSlate = false;
        bCompileICU = false;
        bCompileCEF3 = false;
        bIsBuildingConsoleApplication = true;
        GlobalDefinitions.Add("ALLOW_OTHER_PLATFORM_CONFIG=1");
        GlobalDefinitions.Add("UE_WITH_TURNKEY_SUPPORT=0");
    }
}
