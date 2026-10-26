"""Asset handoff must include texture sources and refuse unsafe/partial imports."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from widget_bp import ENGINE_COMMIT, copy_source_asset, export_source_assets, sha256


class WidgetAssetHandoff(unittest.TestCase):
    def test_export_and_import_include_texture_and_bulk_source(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            root = Path(temp); content = root/'source/Content'
            files = {'UI/WBP_Card.uasset': b'blueprint source', 'Textures/T_Icon.uasset': b'texture metadata',
                     'Textures/T_Icon.ubulk': b'texture source pixels'}
            for name, data in files.items():
                path = content/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            output = root/'card.zip'
            export_source_assets(output, content, content/'UI/WBP_Card.uasset', '/Game/UI/WBP_Card',
                {'texture_dependencies':[{'package':'/Game/Textures/T_Icon'},{'package':'/Engine/Shared/T_White'}]})
            with zipfile.ZipFile(output) as archive:
                index = json.loads(archive.read('assets.json'))
                self.assertEqual(index['external_engine_packages'], ['/Engine/Shared/T_White'])
                self.assertEqual({entry['path'] for entry in index['files']}, {'Content/'+name for name in files})
            dest = root/'dest/Content'; created = []
            copy_source_asset(output, dest, dest/'UI/WBP_Card.uasset', '/Game/UI/WBP_Card', created)
            self.assertEqual(len(created), 3)
            for name, data in files.items(): self.assertEqual((dest/name).read_bytes(), data)

    def test_import_preflights_every_file_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as temp:
            root = Path(temp); content = root/'Content'; content.mkdir()
            for name in ['Content/../escape.uasset', 'Content/Textures/T_Existing.uasset']:
                existing = content/'Textures/T_Existing.uasset'
                existing.parent.mkdir(parents=True, exist_ok=True); existing.write_bytes(b'preserve')
                archive = root/'invalid.zip'
                with zipfile.ZipFile(archive, 'w') as output:
                    entries = []
                    for path in ['Content/UI/WBP_Card.uasset', name]:
                        output.writestr(path, b'payload')
                        entries.append({'path':path, 'bytes':7, 'sha256':'unused preflight'})
                    output.writestr('engine-pin.txt', ENGINE_COMMIT)
                    output.writestr('assets.json', json.dumps({'format':1, 'primary_asset':'/Game/UI/WBP_Card','files':entries}))
                created = []
                with self.assertRaises(ValueError):
                    copy_source_asset(archive, content, content/'UI/WBP_Card.uasset', '/Game/UI/WBP_Card', created)
                self.assertEqual(created, [])
                self.assertFalse((content/'UI/WBP_Card.uasset').exists())
                self.assertEqual(existing.read_bytes(), b'preserve')
                self.assertFalse((root/'escape.uasset').exists())


if __name__ == '__main__': unittest.main()
