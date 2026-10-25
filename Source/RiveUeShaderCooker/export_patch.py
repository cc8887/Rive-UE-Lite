#!/usr/bin/env python3
"""Export cooker-only changes after the existing six-patch baseline."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
engine = root / "engine"
patches = root / "prototype/patches"
paths = [
    "Engine/Source/Runtime/Engine/Engine.Build.cs",
    "Engine/Source/Runtime/AppFramework/AppFramework.Build.cs",
    "Engine/Source/Developer/SourceControl/SourceControl.Build.cs",
    "Engine/Source/Developer/TargetPlatform/TargetPlatform.Build.cs",
    "Engine/Source/Runtime/Engine/Private/Tests/NetTestHelpers.cpp",
    "Engine/Source/Runtime/Engine/Private/World.cpp",
    "Engine/Source/Runtime/Engine/Private/GameInstance.cpp",
    "Engine/Source/Runtime/Engine/Private/AudioDevice.cpp",
    "Engine/Source/Runtime/Engine/Private/PackedLevelActor/PackedLevelActorBuilder.cpp",
    "Engine/Source/Runtime/Engine/Private/KismetRenderingLibrary.cpp",
    "Engine/Source/Runtime/Engine/Private/AnimBlueprint.cpp",
    "Engine/Source/Runtime/Engine/Private/Tests/EngineAutomationTests.cpp",
    "Engine/Source/Runtime/Engine/Private/LevelInstance/LevelInstanceSubsystem.cpp",
    "Engine/Source/Runtime/Engine/Private/EngineGlobals.cpp",
    "Engine/Source/Runtime/Engine/Private/WorldPartition/DataLayer/ExternalDataLayerManager.cpp",
    "Engine/Source/Runtime/Engine/Private/GameModeBase.cpp",
    "Engine/Source/Runtime/Engine/Private/LevelInstance/LevelInstanceEditorPropertyOverrideLevelStreaming.cpp",
    "Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp",
    "Engine/Source/Runtime/Engine/Private/GameEngine.cpp",
    "Engine/Source/Runtime/Engine/Private/Tests/WorldPartition/WorldPartitionStreamingGenerationTests.cpp",
    "Engine/Source/Runtime/Engine/Private/Tests/WorldPartition/WorldPartitionEditorSoftObjectPathTests.cpp",
    "Engine/Source/Runtime/Engine/Private/Tests/WorldPartition/WorldPartitionHandleTests.cpp",
    "Engine/Source/Runtime/Renderer/Private/RayTracing/RayTracing.cpp",
]
with tempfile.TemporaryDirectory(prefix="canonical-patch-", dir=root / "artifacts/setup") as temporary:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
    subprocess.run(["git", "read-tree", "HEAD"], cwd=engine, env=env, check=True)
    subprocess.run(["git", "apply", "--cached", str(patches / "0003-targetplatform-offline-without-turnkey.patch")], cwd=engine, env=env, check=True)
    result = subprocess.run(["git", "diff", "--binary", "--", *paths], cwd=engine, env=env, stdout=subprocess.PIPE, check=True)
    output = patches / "0007-native-cooker-without-editor-ui.patch"
    output.write_bytes(result.stdout)
    print(f"{output}: {len(result.stdout)} bytes")
    report = {
        "schema_version": 1,
        "engine_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=engine, text=True).strip(),
        "patch": output.name,
        "patch_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "requires_preceding_patches": "0001 through 0006 in numeric order; TargetPlatform delta follows 0003",
        "target_definition": "UE_RIVE_STANDALONE_SHADER_COOKER=1",
        "scope": "Offline Engine Program only: omit optional authoring modules and guard unused editor UI, asset creation, movie capture, disabled test includes and world ray-tracing instance sink registration; preserve normal-target branches and reflected field layouts",
        "native_shader_pipeline": "Original Engine BeginCompileShader, GlobalBeginCompileShader, manager, View metadata and native archive serializer are not changed by this patch",
        "shared_preprocessor_exception": "0006 repairs upstream multiline token paste for both independently executed compilers",
        "modified_source_files": [
            {"path": path, "sha256": hashlib.sha256((engine / path).read_bytes()).hexdigest()}
            for path in paths
        ],
    }
    (patches / "native-cooker-source-cuts.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
