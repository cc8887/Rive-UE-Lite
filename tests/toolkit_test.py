"""CLI/process/packaging contracts. Real UE acceptance is a separate suite."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from rive_tool import Coordinator, ToolError, input_path, path_in_workspace, workspace
from package_toolkit import make_archive
from compare_png import sha256


class ToolkitContracts(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux build selection')
    def test_full_bundle_build_is_explicit(self):
        base = ['bash', str(ROOT/'scripts/build_ui.sh')]
        default = subprocess.check_output([*base, '--plan'], text=True)
        self.assertIn('target=RiveRhiLite', default)
        for name in ['RiveUmgHost', 'RiveVerseWorker', 'RiveUmgBlueprintWorker']:
            self.assertNotIn('target='+name, default)
        full = subprocess.check_output([*base, '--all-tools', '--plan'], text=True)
        for name in ['RiveRhiLite', 'RiveUmgHost', 'RiveVerseWorker', 'RiveUmgBlueprintWorker']:
            self.assertIn('target='+name, full)

    def test_workspace_and_output_boundaries(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            root = Path(temp)
            toolkit = root/'bundle'
            toolkit.mkdir()
            for path in [toolkit, toolkit/'components/widget/new', root]:
                with self.assertRaises(ToolError): workspace(path, toolkit)
            ws = workspace(root/'project', toolkit)
            for path in ['../escape.png', '.rive-tool/control.json']:
                with self.assertRaises(ToolError): path_in_workspace(path, ws)
            self.assertEqual(path_in_workspace('renders/a.png', ws), ws/'renders/a.png')
            external = root/'input.riv'
            external.write_bytes(b'input')
            self.assertEqual(input_path(str(external), ws), external)

    def test_busy_stop_and_unknown_operation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            ctrl = Coordinator(Path(temp), Path(temp))
            ctrl.lock.acquire()
            try:
                with self.assertRaises(ToolError) as error: ctrl.dispatch('stop', {})
                self.assertEqual(error.exception.exit_code, 75)
                self.assertTrue(ctrl.dispatch('status', {})['running'])
            finally: ctrl.lock.release()
            with self.assertRaises(ToolError): ctrl.dispatch('arbitrary-shell-command', {})

    def test_cli_bad_argument_is_json(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/rive_tool.py'), '--bad-option'], capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(data['error']['code'], 'invalid_arguments')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux local coordinator')
    def test_real_coordinator_lifecycle_without_starting_ue(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            root = Path(temp)
            toolkit, ws = root/'bundle', root/'workspace with spaces'
            toolkit.mkdir()
            base = [sys.executable, '-B', str(ROOT/'scripts/rive_tool.py'), '--toolkit', str(toolkit), '--workspace', str(ws)]
            def call(*args):
                proc = subprocess.run([*base, *args], capture_output=True, text=True, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
                return json.loads(proc.stdout)
            try:
                first = call('start')
                self.assertEqual(first['native_workers_started'], 0)
                again = call('start')
                self.assertTrue(again['reused'])
                self.assertEqual(first['pid'], again['pid'])
                self.assertIsNone(call('status')['active_job'])
                self.assertNotIn('token', call('status'))
            finally:
                call('stop')
            self.assertFalse(call('status')['running'])
            self.assertFalse(call('stop')['running'])

    def test_tar_deduplicates_and_keeps_executable_permissions(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            root = Path(temp)/'toolkit'
            root.mkdir()
            for name in ['a.txt', 'b.txt']: (root/name).write_bytes(b'same bytes')
            (root/'rive-tool').write_text('#!/bin/bash\nexit 0\n')
            (root/'toolkit-manifest.json').write_text('{}')
            for component in ['rive', 'umg', 'verse', 'widget']: (root/'components'/component/'Engine/Shaders').mkdir(parents=True)
            entries = [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in root.iterdir() if p.is_file() and p.name != 'toolkit-manifest.json']
            result = make_archive(root, {'files': entries})
            self.assertEqual(result['hardlink_entries'], 1)
            with tarfile.open(result['path']) as archive:
                self.assertTrue(archive.getmember('toolkit/b.txt').islnk())
                self.assertTrue(archive.getmember('toolkit/rive-tool').mode & 0o111)
                target = Path(temp)/'extracted'
                archive.extractall(target, filter='data')
            self.assertEqual((target/'toolkit/a.txt').read_bytes(), (target/'toolkit/b.txt').read_bytes())
            if sys.platform.startswith('linux'):
                self.assertTrue(os.path.samefile(target/'toolkit/a.txt', target/'toolkit/b.txt'))


if __name__ == '__main__': unittest.main()
