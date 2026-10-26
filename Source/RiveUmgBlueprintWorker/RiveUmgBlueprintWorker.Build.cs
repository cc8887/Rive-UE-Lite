using UnrealBuildTool;

public class RiveUmgBlueprintWorker : ModuleRules
{
    public RiveUmgBlueprintWorker(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp23;
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "ApplicationCore", "Projects", "Engine", "Renderer", "RHI", "RHICore",
            "RenderCore", "ImageCore", "ImageWrapper", "VulkanRHI", "Json", "Slate", "SlateCore", "SlateRHIRenderer",
            "UMG", "UMGEditor", "UnrealEd", "BlueprintGraph", "Kismet", "AssetRegistry", "NullDrv", "SlateNullRenderer", "TargetPlatform",
            "MovieScene", "MovieSceneTracks"
        });
        DynamicallyLoadedModuleNames.Add("LinuxTargetPlatform");
        PrivateIncludePaths.Add(System.IO.Path.Combine(GetModuleDirectory("RenderCore"), "Internal"));
    }
}
