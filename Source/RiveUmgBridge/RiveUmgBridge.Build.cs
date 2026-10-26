using UnrealBuildTool;

public class RiveUmgBridge : ModuleRules
{
    public RiveUmgBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "RHI", "RenderCore", "SlateCore" });
        PrivateDependencyModuleNames.AddRange(new[] {
            "CoreUObject", "ApplicationCore", "Engine", "Renderer", "UMG", "Slate", "SlateRHIRenderer"
        });
    }
}
