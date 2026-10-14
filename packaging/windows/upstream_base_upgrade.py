"""Optional receipt-bound upstream Windows base upgrade; excludes player/NVIDIA trees."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from publication_policy import relative_path
from runtime_provenance import read_object, require_hash, sha256

ROOT_FILES={'God of War III.exe','Play God of War III.exe','run.py','LICENSE',
            'README.md','README.pt-BR.md','README-Windows.txt'}
PROTECTED_PARTS={'game','user','savedata','savedata_backups','cache','out','mods','logs',
                 'launcher','optiscaler','bin-dlss5','bin-native-dlss','bin-native-effects'}
PROTECTED_NAMES={'gow3.ini','settings.json','mods.json','mods_presets.json','patches.json',
                 'winmm.dll','gow3_dlss.dll','nvngx_dlss.dll'}
REQUIRED={'God of War III.exe','Play God of War III.exe','run.py','LICENSE',
          '_internal/base_library.zip','bin/gow3-probe.exe','bin/gow3-gpu-capabilities.exe',
          'scripts/isa_rewrite.py','scripts/prepare.py','scripts/patches.py','scripts/graphics_options.py'}


def allowed_base(name):
    path=relative_path(name);parts={p.lower() for p in path.parts};lower=path.name.lower()
    if parts&PROTECTED_PARTS or lower in PROTECTED_NAMES or lower.startswith('nvngx'):
        return False
    if lower.startswith('.env') or path.suffix.lower() in {'.iso','.pkg','.prx','.sprx','.log','.raw','.onnx','.safetensors'}:
        return False
    if len(path.parts)==1:return path.name in ROOT_FILES
    if path.parts[0]=='_internal':return True  # Entire matched frozen Python environment, including native modules.
    if path.parts[0]=='bin':return len(path.parts)==2 and path.suffix.lower() in {'.exe','.dll','.txt'}
    if path.parts[0]=='scripts':return path.suffix.lower()=='.py'
    if path.parts[0]=='patches':return len(path.parts)==2 and path.suffix.lower() in {'.xml','.txt','.md'}
    return False


def inventory(stage):
    stage=Path(stage).resolve();entries=[]
    for file in sorted(stage.rglob('*')):
        if file.is_symlink() or (hasattr(file,'is_junction') and file.is_junction()):
            raise ValueError('Linked path in upstream stage: '+file.name)
        if file.is_file() and allowed_base(file.relative_to(stage).as_posix()):
            entries.append({'path':file.relative_to(stage).as_posix(),'size':file.stat().st_size,'sha256':sha256(file)})
    names={entry['path'] for entry in entries}
    if REQUIRED-names:raise ValueError('Incomplete upstream base: '+', '.join(sorted(REQUIRED-names)))
    if any(not entry['size'] and (entry['path'] in REQUIRED or Path(entry['path']).suffix.lower() in {'.exe','.dll','.pyd'})
           for entry in entries):raise ValueError('Empty required upstream base file')
    if not any(name.startswith('_internal/iced_x86/') and name.endswith('.pyd') for name in names):
        raise ValueError('Upstream base lacks the frozen iced_x86 native dependency')
    if not any(name.startswith('_internal/python3') and name.endswith('.dll') for name in names):
        raise ValueError('Upstream base lacks the frozen Python runtime')
    return sorted(entries,key=lambda entry:entry['path'])


def prepare_manifest(stage,archive,expected_archive_sha256,recipe):
    """Only inventories an extracted asset; never executes it or modifies its files."""
    expected=require_hash(expected_archive_sha256,'upstream_archive_sha256')
    if sha256(archive)!=expected:raise ValueError('Upstream ZIP does not match the verified archive hash')
    entries=inventory(stage);archive_entries={}
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            if item.is_dir():continue
            full=relative_path(item.filename)
            if full.parts[0]!='gow3-windows':raise ValueError('Unexpected upstream ZIP root')
            name='/'.join(full.parts[1:])
            if allowed_base(name):
                if name in archive_entries:raise ValueError('Duplicate upstream ZIP entry')
                import hashlib
                archive_entries[name]={'path':name,'size':item.file_size,
                                      'sha256':hashlib.sha256(zipped.read(item)).hexdigest()}
    if entries!=[archive_entries[k] for k in sorted(archive_entries)]:
        raise ValueError('Extracted upstream base differs from the verified ZIP')
    if recipe.get('upstream_tag')!='windows-v2.1.8':raise ValueError('Expected the 2.1.8 packaging recipe')
    recipe={**recipe,'upstream_commit':require_hash(recipe.get('upstream_commit'),'upstream_commit',40),
            'package_script_sha256':require_hash(recipe.get('package_script_sha256'),'package_script_sha256')}
    return {'schema_version':1,'upstream_tag':'windows-v2.1.8','upstream_archive_sha256':expected,
            'packaging_recipe':recipe,'files':entries,
            'note':'Verified asset inventory; documented upstream recipe is not independent compiler attestation.'}


def verified_plan(stage,receipt,manifest_path=None):
    stage=Path(stage).resolve()
    manifest_path=Path(manifest_path) if manifest_path else stage.parent/'upstream-base-manifest.json'
    expected=require_hash(receipt.get('upstream_base_manifest_sha256'),'upstream_base_manifest_sha256')
    if sha256(manifest_path)!=expected:raise ValueError('Upstream base manifest does not match the receipt')
    manifest=read_object(manifest_path)
    tag=manifest.get('upstream_tag',manifest.get('tag'))
    if tag!='windows-v2.1.8':raise ValueError('Upstream base manifest is not 2.1.8')
    archive_hash=require_hash(manifest.get('upstream_archive_sha256',manifest.get('archive_sha256')),'upstream_archive_sha256')
    recipe=manifest.get('packaging_recipe')
    if recipe is None:
        # Existing parent inventory has tag/commit/archive_sha256, without inferred build versions.
        # Record the recipe from that exact upstream source revision; do not claim it attests the binary build.
        commit=require_hash(manifest.get('commit'),'upstream_commit',40)
        root=Path(__file__).resolve().parents[2]
        tag_commit=subprocess.check_output(['git','-C',str(root),'rev-parse','refs/tags/'+tag+'^{commit}']).decode().strip()
        if tag_commit!=commit:raise ValueError('Upstream inventory commit does not match the source tag')
        script=subprocess.check_output(['git','-C',str(root),'show',commit+':packaging/windows/package.sh'])
        import hashlib
        recipe={'upstream_tag':tag,'upstream_commit':commit,'package_script_sha256':hashlib.sha256(script).hexdigest(),
                'source_path':'packaging/windows/package.sh','frozen_entrypoint':'launcher/gow3_launcher_win.py',
                'iced_x86_requirement':'1.21.0','status':'Documented source recipe; actual compiler versions not independently attested.'}
    if not isinstance(recipe,dict) or recipe.get('upstream_tag')!=tag:
        raise ValueError('Missing upstream packaging recipe')
    require_hash(recipe.get('upstream_commit'),'upstream_commit',40)
    require_hash(recipe.get('package_script_sha256'),'package_script_sha256')
    rows=manifest.get('files')
    if not isinstance(rows,list):raise ValueError('Missing upstream file inventory')
    expected_files={}
    for entry in rows:
        name=relative_path(entry['path']).as_posix()
        if name in expected_files:raise ValueError('Duplicate upstream inventory entry')
        digest=require_hash(entry.get('sha256'),'upstream file sha256')
        file=stage/name
        if not file.is_file() or not file.resolve().is_relative_to(stage) or sha256(file)!=digest:
            raise ValueError('Upstream stage changed after receipt validation: '+name)
        if allowed_base(name):expected_files[name]={'path':name,'size':file.stat().st_size,'sha256':digest}
    files=inventory(stage)
    if files!=[expected_files[k] for k in sorted(expected_files)]:raise ValueError('Unexpected upstream base files')
    return {**manifest,'upstream_tag':tag,'upstream_archive_sha256':archive_hash,'packaging_recipe':recipe,
            'files':files,'manifest_sha256':expected,'stage':str(stage),'manifest':str(manifest_path),
            'frontend':'Official frozen launcher/role host; NVIDIA source frontend remains separate.'}


def install_base(stage,port,backup,plan):
    """Called only by an explicitly applied installer; tests use disposable fixture targets."""
    stage=Path(stage).resolve();port=Path(port).resolve();backup=Path(backup).resolve()
    if stage==port or stage.is_relative_to(port) or backup==port or backup.is_relative_to(port):
        raise ValueError('Upstream stage and backup must be outside the installed port')
    if inventory(stage)!=plan['files']:raise ValueError('Upstream files changed before copy')
    targets=[]
    for entry in plan['files']:
        relative=relative_path(entry['path'])
        if not allowed_base(relative):raise ValueError('Protected target in upgrade plan')
        target=port/Path(relative)
        if not target.resolve().is_relative_to(port):raise ValueError('Upgrade target escapes installed port')
        for path in [target,*target.parents]:
            if path==port.parent:break
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('Linked installed target: '+relative.as_posix())
        if target.exists() and not target.is_file():raise ValueError('File/directory collision: '+relative.as_posix())
        targets.append((entry,target))
    internal=port/'_internal';saved_internal=backup/'_internal'
    if saved_internal.exists():raise ValueError('Use a fresh upstream backup directory')
    backup.mkdir(parents=True,exist_ok=True)
    # Save every overwritten existing base file before replacing the root executable.
    existing=[];created=[]
    for entry,target in targets:
        if entry['path'].startswith('_internal/'):continue
        if target.is_file():
            saved=backup/entry['path'];saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,saved);existing.append(entry['path'])
        else:created.append(entry['path'])
    # Move the complete old frozen environment into the explicit rollback directory;
    # overlaying it would leave obsolete modules able to shadow the new package.
    if internal.exists():
        if internal.resolve()!=port/'_internal' or not internal.is_dir():raise ValueError('Invalid frozen environment target')
        shutil.move(str(internal),str(saved_internal))
    try:
        for entry,target in targets:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/entry['path'],target)
            if sha256(target)!=entry['sha256']:raise ValueError('Upstream file changed during copy: '+entry['path'])
    except Exception:
        # Safe local rollback of only these explicit base paths. No player/NVIDIA tree is touched.
        for name in existing:shutil.copy2(backup/name,port/name)
        for name in created:(port/name).unlink(missing_ok=True)
        if internal.exists():
            if internal.resolve()!=port/'_internal':raise ValueError('Frozen rollback target escaped installed port')
            shutil.rmtree(internal)
        if saved_internal.exists():shutil.copytree(saved_internal,internal)
        raise
    (backup/'UPSTREAM-BASE-BACKUP.json').write_text(json.dumps(
        {'existing':existing,'created':created,'upstream_archive_sha256':plan['upstream_archive_sha256']},indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--sha256',required=True);parser.add_argument('--recipe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=prepare_manifest(args.stage,args.archive,args.sha256,read_object(args.recipe))
    args.output.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
