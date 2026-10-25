using System.IO;
using UnrealBuildTool;

public class RiveLiteShaderCompiler : ModuleRules
{
    public RiveLiteShaderCompiler(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicIncludePathModuleNames.Add("Launch");
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Projects", "ApplicationCore", "RHI", "RenderCore",
            "TargetPlatform", "ShaderCompilerCommon", "VulkanShaderFormat", "Json",
            "RiveLiteRenderer"
        });
        DynamicallyLoadedModuleNames.Add("LinuxTargetPlatform");
        // FShaderSerializeContext is a RenderCore internal API, intentionally pinned to this fork.
        PrivateIncludePaths.Add(Path.Combine(GetModuleDirectory("RenderCore"), "Internal"));
    }
}
