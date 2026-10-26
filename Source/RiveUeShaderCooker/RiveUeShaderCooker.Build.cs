using System.IO;
using UnrealBuildTool;

public class RiveUeShaderCooker : ModuleRules
{
    public RiveUeShaderCooker(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Projects", "ApplicationCore", "Engine", "Renderer",
            "RHI", "RHICore", "RenderCore", "TargetPlatform", "ShaderCompilerCommon",
            "VulkanShaderFormat", "DerivedDataCache", "NullDrv", "Json", "RiveUeReferenceRenderer", "SlateRHIRenderer"
        });
        DynamicallyLoadedModuleNames.Add("LinuxTargetPlatform");
        PrivateIncludePaths.Add(Path.Combine(GetModuleDirectory("RenderCore"), "Internal"));
    }
}
