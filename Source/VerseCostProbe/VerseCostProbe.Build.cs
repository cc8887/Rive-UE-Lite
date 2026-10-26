using UnrealBuildTool;

public class VerseCostProbe : ModuleRules
{
    public VerseCostProbe(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicIncludePathModuleNames.Add("Launch");
        PrivateDependencyModuleNames.AddRange(new[] {"Core", "Projects"});
        bool Frontend = Target.Name == "VerseFrontendCostProbe";
        PrivateDefinitions.Add("VERSE_COST_FRONTEND=" + (Frontend ? "1" : "0"));
        if (Frontend)
        {
            PrivateDependencyModuleNames.AddRange(new[] {"VerseCompiler", "VerseProgramHostServices"});
        }
    }
}
