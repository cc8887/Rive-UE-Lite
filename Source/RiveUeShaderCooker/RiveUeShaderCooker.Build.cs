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
            "DerivedDataCache", "NullDrv", "Json", "RiveUeReferenceRenderer", "SlateRHIRenderer"
        });
        PrivateDependencyModuleNames.Add(Target.Platform == UnrealTargetPlatform.Mac ? "MetalShaderFormat" : "VulkanShaderFormat");
        DynamicallyLoadedModuleNames.Add(Target.Platform == UnrealTargetPlatform.Mac ? "MacTargetPlatform" : "LinuxTargetPlatform");
        PrivateIncludePaths.Add(Path.Combine(GetModuleDirectory("RenderCore"), "Internal"));
    }
}
