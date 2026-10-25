#!/usr/bin/env python3
"""Extract the prototype's tested Core bootstrap, never shader compiler code."""
import hashlib
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("extractor", root / "Source/RiveLiteShaderCompiler/generate_shader_support.py")
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)
source = root / "Source/RiveUeReference/Private/Main.cpp"
text = source.read_text(encoding="utf-8-sig")
pool = extractor.function(text, "static void CreateReferencePool(")
pool = pool.replace("128 * 1024", "1024 * 1024")
bootstrap = extractor.function(text, "static void BootstrapReferenceCore(")
objects = extractor.function(bootstrap, "if (InitializeObjects)")
bootstrap = bootstrap.replace(objects, "")
bootstrap = bootstrap.replace("BootstrapReferenceCore(bool InitializeObjects)", "BootstrapCore()")
bootstrap = bootstrap.replace("RiveUeReference", "RiveUeShaderCooker").replace("GReferenceStdOut", "GCookerStdOut")
bootstrap = bootstrap.replace("GIsClient = true;", "GIsClient = false;\n    GIsEditor = true;\n    PRIVATE_GIsRunningCommandlet = true;\n    PRIVATE_GIsRunningCookCommandlet = true;\n    GUsingNullRHI = true;")
bootstrap = bootstrap.replace("RiveUeShaderCookerRenderer", "RiveUeReferenceRenderer")
bootstrap = bootstrap.replace(
    'CreateReferencePool(GThreadPool, 4, TPri_SlightlyBelowNormal, TEXT("ReferenceWorkers"));',
    'GLargeThreadPool = new FQueuedLowLevelThreadPool();\n    GThreadPool = new FQueuedThreadPoolWrapper(GLargeThreadPool, 4);')
# Match the native WITH_EDITOR startup ordering and configuration calls in
# LaunchEngineLoop.cpp. No shader-input preparation is extracted or copied.
core_modules = '''    RegisterModularObjectsProcessing();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("CoreUObject"));
'''
bootstrap = bootstrap.replace(core_modules, "")
bootstrap = bootstrap.replace('    FCoreDelegates::OnInit.Broadcast();\n', "")
bootstrap = bootstrap.replace('    FConfigCacheIni::InitializeConfigSystem();', core_modules + '''    InitializeRenderingCVarsCaching();
    FConfigCacheIni::InitializeConfigSystem();
    FCoreDelegates::OnInit.Broadcast();
    for (const TCHAR* Section : {
        TEXT("/Script/Engine.RendererSettings"),
        TEXT("/Script/Engine.RendererOverrideSettings"),
        TEXT("/Script/Engine.StreamingSettings"),
        TEXT("/Script/Engine.GarbageCollectionSettings"),
        TEXT("/Script/Engine.NetworkSettings"),
        TEXT("/Script/UnrealEd.CookerSettings")})
        UE::ConfigUtilities::ApplyCVarSettingsFromIni(Section, *GEngineIni, ECVF_SetByProjectSetting);
    Scalability::InitScalabilitySystem();
#if UE_WITH_CONSTINIT_UOBJECT
    UE::CoreUObject::ConstructCompiledInObjects();
#endif
    UDeviceProfileManager::InitializeCVarsForActiveDeviceProfile();
    Scalability::LoadState(GGameUserSettingsIni);''')
output = Path(__file__).resolve().parent / "Private/CanonicalBootstrap.inl"
output.write_text("// Core bootstrap only; extracted from the independently built Engine reference.\n" + pool + "\n\n" + bootstrap + "\n", encoding="utf-8")
output.with_suffix(".provenance.json").write_text(json.dumps({
    "source": source.relative_to(root).as_posix(), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "scope": "Core initialization only; no lite SetupInput or copied shader compilation algorithm",
    "native_editor_bootstrap_reference": "engine/Engine/Source/Runtime/Launch/Private/LaunchEngineLoop.cpp",
    "native_editor_bootstrap_reference_sha256": hashlib.sha256((root / "engine/Engine/Source/Runtime/Launch/Private/LaunchEngineLoop.cpp").read_bytes()).hexdigest(),
    "native_editor_steps": ["CoreUObject before CVar sinks", "InitializeRenderingCVarsCaching", "project settings / scalability / constinit objects / device-profile CVars", "GLargeThreadPool and real queued wrapper", "1 MiB worker stack"],
}, indent=2) + "\n", encoding="utf-8")
print(output)
