"""Mac staging guards; these tests do not simulate Metal or claim Mac builds."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from check_macos_archives import LIBRARIES, validate
from package_macos import validate_shader


class MacStagingGuards(unittest.TestCase):
    def test_archives_reject_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/LIBRARIES[0]).write_text('version https://git-lfs.github.com/spec/v1\n')
            with self.assertRaisesRegex(RuntimeError, 'LFS pointer'):
                validate(root, 'arm64')

    def test_archives_reject_other_architecture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in LIBRARIES: (root/name).write_bytes(b'a'*512)
            with patch('check_macos_archives.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'x86_64', '')):
                with self.assertRaisesRegex(RuntimeError, 'architecture'):
                    validate(root, 'arm64')

    def test_all_native_libraries_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in LIBRARIES[:-1]: (root/name).write_bytes(b'a'*512)
            with patch('check_macos_archives.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'arm64', '')):
                with self.assertRaisesRegex(RuntimeError, 'Missing archive'):
                    validate(root, 'arm64')

    def test_shader_rejects_linux_editor_and_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder)/'global.bin'
            archive.write_bytes(b'archive')
            manifest = {'complete': True, 'kind': 'ue_engine_canonical', 'target_platform': 'Mac',
                        'shader_platform': 'METAL_SM5', 'target_has_editor_only_data': False, 'archive_bytes': 7,
                        'type_filter': '', 'loads_lite_archive': False, 'failed_jobs': 0, 'submitted_jobs': 10, 'succeeded_jobs': 10}
            sidecar = Path(str(archive)+'.manifest.json')
            sidecar.write_text(json.dumps(manifest))
            validate_shader(archive)
            for field, value in [('complete', False), ('target_platform', 'Linux'), ('shader_platform', 'VULKAN_SM5_LINUX'),
                                 ('target_has_editor_only_data', True), ('archive_bytes', 6), ('type_filter', 'SomeShader'),
                                 ('loads_lite_archive', True), ('failed_jobs', 1), ('succeeded_jobs', 9)]:
                with self.subTest(field=field):
                    sidecar.write_text(json.dumps({**manifest, field: value}))
                    with self.assertRaises(RuntimeError): validate_shader(archive)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'shell plan checks run under WSL/Linux')
    def test_default_and_explicit_build_plans(self):
        command = ['bash', str(ROOT/'scripts/build_ui.sh')]
        linux = subprocess.check_output(command+['--plan'], text=True)
        mac = subprocess.check_output(command+['--platform=macos', '--plan'], text=True)
        self.assertIn('target=RiveRhiLite', linux)
        self.assertIn('target=RiveRhiLite', mac)
        for text in [linux, mac]:
            self.assertNotIn('target=RiveUmgHost', text)
            self.assertNotIn('target=RiveVerseWorker', text)
            self.assertNotIn('target=RiveUeShaderCooker', text)
        unsupported = subprocess.run(command+['--platform=macos', '--with-umg', '--plan'], capture_output=True)
        self.assertNotEqual(unsupported.returncode, 0)


if __name__ == '__main__': unittest.main()
