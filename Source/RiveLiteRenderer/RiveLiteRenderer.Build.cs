// Isolated Rive UE RHI/RDG prototype. Native runtime ABI matches the vendor build.
using System;
using System.IO;
using UnrealBuildTool;

public class RiveLiteRenderer : ModuleRules
{
    public RiveLiteRenderer(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // UE6 Core headers use if consteval. The native Rive ABI remains C++20.
        CppStandard = CppStandardVersion.Cpp23;
        PublicIncludePathModuleNames.Add("Shaders");
        PublicDependencyModuleNames.AddRange(new[] { "Core", "RHI", "RHICore", "RenderCore" });
        PrivateDependencyModuleNames.AddRange(new[] { "CoreUObject", "ImageWrapper" });
        PublicIncludePaths.Add(Path.Combine(ModuleDirectory, "Public"));
        PrivateIncludePaths.Add(Path.Combine(ModuleDirectory, "Private"));

        string PrototypeRoot = Path.GetFullPath(Path.Combine(ModuleDirectory, "../.."));
        string NativeRoot = Path.Combine(PrototypeRoot, "vendor", "rive-unreal", "Source", "ThirdParty", "RiveLibrary");
        string IncludeRoot = Environment.GetEnvironmentVariable("RIVE_LITE_INCLUDE_DIR") ?? Path.Combine(NativeRoot, "Includes");
        PublicSystemIncludePaths.Add(IncludeRoot);
        RiveNativeLibraries.Add(this, Target, NativeRoot);
        AddEngineThirdPartyPrivateStaticDependencies(Target, "zlib");
        PublicDefinitions.AddRange(new[] {
            "RIVE_UNREAL", "WITH_RIVE=1", "RIVE_CANVAS=1", "RIVE_ORE=1",
            "ORE_BACKEND_RHI=1", "TRACK_RIVE_SHADER_ID", "RIVE_WITH_UNREAL=1",
            "WITH_RIVE_AUDIO=1", "EXTERNAL_RIVE_AUDIO_ENGINE=1", "RIVE_LITE_ORE_ENABLED=0",
            "WITH_RIVE_TEXT=1", "WITH_RIVE_LAYOUT=1", "MA_NO_DEVICE_IO", "MA_NO_RESOURCE_MANAGER"
        });
        if (Environment.GetEnvironmentVariable("RIVE_LITE_SCRIPTING") == "1")
            PublicDefinitions.Add("WITH_RIVE_SCRIPTING=1");
    }
}

// Shared selection only; neither renderer module depends on the other.
public static class RiveNativeLibraries
{
    public static void Add(ModuleRules Rules, ReadOnlyTargetRules Target, string NativeRoot)
    {
        string DirectoryName;
        string Pattern = "*.a";
        if (Target.Platform == UnrealTargetPlatform.Mac)
        {
            // Build each architecture separately. Do not feed both thin archives
            // into one link; a universal package needs independently verified slices.
            if (Target.Architectures.Architectures.Count != 1)
                throw new BuildException("Rive Mac: select one architecture (-architecture=arm64 or x64).");
            DirectoryName = Path.Combine("Mac", Target.Architecture == UnrealArch.Arm64 ? "Mac" : "Intel");
            Rules.PublicDefinitions.Add(Target.Architecture == UnrealArch.Arm64 ? "WITH_RIVE_MAC_ARM64=1" : "WITH_RIVE_MAC_INTEL=1");
        }
        else if (Target.Platform == UnrealTargetPlatform.Linux)
            DirectoryName = "Linux";
        else if (Target.Platform == UnrealTargetPlatform.Win64)
        {
            DirectoryName = "Win64";
            Pattern = "*.lib";
        }
        else throw new BuildException("Unsupported Rive native platform: " + Target.Platform);

        string Root = Environment.GetEnvironmentVariable("RIVE_LITE_NATIVE_LIB_DIR") ?? Path.Combine(NativeRoot, "Libraries", DirectoryName);
        if (!Directory.Exists(Root)) throw new BuildException("Missing Rive native library directory: " + Root);
        int Count = 0;
        foreach (string Archive in Directory.GetFiles(Root, Pattern))
        {
            string Name = Path.GetFileNameWithoutExtension(Archive);
            if (Name.EndsWith("_d", StringComparison.Ordinal)) continue;
            // Use the engine's zlib on all platforms, including libzlib.a on Mac.
            if (Name == "rive_libzlib" || Name == "libzlib" || Name == "zlib" || Name == "rive_zlib") continue;
            if (Name.Contains("luau") && Environment.GetEnvironmentVariable("RIVE_LITE_SCRIPTING") != "1") continue;
            if (new FileInfo(Archive).Length < 256)
                throw new BuildException("Rive native archive is an LFS pointer or invalid: " + Archive);
            Rules.PublicAdditionalLibraries.Add(Archive);
            ++Count;
        }
        if (Count == 0) throw new BuildException("No Rive native archives in " + Root);
    }
}
