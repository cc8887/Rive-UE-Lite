// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class RiveVerseWorker : ModuleRules
{
	public RiveVerseWorker(ReadOnlyTargetRules Target) : base(Target)
	{
		bForceIncludeTestsFolder = true;

		SetupVerse("/Verse.org/Verse", VerseScope.PublicAPI);

		PublicIncludePathModuleNames.Add("Launch");

		PrivateDependencyModuleNames.AddRange(new string[]{
			"VerseProgramHostServices",

			"ApplicationCore",
			"Core",
			"CoreUObject",
			"Projects",
			"SolarisBridge",
			"SolarisTestUtils",
			"ScriptDisassembler",
			"Solaris",
			"uLangUE",
			"uLangCore",
			"VerseCompiler",
			"VerseVMCodeGen",
			"VerseVMSocketDebugger",
			"VerseNative",
			"Verse",
		});

		CppCompileWarningSettings.SwitchUnhandledEnumeratorWarningLevel = WarningLevel.Error;
		CppCompileWarningSettings.UnsafeTypeCastWarningLevel = WarningLevel.Error;
	}
}
