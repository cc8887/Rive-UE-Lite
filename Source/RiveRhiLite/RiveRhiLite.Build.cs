using System.IO;
using UnrealBuildTool;

public class RiveRhiLite : ModuleRules
{
    public RiveRhiLite(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicIncludePathModuleNames.Add("Launch");
        PrivateIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../RivePlayback/Public")));
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Projects", "ApplicationCore", "RHI", "RHICore",
            "RenderCore", "ImageCore", "ImageWrapper", "VulkanRHI", "Json"
        });
        if (Target.Name != "RiveLiteRhiProbe")
            PrivateDependencyModuleNames.Add("RiveLiteRenderer");
    }
}
