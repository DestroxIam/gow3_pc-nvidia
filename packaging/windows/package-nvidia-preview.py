#!/usr/bin/env python3
"""Build a clean portable preview from allowlisted runtime files, never a player's tree."""
from pathlib import Path
import argparse,zipfile,shutil,configparser,json,hashlib
root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--base-zip',type=Path,required=True)
parser.add_argument('--runtime-root',type=Path,required=True)
parser.add_argument('--native-runtime',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
stage=output/'gow3-windows-nvidia';stage.mkdir(exist_ok=True)
forbidden_names={'eboot.bin','sce_module','sce_sys','savedata','savedata_backups','settings.json','nvngx_dlssnr.dll'}
forbidden_suffixes={'.iso','.pkg','.prx','.sprx','.raw','.spv','.log','.pdb'}
def allowed(relative):
    path=Path(relative);parts={p.lower() for p in path.parts}
    return not (parts&forbidden_names or path.suffix.lower() in forbidden_suffixes or '__pycache__' in parts or '.git' in parts)
with zipfile.ZipFile(args.base_zip) as archive:
    for item in archive.infolist():
        parts=Path(item.filename).parts
        if len(parts)<2 or item.is_dir():continue
        relative=Path(*parts[1:])
        # Only the upstream normal runtime is reused. New launcher and scripts come from source.
        if relative.parts[0]!='bin' or not allowed(relative):continue
        destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(archive.read(item))
frozen=root/'out/nvidia-launcher-dist/God of War III'
for path in frozen.rglob('*'):
    if path.is_file():
        relative=path.relative_to(frozen)
        if not allowed(relative):raise RuntimeError('Unexpected frozen file: '+str(relative))
        destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
for folder in ('scripts','patches','launcher','Game'):
    for path in (root/folder).rglob('*'):
        if not path.is_file() or not allowed(path.relative_to(root)):continue
        relative=path.relative_to(root)
        if folder=='launcher' and path.suffix not in {'.py','.png','.json','.ico','.ttf','.txt'}:continue
        destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
for name in ('run.py','LICENSE','README.md','README.pt-BR.md','CHANGELOG.md'):shutil.copy2(root/name,stage/name)
shutil.copytree(root/'docs',stage/'docs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
def runtime_tree(source,destination):
    destination.mkdir(exist_ok=True)
    for path in source.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(source)
        if not allowed(relative) or relative.name in {'source-manifest.json','renderer-build.json','OptiScaler.ini'}:continue
        if path.suffix.lower() not in {'.dll','.exe','.txt','.md'}:continue
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
native=args.native_runtime.resolve();normal=args.runtime_root.resolve()
runtime_tree(native,stage/'bin-native-dlss')
runtime_tree(native,stage/'bin-native-effects')
runtime_tree(normal/'bin-dlss5',stage/'bin-dlss5')
for name in ('winmm.dll',):shutil.copy2(normal/'bin-dlss5'/name,stage/'bin-native-effects'/name)
for path in (normal/'bin-dlss5/OptiScaler').rglob('*'):
    if path.is_file() and allowed(path.relative_to(normal/'bin-dlss5')):
        rel=path.relative_to(normal/'bin-dlss5');target=stage/'bin-native-effects'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
for folder in ('bin-dlss5','bin-native-effects'):
    config=configparser.ConfigParser(interpolation=None,strict=False);config.optionxform=str
    config.read(normal/'bin-dlss5/OptiScaler.ini',encoding='utf-8-sig')
    for section,values in {'DlssNr':{'Enabled':'false','TargetProcessName':'auto'},
                           'Log':{'LogFileName':'NVIDIA.log','LogToFile':'true','LogToConsole':'false'},
                           'ProcessFilter':{'TargetProcessName':'auto'},'FrameGen':{'Enabled':'false'}}.items():
        if not config.has_section(section):config.add_section(section)
        config[section].update(values)
    with (stage/folder/'OptiScaler.ini').open('w',encoding='utf-8') as file:config.write(file)
    # Every mod keeps its upstream GPL and vendor dependency notices.
    license_path=normal/'bin-dlss5/OptiScaler/streamline/Streamline-LICENSE.txt'
    if license_path.exists():shutil.copy2(license_path,stage/folder/'OptiScaler/Streamline-LICENSE.txt')
    shutil.copy2(root/'patches/optiscaler/LICENSE',stage/folder/'OptiScaler/LICENSE-GPL3.txt')
for folder in ('bin-native-dlss','bin-native-effects'):
    info={'source_repository':'https://github.com/DestroxIam/gow3_pc-nvidia','upstream_commit':'b907d8a9f2324ba5f514fbfe7de803e027c6ca26',
          'native_dlss':True,'probe_sha256':hashlib.sha256((stage/folder/'gow3-probe.exe').read_bytes()).hexdigest()}
    (stage/folder/'renderer-build.json').write_text(json.dumps(info,indent=2))
(stage/'gow3.ini').write_text('''# Clean preview defaults, not a player configuration
upscaler=off
preset=3
output_res=3840x2160
render_resolution=native
engine_fps=120
fps_limit=120
display_mode=windowed
vsync=1
object_motion=1
jitter=1
show_fps=1
async_shaders=1
deferred_readback=1
stale_readback=1
frames_queued=1
fsr1=1
rcas=1
cheat_health=0
cheat_magic=0
cheat_double_jumps=0
''',encoding='utf-8')
(stage/'Configure God of War III.cmd').write_text('@echo off\ncd /d "%~dp0"\nstart "" "%~dp0God of War III.exe"\n')
(stage/'Play God of War III.cmd').write_text('@echo off\ncd /d "%~dp0"\nstart "" "%~dp0God of War III.exe" --play\n')
report=[]
for path in stage.rglob('*'):
    if not path.is_file():continue
    relative=path.relative_to(stage)
    if not allowed(relative):raise RuntimeError('Forbidden publication content: '+str(relative))
    if relative.parts[0].lower() in {'user','out','cache','savedata'}:raise RuntimeError('Player state in package')
    if relative.parts[0]=='Game' and relative.name not in {'README.md','.gitkeep'}:raise RuntimeError('Game content in package')
    if path.suffix.lower() in {'.py','.md','.txt','.json','.ini','.cmd','.xml'}:
        data=path.read_text(encoding='utf-8',errors='ignore')
        if 'C:\\Users\\Destr' in data or 'C:/Users/Destr' in data or 'lkv1n.designer@' in data:raise RuntimeError('Private path/contact in '+str(relative))
    report.append({'path':str(relative).replace('\\','/'),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(output/'PACKAGE-AUDIT.json').write_text(json.dumps({'no_game_files':True,'nr_model_excluded':True,'no_personal_state':True,'files':report},indent=2))
archive=output/'gow3-windows-nvidia-preview-1.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
    for entry in report:zipped.write(stage/entry['path'],'gow3-windows-nvidia/'+entry['path'])
checksums=output/'SHA256SUMS.txt';checksums.write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(json.dumps({'archive':str(archive),'size':archive.stat().st_size,'files':len(report),'no_game_files':True,'nr_model_excluded':True}))
