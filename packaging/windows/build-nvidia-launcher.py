#!/usr/bin/env python3
"""Freeze only after mandatory dependency, native import and license checks pass."""
import argparse
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
HIDDEN=('argparse','base64','collections','configparser','hashlib','json','math','re','shutil','struct','tempfile',
 'dataclasses','iced_x86','iced_x86._iced_x86_py','PIL.Image','PIL.ImageFont','PIL._imaging','PIL._imagingft',
 'xml.etree.ElementTree','urllib.request','ctypes.wintypes','importlib.util','importlib.metadata','types',
 'graphics_options','isa_rewrite','patches','prepare','gow3_launcher_dlss','gow3_lang','gow3_dlss_control','gow3_redesign','game_layout','button_icons','gow3_vulkan','gow3_assets')

def preflight(hidden=HIDDEN):
    missing=[]
    for name in hidden:
        try:
            if importlib.util.find_spec(name) is None:missing.append(name)
        except (ImportError,ValueError,AttributeError):missing.append(name)
    if missing:raise RuntimeError('Required freeze imports missing: '+', '.join(missing))
    for name in ('dataclasses','iced_x86._iced_x86_py','PIL._imaging','PIL._imagingft'):
        try:importlib.import_module(name)
        except (ImportError,OSError) as error:raise RuntimeError('Required native/standard import failed: '+name) from error
    versions={name:importlib.metadata.version(name) for name in ('iced-x86','Pillow','PyInstaller')}
    if versions['iced-x86']!='1.21.0':raise RuntimeError('Freeze requires project-supplied iced-x86==1.21.0')
    licenses={}
    for name in versions:
        dist=importlib.metadata.distribution(name)
        files=[dist.locate_file(p) for p in dist.files or [] if p.name.lower().startswith(('license','copying'))]
        if not files or any(not p.is_file() or not p.stat().st_size for p in files):raise RuntimeError('Required distribution license missing: '+name)
        licenses[name]=files
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():raise RuntimeError('Python distribution LICENSE.txt missing')
    licenses['Python']=[python_license]
    return versions,licenses

def checked_pyinstaller(command,env):
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    output=result.stdout+'\n'+result.stderr
    fatal=re.search(r'(?im)^.*\b(?:ERROR|FATAL):[^\r\n]*',output)
    if result.returncode or fatal:raise RuntimeError('PyInstaller failed (exit '+str(result.returncode)+'): '+(fatal.group(0).strip()[:400] if fatal else output[-1000:]))
    return output

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency-dir',type=Path,help='Parent-supplied local target; never installs packages')
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--verify-only',action='store_true',help='Verify an existing frozen output without rebuilding')
    args=parser.parse_args()
    dependency=args.dependency_dir or ROOT.parent/'nvidia-freeze-deps'
    if args.dependency_dir and not dependency.is_dir():raise RuntimeError('Supplied dependency directory missing')
    paths=[ROOT/'scripts',ROOT/'launcher']
    if dependency.is_dir():paths.insert(0,dependency.resolve())
    for path in reversed(paths):sys.path.insert(0,str(path))
    versions,licenses=preflight()
    if args.preflight_only:
        print(json.dumps({'dependencies':versions,'licenses_checked':sorted(licenses)}));return
    env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join([*(str(p) for p in paths),env.get('PYTHONPATH','')])
    frozen=ROOT/'out/nvidia-launcher-dist/God of War III';marker=frozen/'freeze-validation.json'
    marker.unlink(missing_ok=True)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--log-level','WARN','--windowed',
     '--name','God of War III','--icon',str(ROOT/'launcher/gow3.ico'),
     '--distpath',str(ROOT/'out/nvidia-launcher-dist'),'--workpath',str(ROOT/'out/nvidia-launcher-work'),
     '--specpath',str(ROOT/'out/nvidia-launcher-work')]
    for p in paths:command+=['--paths',str(p)]
    for name in HIDDEN:command+=['--hidden-import',name]
    for name in ('Pillow','iced-x86','PyInstaller'):command+=['--copy-metadata',name]
    command+=[str(ROOT/'launcher/gow3_launcher_win.py')]
    if not args.verify_only:checked_pyinstaller(command,env)
    notices=frozen/'THIRD-PARTY-LICENSES';notices.mkdir(exist_ok=True)
    for name,files in licenses.items():
        for i,file in enumerate(files):shutil.copy2(file,notices/(name+'-'+str(i)+'-'+file.name))
    report=ROOT/'out/nvidia-launcher-work/frozen-role-report.json';report.unlink(missing_ok=True)
    subprocess.run([str(frozen/'God of War III.exe'),'--script',str(Path(__file__).with_name('frozen_probe.py')),
     '--source',str(ROOT),'--report',str(report)],cwd=frozen,check=True,timeout=45)
    result=json.loads(report.read_text(encoding='utf-8'))
    if result.get('passed') is not True:raise RuntimeError('Frozen role/import/source verification failed')
    import hashlib
    result['root_exe_sha256']=hashlib.sha256((frozen/'God of War III.exe').read_bytes()).hexdigest()
    result['licenses']=[p.name for p in sorted(notices.iterdir()) if p.is_file()]
    marker.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'frozen_verified':True,'dependencies':versions,'source_checks':result['source_checks'],
     'licenses':result['licenses'],'root_exe_sha256':result['root_exe_sha256']}))

if __name__=='__main__':main()
