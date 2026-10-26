import hashlib, io, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, urllib.request, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
source=root/'vendor/rive-unreal/submodules/rive-runtime'
pin='47d1cd54ccefd468db7cb26ecc4699ae1723dd85'
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==pin
stage=root/'build/windows/rive-runtime'
if not stage.exists():
    stage.mkdir(parents=True)
    data=subprocess.check_output(['git','-C',str(source),'archive','HEAD'])
    with tarfile.open(fileobj=io.BytesIO(data)) as t: t.extractall(stage,filter='data')
    (stage/'.rive-prototype-pin').write_text(pin)
elif not (stage/'.rive-prototype-pin').is_file() or (stage/'.rive-prototype-pin').read_text()!=pin:
    raise RuntimeError('Unrecognized Windows staging tree; preserve and inspect it')
shader=stage/'renderer/src/shaders'
out=stage/'out/windows/release'
generated=out/'include/generated/shaders'
generated.mkdir(parents=True,exist_ok=True)
inputs=sorted([str(p) for p in shader.iterdir() if p.suffix in ('.glsl','.vert','.frag')])
with tempfile.TemporaryDirectory(prefix='shader-stage-',dir=out) as temp:
    subprocess.run([sys.executable,str(shader/'minify.py'),'-p',str(root/'vendor/rive-native-deps/dabeaz_ply_3.11'),'--human-readable','--msvc','-o',temp,*inputs],cwd=shader,check=True)
    for src in pathlib.Path(temp).iterdir():
        dest=generated/src.name
        if not dest.exists() or dest.read_bytes()!=src.read_bytes():
            shutil.copy2(src,dest)
p=stage/'renderer/premake5_pls_renderer.lua'
s=p.read_text(encoding='utf-8')
s=s.replace('execute_and_check(makecommand)','assert(_OPTIONS[\'for_unreal\'], "Isolated shader preparation only supports UE RHI")')
p.write_text(s,encoding='utf-8')
env=os.environ.copy(); env['DEPENDENCIES']=str(root/'vendor/rive-native-deps'); env['PREMAKE_PATH']=str(stage/'build')
premake_dir=root/'dependencies/premake-windows-5.0.0-beta7'
premake_dir.mkdir(parents=True,exist_ok=True)
archive=premake_dir/'premake.zip'
digest='8baec7b265fd43050f006ef47000457fa93b6fafbb1ead7e333e862a467c2e95'
if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:
    urllib.request.urlretrieve('https://github.com/premake/premake-core/releases/download/v5.0.0-beta7/premake-5.0.0-beta7-windows.zip',archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
premake=premake_dir/'premake5.exe'
with zipfile.ZipFile(archive) as z: premake.write_bytes(z.read('premake5.exe'))
subprocess.run([str(premake),'vs2022','--config=release','--out=../out/windows/release','--with_rive_text','--with_rive_layout','--with_rive_audio=external','--for_unreal','--no_gl','--cpp20','--with_rive_canvas','--track_rive_shader_id','--no-lto','--raw_shaders','--toolset=msc','--toolsversion=14.50.35717'],cwd=stage/'renderer',env=env,check=True)
print('STAGED',stage)

# Only the C++ embedding uses --msvc; UE shader text must remain identical.
for p in generated.iterdir():
    if 'minified' in p.name:
        q=root/'Shaders/Private/Rive/Generated'/(p.stem+'.ush' if p.suffix=='.glsl' else p.name+'.ush')
        assert q.read_bytes()==p.read_bytes(), str(p)
vswhere=pathlib.Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
msbuild=subprocess.check_output([str(vswhere),'-latest','-prerelease','-products','*','-find','MSBuild/Current/Bin/MSBuild.exe'],text=True).strip().splitlines()[0]
tool=root/'dependencies/windows-msvc/AutoSDK/HostWin64/Win64/VS2026/14.50.35717'
env['CL']='/utf-8 /MP8'
targets='rive;rive_decoders;rive_harfbuzz;rive_pls_renderer;rive_sheenbidi;miniaudio;rive_yoga;libpng;libjpeg;libwebp;zlib'
subprocess.run([msbuild,str(out/'rive.sln'),'-t:'+targets,'-m:4','-p:Configuration=default','-p:Platform=x64','-p:PlatformToolset=v145','-p:PreferredToolArchitecture=x64','-p:VCToolsInstallDir='+str(tool)+os.sep,'-p:VCToolsVersion=14.50.35717','-p:WindowsTargetPlatformVersion=10.0.26100.0'],env=env,check=True)
