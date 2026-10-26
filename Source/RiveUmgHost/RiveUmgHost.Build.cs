using System.IO;
using UnrealBuildTool;

public class RiveUmgHost : ModuleRules
{
    public RiveUmgHost(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp23;
        PrivateIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../RivePlayback/Public")));
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Projects", "ApplicationCore", "Engine", "Renderer", "RHI", "RHICore",
            "RenderCore", "ImageCore", "ImageWrapper", "VulkanRHI", "Json", "SlateCore",
            "RiveLiteRenderer", "RiveUmgBridge"
        });
        PrivateDefinitions.Add("RIVE_HOST_WITH_UMG=1");
    }
}
