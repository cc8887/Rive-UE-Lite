import hashlib, json, pathlib, urllib.request, zipfile
root = pathlib.Path(__file__).resolve().parents[1]
selected = json.loads((root / 'scripts/windows-msvc-manifest.json').read_text(encoding='utf-8'))
base = root / 'dependencies/windows-msvc'
base.mkdir(parents=True, exist_ok=True)
(base / 'payloads.json').write_text(json.dumps(selected, indent=2))
for package in selected:
    for p in package['payloads']:
        dest = base / p['fileName']
        if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != p['sha256']:
            urllib.request.urlretrieve(p['url'], dest)
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == p['sha256']
        with zipfile.ZipFile(dest) as z:
            for info in z.infolist():
                parts = pathlib.PurePosixPath(info.filename).parts
                if parts[:4] == ('Contents','VC','Tools','MSVC'):
                    target = base / 'AutoSDK/HostWin64/Win64/VS2026' / pathlib.Path(*parts[4:])
                elif parts[:3] == ('Contents','VC','Redist'):
                    target = base / 'Redist' / pathlib.Path(*parts[3:])
                else:
                    continue
                assert target.resolve().is_relative_to(base.resolve())
                if not info.is_dir():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = z.read(info)
                    if not target.exists() or target.read_bytes() != data:
                        target.write_bytes(data)
        print(package['id'], package['version'], 'verified and extracted', flush=True)
