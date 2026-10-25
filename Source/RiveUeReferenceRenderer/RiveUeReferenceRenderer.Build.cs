using System;
using System.IO;
using UnrealBuildTool;

public class RiveUeReferenceRenderer : ModuleRules
{
    public RiveUeReferenceRenderer(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp23;
        PublicIncludePathModuleNames.Add("Shaders");
        PublicDependencyModuleNames.AddRange(new[] { "Core", "Engine", "RHI", "RHICore", "RenderCore" });
        PrivateDependencyModuleNames.AddRange(new[] { "CoreUObject", "Renderer", "Projects", "ImageWrapper" });
        PublicIncludePaths.Add(Path.Combine(ModuleDirectory, "Public"));
        PrivateIncludePaths.Add(Path.Combine(ModuleDirectory, "Private"));
        string PrototypeRoot = Path.GetFullPath(Path.Combine(ModuleDirectory, "../.."));
        string NativeRoot = Path.Combine(PrototypeRoot, "vendor", "rive-unreal", "Source", "ThirdParty", "RiveLibrary");
        string IncludeRoot = Environment.GetEnvironmentVariable("RIVE_LITE_INCLUDE_DIR") ?? Path.Combine(NativeRoot, "Includes");
        string LibraryRoot = Environment.GetEnvironmentVariable("RIVE_LITE_NATIVE_LIB_DIR") ?? Path.Combine(NativeRoot, "Libraries", "Linux");
        PublicSystemIncludePaths.Add(IncludeRoot);
        if (Directory.Exists(LibraryRoot))
            foreach (string Archive in Directory.GetFiles(LibraryRoot, "*.a"))
                if (!Archive.EndsWith("_d.a", StringComparison.Ordinal) && Path.GetFileName(Archive) != "rive_libzlib.a")
                    PublicAdditionalLibraries.Add(Archive);
        AddEngineThirdPartyPrivateStaticDependencies(Target, "zlib");
        PublicDefinitions.AddRange(new[] {
            "RIVE_UNREAL", "WITH_RIVE=1", "RIVE_CANVAS=1", "RIVE_ORE=1", "ORE_BACKEND_RHI=1",
            "TRACK_RIVE_SHADER_ID", "RIVE_WITH_UNREAL=1", "WITH_RIVE_AUDIO=1", "EXTERNAL_RIVE_AUDIO_ENGINE=1",
            "WITH_RIVE_TEXT=1", "WITH_RIVE_LAYOUT=1", "MA_NO_DEVICE_IO", "MA_NO_RESOURCE_MANAGER", "RIVE_LITE_ORE_ENABLED=0"
        });
    }
}
