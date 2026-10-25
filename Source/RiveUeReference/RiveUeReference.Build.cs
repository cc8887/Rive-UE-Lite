using System.IO;
using UnrealBuildTool;

public class RiveUeReference : ModuleRules
{
    public RiveUeReference(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../RivePlayback/Public")));
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Projects", "ApplicationCore", "Engine", "Renderer", "RHI", "RHICore",
            "RenderCore", "ImageCore", "ImageWrapper", "VulkanRHI", "RiveUeReferenceRenderer", "Json"
        });
    }
}
