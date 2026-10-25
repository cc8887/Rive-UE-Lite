"""Small fixtures validate acceptance gates, alpha comparison and mask policy."""
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from compare_png import compare_images, read_png
from measure_ue_lite import apply_cpu_profile, cpu_devices, inspect_build, inspect_vulkan_dependencies, parse_link_modules, reference_provenance, rive_draw_evidence, run_once, runtime_device, summarize_status
from compare_png import sha256
from measure_pair import reference_capture_evidence, source_pins
from measure_playback_matrix import coverage_evidence, input_effect_evidence, inspect_cook_provenance, inspect_independent_cooks, legacy_playback_evidence, pixel_content_evidence, playback_evidence, validate_scenario


def png(path, pixels, width=2, color_metadata=None):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    height = len(pixels) // width
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    if color_metadata:
        data += chunk(b"sRGB", bytes([color_metadata]))
    raw = b"".join(b"\x00" + bytes(value for pixel in pixels[row * width:(row + 1) * width] for value in pixel) for row in range(height))
    path.write_bytes(data + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_alpha_and_mask(self):
        a, b, mask = (self.root / name for name in ("a.png", "b.png", "mask.png"))
        png(a, [(10, 20, 30, 255), (40, 50, 60, 255)])
        png(b, [(10, 20, 30, 254), (40, 50, 60, 255)])
        self.assertEqual(compare_images(a, a)["status"], "passed")
        comparison = compare_images(a, b)
        self.assertEqual(comparison["status"], "failed")
        self.assertEqual(comparison["alpha_different_pixels"], 1)
        self.assertEqual(comparison["different_pixel_fraction"], 0.5)
        png(mask, [(0, 0, 0, 255), (255, 255, 255, 255)])
        self.assertEqual(compare_images(a, b, mask)["status"], "passed")
        self.assertEqual(compare_images(a, b, channel_tolerance=1)["status"], "passed")

    def test_missing_corrupt_size_and_colorspace(self):
        a, b = self.root / "a.png", self.root / "b.png"
        self.assertEqual(compare_images(a, b)["status"], "incomplete")
        png(a, [(0, 0, 0, 255), (1, 1, 1, 255)])
        png(b, [(0, 0, 0, 255), (1, 1, 1, 255)], width=1)
        self.assertEqual(compare_images(a, b)["status"], "failed")
        png(b, [(0, 0, 0, 255), (1, 1, 1, 255)], color_metadata=1)
        self.assertEqual(compare_images(a, b)["reason"], "color metadata differs; no implicit color conversion is permitted")
        b.write_bytes(a.read_bytes()[:-4])
        self.assertEqual(compare_images(a, b)["status"], "incomplete")

    def test_receipt_alone_cannot_prove_module_exclusion(self):
        receipt, link = self.root / "RiveLite.target", self.root / "RiveLite.rsp"
        executable = self.root / "RiveLite"
        receipt.write_text(json.dumps({"BuildProducts": [{"Path": "$(EngineDir)/Binaries/Linux/RiveLite"}]}))
        self.assertEqual(inspect_build([receipt], [], executable)["status"], "incomplete")
        link.write_text("Module.Core.1.cpp.o Module.RHI.cpp.o Module.RenderCore.2.cpp.o Module.RiveLiteRenderer.cpp.o")
        self.assertEqual(inspect_build([receipt], [link], executable)["status"], "passed")
        link.write_text(link.read_text() + " Module.Renderer.5.cpp.o")
        self.assertEqual(inspect_build([receipt], [link], executable)["status"], "failed")
        self.assertNotIn("Renderer", parse_link_modules("Module.RiveLiteRenderer.cpp.o"))

    def test_recursive_linker_response_and_missing_nested_input(self):
        receipt, driver, objects = (self.root / name for name in ("RiveLite.target", "RiveLite.link.rsp", "RiveLite.rsp"))
        executable = self.root / "RiveLite"
        receipt.write_text(json.dumps({"BuildProducts": [{"Path": "$(EngineDir)/Binaries/Linux/RiveLite"}]}))
        driver.write_text(f'-o "{executable.as_posix()}"\n-Wl,@"{objects.as_posix()}"\n')
        self.assertEqual(inspect_build([receipt], [driver], executable)["status"], "incomplete")
        objects.write_text("Module.Core.1.cpp.o Module.RHI.cpp.o Module.RenderCore.2.cpp.o")
        report = inspect_build([receipt], [driver], executable)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["evidence"]), 3)
        objects.write_text(objects.read_text() + " Module.Engine.1.cpp.o")
        self.assertEqual(inspect_build([receipt], [driver], executable)["status"], "failed")

    def test_cpu_evidence_and_incomplete_gates(self):
        self.assertEqual(cpu_devices("deviceType = PHYSICAL_DEVICE_TYPE_CPU\ndeviceName = llvmpipe")["status"], "passed")
        self.assertEqual(cpu_devices("deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU")["status"], "failed")
        self.assertEqual(runtime_device("enumerated llvmpipe device")["status"], "incomplete")
        self.assertEqual(runtime_device("Selected Vulkan device: llvmpipe deviceType=CPU")["status"], "passed")
        self.assertEqual(runtime_device('RIVE_LITE_CAPTURE adapter="llvmpipe (LLVM 20.1.2, 256 bits)" probe_only=0 render_path=UE_RHI_RDG RiveDrawCompleted=1')["status"], "passed")
        self.assertEqual(runtime_device('RIVE_UE_REFERENCE_CAPTURE adapter="llvmpipe (LLVM 20.1.2, 256 bits)" render_path=UE_RHI_RDG engine_frender_target=1')["status"], "passed")
        self.assertEqual(summarize_status({"a": {"status": "passed"}, "b": {"status": "incomplete"}}), "incomplete")

    def test_dependency_inventory_requires_successful_loader_and_ldd_probes(self):
        package = self.root / "package"
        package.mkdir()
        loader, driver, shared = (self.root / name for name in ("libvulkan.so.1", "libvulkan_lvp.so", "libshared.so"))
        loader.write_bytes(b"loader")
        driver.write_bytes(b"driver")
        shared.write_bytes(b"shared")
        icd = self.root / "lvp.json"
        icd.write_text(json.dumps({"ICD": {"library_path": driver.name}}))
        app = {"logical_file_bytes": 100, "ldd_inspection": {"exit_code": 0},
               "dynamic_dependencies": [{"name": shared.name, "resolved": str(shared)}]}

        def lookup(name, *, path):
            self.assertIn("/sbin", path)
            self.assertIn("/usr/sbin", path)
            return "/sbin/ldconfig"

        def probes(command):
            if command[0] == "/sbin/ldconfig":
                output = f" {loader.name} (libc6,x86-64) => {loader}\n {driver.name} (libc6,x86-64) => {driver}\n"
            else:
                output = f" {shared.name} => {shared} (0x0000)\n"
            return {"command": command, "exit_code": 0, "output": output}

        with mock.patch("measure_ue_lite.shutil.which", side_effect=lookup), mock.patch("measure_ue_lite.capture", side_effect=probes):
            inventory = inspect_vulkan_dependencies(icd, package, app)
        self.assertEqual(inventory["status"], "passed")
        self.assertTrue(inventory["inventory_complete"])
        self.assertFalse(inventory["standalone_bundle"])
        self.assertEqual(inventory["external_library_bytes_deduplicated"], 18)
        self.assertEqual(len(inventory["libraries"]), 3)
        self.assertTrue(all(row["sha256"] for row in inventory["libraries"]))

        def broken_ldd(command):
            return probes(command) if command[0] == "/sbin/ldconfig" else {"command": command, "error": "ldd unavailable"}

        with mock.patch("measure_ue_lite.shutil.which", side_effect=lookup), mock.patch("measure_ue_lite.capture", side_effect=broken_ldd):
            incomplete = inspect_vulkan_dependencies(icd, package, app)
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertTrue(incomplete["unresolved"])
        self.assertEqual(summarize_status({"render": {"status": "passed"}, "runtime_dependency_inventory": incomplete}), "incomplete")

    def test_independent_cooks_reject_reused_output_but_allow_equal_bytes(self):
        lite_archive, ref_archive = self.root / "lite.bin", self.root / "reference.bin"
        lite_archive.write_bytes(b"synthetic fixture only")
        ref_archive.write_bytes(lite_archive.read_bytes())
        lite = {"status": "passed", "execution_id": "lite-invocation", "compiler": {"path": "/lite-cooker"}, "cook_log": {"path": "/lite.log"}}
        reference = {"status": "passed", "execution_id": "ref-invocation", "compiler": {"path": "/engine-cooker"}, "cook_log": {"path": "/ref.log"}}
        self.assertEqual(inspect_independent_cooks(lite, reference, lite_archive, ref_archive)["status"], "passed")
        self.assertEqual(inspect_independent_cooks(lite, reference, lite_archive, lite_archive)["status"], "failed")
        reference["execution_id"] = lite["execution_id"]
        self.assertEqual(inspect_independent_cooks(lite, reference, lite_archive, ref_archive)["status"], "failed")

    def test_cook_manifest_rejects_filtered_partial_or_failed_jobs(self):
        # Synthetic files exercise the validator only, never runtime provenance.
        compiler, source, build_log, cook_log, archive, manifest, provenance = (self.root / name for name in
            ("fixture-compiler", "fixture.cpp", "fixture-build.log", "fixture-cook.log", "fixture.bin", "fixture.manifest.json", "provenance.json"))
        for path in (compiler, build_log, cook_log, archive):
            path.write_bytes(b"synthetic gate fixture only")
        source.write_text("void Fixture() { SetupCompileEnvironment(); CompileShader(); }")
        pins = {"engine_commit": "a" * 40, "rive_unreal_commit": "b" * 40, "rive_runtime_commit": "c" * 40}
        def evidence(path):
            return {"path": str(path), "sha256": sha256(path)}
        metadata = {"kind": "lite_helper", "status": "passed", "source_pins": {"pins": pins},
                    "compiler": evidence(compiler), "build_logs": [evidence(build_log)], "source_inputs": [evidence(source)],
                    "cook_execution": {"execution_id": "synthetic-fixture-only", "executed": True, "archive_absent_before_invocation": True,
                                       "started_utc": "fixture", "finished_utc": "fixture", "command": [str(compiler), f"-Output={archive}"],
                                       "exit_code": 0, "log": evidence(cook_log), "output": evidence(archive)}}
        domain = {"complete": True, "type_filter": "", "list_only": False, "with_engine": False, "with_editor": True,
                  "shader_platform": "VULKAN_SM5_LINUX", "compiled_permutations": 1,
                  "jobs": [{"type": "FRiveFixture", "source": "/Plugin/Rive/fixture.usf", "permutation": 0, "compiled": True}]}
        def inspect():
            manifest.write_text(json.dumps(domain))
            metadata["archive_manifest"] = evidence(manifest)
            provenance.write_text(json.dumps(metadata))
            return inspect_cook_provenance(provenance, archive, "lite_helper", pins)
        self.assertEqual(inspect()["status"], "passed")
        domain["type_filter"] = "FRiveFixture"
        self.assertEqual(inspect()["status"], "failed")
        domain["type_filter"] = ""
        domain["jobs"][0]["compiled"] = False
        self.assertEqual(inspect()["status"], "failed")
        domain["jobs"][0]["compiled"] = True
        domain["compiled_permutations"] = 2
        self.assertEqual(inspect()["status"], "failed")
        domain.clear()
        self.assertEqual(inspect()["status"], "incomplete")

    def test_formal_coverage_rejects_reduced_scenarios_or_static_subset(self):
        root = SCRIPTS.parent
        cases = json.loads((root / "fixtures/playback/scenarios.json").read_text())["scenarios"]
        static = [root / f"fixtures/{name}.riv" for name in ("fix_rectangle", "blend_test", "clip_tests", "bankcard", "circle_clips")]
        self.assertEqual(coverage_evidence(cases, static, "independent-60-v1", root)["status"], "passed")
        self.assertEqual(coverage_evidence(cases[:-1], static, "independent-60-v1", root)["status"], "incomplete")
        self.assertEqual(coverage_evidence(cases, static[:1], "independent-60-v1", root)["status"], "incomplete")

    def test_playback_requires_real_timeline_driver_and_input_evidence(self):
        scenario = {"mode": "state_machine", "artboard": "board", "state_machine": "machine", "fixed_delta": 0.25,
                    "target_time": 0.5, "events": [{"time": 0.25, "type": "bool", "name": "enabled", "value": True}]}
        metadata = {"schema_version": 1, "status": "completed", "mode": "state_machine", "artboard": "board",
                    "state_machine": "machine", "artboard_index": 0, "selected_index": 0,
                    "fixed_delta": 0.25, "target_time": 0.5, "advanced_time": 0.5,
                    "advance_count": 2, "initialization_advance_count": 1, "event_settle_advance_count": 1,
                    "events_applied": [dict(scenario["events"][0], tick=1)],
                    "final_inputs": [{"name": "enabled", "type": "bool", "value": True}],
                    "state_changes": [], "current_animations": [], "api_calls": {"state_machine_advance_and_apply": 4, "bool_set": 1}}
        path = self.root / "playback.json"
        path.write_text(json.dumps(metadata))
        self.assertEqual(playback_evidence(path, scenario)["status"], "passed")
        metadata["api_calls"]["state_machine_advance_and_apply"] = 0
        path.write_text(json.dumps(metadata))
        self.assertEqual(playback_evidence(path, scenario)["status"], "incomplete")
        metadata["api_calls"]["state_machine_advance_and_apply"] = 4
        metadata["events_applied"][0]["value"] = False
        path.write_text(json.dumps(metadata))
        self.assertEqual(playback_evidence(path, scenario)["status"], "failed")
        validate_scenario({"playback": scenario, "sample_times": [0, 0.5]})
        with self.assertRaises(ValueError):
            validate_scenario({"playback": scenario, "sample_times": [0, 0.3]})

    def test_input_effect_control_rejects_time_only_animation_change(self):
        event, control = self.root / "event.png", self.root / "no-events.png"
        png(event, [(10, 20, 30, 255), (40, 50, 60, 255)])
        png(control, [(10, 20, 30, 255), (40, 50, 61, 255)])
        unchanged_state = {"state_changes": [{"state_index": 1}], "current_animations": [{"name": "auto", "time": 0.5}]}
        self.assertEqual(input_effect_evidence(event, control, unchanged_state, unchanged_state)["status"], "failed")
        changed_state = {"state_changes": [{"state_index": 2}], "current_animations": [{"name": "triggered", "time": 0.5}]}
        self.assertEqual(input_effect_evidence(event, control, changed_state, unchanged_state)["status"], "passed")
        self.assertEqual(input_effect_evidence(event, event, changed_state, unchanged_state)["status"], "failed")

    def test_static_capture_requires_real_legacy_and_explicit_empty_policy(self):
        path = self.root / "playback.json"
        metadata = {"schema_version": 1, "status": "completed", "mode": "legacy", "artboard": "Default",
                    "target_time": 0, "api_calls": {"artboard_advance": 1, "animation_advance": 0, "state_machine_advance_and_apply": 0}}
        path.write_text(json.dumps(metadata))
        self.assertEqual(legacy_playback_evidence(path)["status"], "passed")
        metadata["api_calls"]["animation_advance"] = 1
        path.write_text(json.dumps(metadata))
        self.assertEqual(legacy_playback_evidence(path)["status"], "failed")
        image = self.root / "static.png"
        self.assertEqual(pixel_content_evidence(image, False)["status"], "incomplete")
        png(image, [(0, 0, 0, 0), (0, 0, 0, 0)])
        self.assertEqual(pixel_content_evidence(image, False)["status"], "failed")
        self.assertEqual(pixel_content_evidence(image, True)["status"], "passed")
        png(image, [(0, 0, 0, 0), (12, 34, 56, 255)])
        self.assertEqual(pixel_content_evidence(image, False)["status"], "passed")

    def test_reference_metadata_and_hash_binding(self):
        a, b, evidence = (self.root / name for name in ("a.png", "b.png", "reference.json"))
        png(a, [(1, 2, 3, 255), (4, 5, 6, 255)])
        png(b, [(1, 2, 3, 255), (4, 5, 6, 255)])
        metadata = {"engine_commit": "abc", "rive_unreal_commit": "def", "rive_runtime_commit": "123",
                    "fixture_sha256": "456", "shader_archive_sha256": "same-archive", "width": 2, "height": 1, "render_path": "UE RHI/RDG",
                    "color_space": "encoded sRGB", "alpha_mode": "straight", "sample_count": 1,
                    "frame_index": 0, "time_seconds": 0, "clear_color": [0, 0, 0, 0], "png_sha256": sha256(a)}
        evidence.write_text(json.dumps({"reference": dict(metadata, host_kind="UE editor"), "prototype": metadata}))
        self.assertEqual(reference_provenance(evidence, a, b)["status"], "passed")
        mismatch = dict(metadata, fixture_sha256="different")
        evidence.write_text(json.dumps({"reference": dict(metadata, host_kind="UE editor"), "prototype": mismatch}))
        self.assertEqual(reference_provenance(evidence, a, b)["status"], "failed")
        mismatch = dict(metadata, shader_archive_sha256="different-archive")
        evidence.write_text(json.dumps({"reference": dict(metadata, host_kind="UE editor"), "prototype": mismatch}))
        self.assertEqual(reference_provenance(evidence, a, b)["status"], "failed")
        evidence.write_text("{}")
        self.assertEqual(reference_provenance(evidence, a, b)["status"], "incomplete")

    def test_clear_probe_cannot_pass_rive_draw_gate(self):
        actual = self.root / "output with spaces.png"
        png(actual, [(1, 2, 3, 255), (4, 5, 6, 255)])
        dimensions = {"width": 2, "height": 1}
        prefix = f'LogRiveLiteHost: Display: RIVE_LITE_CAPTURE path="{actual.as_posix()}" width=2 height=1 '
        probe = prefix + "probe_only=1 render_path=UE_RHI_RDG RiveDrawCompleted=1"
        self.assertEqual(rive_draw_evidence(probe, actual, dimensions)["status"], "failed")
        valid = prefix + "probe_only=0 render_path=UE_RHI_RDG RiveDrawCompleted=1"
        self.assertEqual(rive_draw_evidence(valid, actual, dimensions)["status"], "passed")
        self.assertEqual(rive_draw_evidence(prefix + "probe_only=0", actual, dimensions)["status"], "incomplete")
        self.assertEqual(rive_draw_evidence(valid.replace("UE_RHI_RDG", "NATIVE_VULKAN"), actual, dimensions)["status"], "failed")
        self.assertEqual(rive_draw_evidence(valid.replace("width=2", "width=99"), actual, dimensions)["status"], "failed")
        self.assertEqual(rive_draw_evidence(valid, self.root / "other.png", dimensions)["status"], "failed")
        self.assertEqual(rive_draw_evidence(valid, actual, None)["status"], "incomplete")
        self.assertEqual(rive_draw_evidence("RiveDrawCompleted=1", actual, dimensions)["status"], "incomplete")

    def test_reference_requires_engine_render_target_completion(self):
        actual = self.root / "reference image.png"
        image = {"width": 512, "height": 512}
        marker = (f'RIVE_UE_REFERENCE_CAPTURE path="{actual.as_posix()}" width=512 height=512 '
                  'render_path=UE_RHI_RDG engine_linked=1 renderer_linked=1 engine_frender_target=1 '
                  'utexture_target=0 editor_viewport=0 umg_composite=0')
        self.assertEqual(reference_capture_evidence(marker, actual, image, 512, 512, False)["status"], "passed")
        self.assertEqual(reference_capture_evidence(marker, actual, image, 512, 512, True)["status"], "failed")
        self.assertEqual(reference_capture_evidence(marker.replace("engine_frender_target=1", "engine_frender_target=0"), actual, image, 512, 512, False)["status"], "failed")
        self.assertEqual(reference_capture_evidence(marker.replace("RIVE_UE_REFERENCE_CAPTURE", "RIVE_LITE_CAPTURE"), actual, image, 512, 512, False)["status"], "incomplete")

    @unittest.skipUnless(hasattr(os, "sched_getaffinity"), "Linux affinity API")
    def test_cpu_profile_records_affinity_and_mesa_threads(self):
        env = {}
        with mock.patch("measure_ue_lite.os.sched_getaffinity", side_effect=[{2, 4, 6}, {2, 4}]), mock.patch("measure_ue_lite.os.sched_setaffinity") as setter:
            result = apply_cpu_profile(2, 2, env)
        setter.assert_called_once_with(0, {2, 4})
        self.assertEqual(result["affinity_effective"], [2, 4])
        self.assertEqual(env["LP_NUM_THREADS"], "2")

    def test_source_pins_fallback_to_consistent_manifests(self):
        source_state = self.root / "artifacts/source-state.json"
        upstream = self.root / "Source/RiveLiteRenderer/upstream-manifest.json"
        native = self.root / "Source/RiveLiteRenderer/native-build-result.json"
        source_state.parent.mkdir(parents=True)
        upstream.parent.mkdir(parents=True)
        source_state.write_text(json.dumps({"engine_commit": "a" * 40, "rive_unreal_commit": "b" * 40, "rive_runtime_gitlink": "c" * 40}))
        upstream.write_text(json.dumps({"source_commit": "b" * 40, "runtime_commit": "c" * 40}))
        native.write_text(json.dumps({"runtime_commit": "c" * 40, "compiled": True}))
        report = source_pins(self.root)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["pins"]["rive_runtime_commit"], "c" * 40)
        self.assertTrue(all(item["origin"] == "recorded provenance manifest" for item in report["evidence"]))
        native.write_text(json.dumps({"runtime_commit": "d" * 40, "compiled": True}))
        self.assertEqual(source_pins(self.root)["status"], "failed")

    @unittest.skipUnless(sys.platform.startswith("linux") and Path("/usr/bin/time").exists(), "Linux invocation metrics")
    def test_measured_fixture_process_and_stale_png(self):
        # This synthetic process tests the runner only. It is not rendering evidence.
        fixture = self.root / "fixture.png"
        output = self.root / "output with spaces.png"
        png(fixture, [(1, 2, 3, 255), (4, 5, 6, 255)])
        script = "import pathlib,sys,time;time.sleep(0.02);pathlib.Path(sys.argv[2]).write_bytes(pathlib.Path(sys.argv[1]).read_bytes())"
        record = run_once(Path(sys.executable), ["-c", script, str(fixture), "{output}"], output,
                          0, self.root, dict(os.environ, LC_ALL="C"), 5, self.root)
        self.assertEqual(record["status"], "passed")
        self.assertGreater(record["peak_rss_kib"], 0)
        self.assertGreater(record["first_png_wall_seconds"], 0.02)
        self.assertEqual(record["runtime_device"]["status"], "incomplete")
        self.assertEqual(record["rive_draw"]["status"], "incomplete")
        stale = run_once(Path(sys.executable), [], output, 1, self.root, dict(os.environ), 5, self.root)
        self.assertEqual(stale["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
