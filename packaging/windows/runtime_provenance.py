"""Build-time source snapshots and receipt-bound runtime identity; no live operations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from publication_policy import BLOCKED_PARTS, BUILD_PARTS, SOURCE_SUFFIXES, relative_path


def sha256(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def tested_nr_fg_multipliers(record):
    values=record.get('native_nr_fg_tested_multipliers',[])
    return [2] if record.get('native_nr_after_sr') is True and isinstance(values,list) and any(
        type(v) is int and v==2 for v in values) else []


def read_object(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object: ' + Path(path).name)
    return value


def require_hash(value, field, length=64):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{'+str(length)+'}', value):
        raise ValueError('Missing or invalid ' + field)
    return value.lower()


def build_recipe(value):
    """Require actual commands/toolchain metadata without publishing workstation paths."""
    if not isinstance(value, dict) or not value.get('commands') or not value.get('toolchain'):
        raise ValueError('build_recipe requires commands and toolchain metadata')
    if not isinstance(value['commands'], list) or any(
            not isinstance(cmd, list) or not cmd or any(not isinstance(arg, str) for arg in cmd)
            for cmd in value['commands']):
        raise ValueError('build_recipe commands must be nonempty argv lists')
    if not isinstance(value['toolchain'], dict) or not all(
            isinstance(v,str) and v.strip() for v in value['toolchain'].values()):
        raise ValueError('build_recipe toolchain must be an object with versions')
    def check(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.search(r'password|secret|token|credential', key, re.I):
                    raise ValueError('Private field in build_recipe')
                check(child)
        elif isinstance(item, list):
            for child in item: check(child)
        elif isinstance(item, str):
            if len(item)>2048 or re.search(r'(?i)(?:[a-z]:[\\/]|\\\\|/home/|/Users/)', item):
                raise ValueError('build_recipe must use relative paths and public toolchain names')
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise ValueError('Invalid build_recipe value')
    check(value)
    return value


def source_path(name):
    path = relative_path(name)
    parts = {part.lower() for part in path.parts}
    # Cover all tracked source roots (src, scripts, renderer, tests, packaging), not just GPU.
    # Tracked dependency binaries and fixtures belong to the source tree too; runtime outputs do not.
    return not (parts & (BLOCKED_PARTS | BUILD_PARTS) or
                any(part.lower().startswith('.env') for part in path.parts) or
                path.suffix.lower() in {'.dll', '.exe', '.log', '.iso', '.pkg', '.pdb', '.pyc', '.raw'})


def source_inventory(source):
    source = Path(source)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args])
    if Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()!=source.resolve():
        raise ValueError('Uninitialized source dependency: '+source.name)
    names = git('ls-files', '-z') + git('ls-tree','-r','--name-only','-z','HEAD')
    tracked = sorted({name for name in names.decode('utf-8').split('\0') if name and source_path(name)})
    # HEAD comparison includes staged + unstaged changes, deletes, renames and submodule pointers.
    # Bounded argv batches stay below Windows command-line limits; disable rename detection
    # so moving a file between batches still has a stable, complete add/delete representation.
    patches = []
    for i in range(0,len(tracked),80):
        patches.append(git('diff', '--binary', '--no-renames', '--no-ext-diff', '--no-textconv',
                           '--ignore-submodules=none', 'HEAD', '--', *tracked[i:i+80]))
    patch = b''.join(patches)
    untracked = sorted(name for name in git('ls-files', '--others', '--exclude-standard', '-z')
                       .decode('utf-8').split('\0') if name and source_path(name) and
                       Path(name).suffix.lower() in SOURCE_SUFFIXES)
    entries = []; dependency_dirty = False
    for name in tracked + untracked:
        path = source/name
        if path.is_symlink(): raise ValueError('Symlink in build source: '+name)
        if path.is_file(): entries.append({'path':name, 'sha256':sha256(path)})
        elif not path.exists(): entries.append({'path':name, 'deleted':True})
        elif path.is_dir():
            # A tracked directory is a gitlink; record current dependency commit + dirty content.
            dependency = source_inventory(path)
            dependency_dirty |= dependency['source_dirty']
            entries.append({'path':name, 'gitlink':subprocess.check_output(
                ['git','-C',str(path),'rev-parse','HEAD']).decode().strip(),
                'source_inventory':dependency})
    return {'source_dirty':bool(patch or untracked or dependency_dirty),
            'tracked_source_diff_sha256':hashlib.sha256(patch).hexdigest(),
            'untracked_source_sha256':json_digest([e for e in entries if e['path'] in untracked]),
            'source_tree_sha256':json_digest(sorted(entries,key=lambda e:e['path']))}


def source_snapshot(source, upstream_tag, recipe):
    source = Path(source).resolve()
    if not isinstance(upstream_tag, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', upstream_tag):
        raise ValueError('Invalid upstream_tag')
    def git(*args): return subprocess.check_output(['git', '-C', str(source), *args]).decode().strip()
    head = git('rev-parse', 'HEAD')
    upstream = git('rev-parse', 'refs/tags/'+upstream_tag+'^{commit}')
    git('merge-base', '--is-ancestor', upstream, head)
    return {'source_commit':require_hash(head,'source_commit',40), 'upstream_tag':upstream_tag,
            'upstream_commit':require_hash(upstream,'upstream_commit',40),
            **source_inventory(source), 'build_recipe':build_recipe(recipe)}


def bind_snapshot(snapshot, source, stage):
    """Call after a successful build, with the snapshot captured BEFORE that build."""
    current = source_snapshot(source, snapshot['upstream_tag'], snapshot['build_recipe'])
    if snapshot != current:
        raise ValueError('Source changed during the build; rebuild from a fresh snapshot')
    probe = Path(stage)/'gow3-probe.exe'
    if not probe.is_file() or not probe.stat().st_size:
        raise ValueError('Nonempty staged gow3-probe.exe required')
    result = dict(snapshot, schema_version=1, probe_sha256=sha256(probe))
    (Path(stage)/'source-manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def verified_stage(stage, receipt, receipt_field='source_manifest_sha256', effects=False):
    stage = Path(stage)
    manifest_path = stage/'source-manifest.json'
    expected = require_hash(receipt.get(receipt_field), receipt_field)
    if sha256(manifest_path) != expected:
        raise ValueError('Staged source manifest does not match the tested receipt: '+receipt_field)
    manifest = read_object(manifest_path)
    identity = {field:require_hash(manifest.get(field),field,40) for field in ('source_commit','upstream_commit')}
    tag = manifest.get('upstream_tag')
    if not isinstance(tag,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*',tag):
        raise ValueError('Missing or invalid upstream_tag')
    identity['upstream_tag'] = tag
    if type(manifest.get('source_dirty')) is not bool: raise ValueError('Missing source_dirty flag')
    identity['source_dirty'] = manifest['source_dirty']
    for field in ('tracked_source_diff_sha256','untracked_source_sha256','source_tree_sha256'):
        identity[field] = require_hash(manifest.get(field),field)
    if not identity['source_dirty'] and identity['tracked_source_diff_sha256']!=hashlib.sha256(b'').hexdigest():
        raise ValueError('Clean source flag contradicts tracked source diff')
    if not identity['source_dirty'] and identity['untracked_source_sha256']!=json_digest([]):
        raise ValueError('Clean source flag contradicts untracked source inventory')
    identity['build_recipe'] = build_recipe(manifest.get('build_recipe'))
    for name,field in [('gow3-probe.exe','probe_sha256')] + ([('winmm.dll','optiscaler_sha256')] if effects else []):
        file = stage/name
        expected = require_hash(receipt.get(field),field)
        if not file.is_file() or not file.stat().st_size or sha256(file)!=expected or require_hash(
                manifest.get(field),field)!=expected:
            raise ValueError('Staged '+name+' does not match source manifest and tested receipt')
        identity[field] = expected
    identity['source_manifest_sha256'] = sha256(manifest_path)
    if effects:
        # An effects manifest must bind the corresponding full OptiScaler source inventory too.
        opti = manifest.get('optiscaler_source')
        if not isinstance(opti,dict): raise ValueError('Missing optiscaler_source provenance')
        identity['optiscaler_source'] = {
            'upstream_commit':require_hash(opti.get('upstream_commit'),'OptiScaler upstream_commit',40),
            **{field:require_hash(opti.get(field),'OptiScaler '+field) for field in
               ('upstream_archive_sha256','overlay_sha256','source_tree_sha256')},
            'build_recipe':build_recipe(opti.get('build_recipe'))}
    return identity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    snap=commands.add_parser('snapshot');snap.add_argument('--source',type=Path,required=True)
    snap.add_argument('--tag',required=True);snap.add_argument('--recipe',type=Path,required=True)
    snap.add_argument('--output',type=Path,required=True)
    bind=commands.add_parser('bind');bind.add_argument('--source',type=Path,required=True)
    bind.add_argument('--snapshot',type=Path,required=True);bind.add_argument('--stage',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='snapshot':
        data=source_snapshot(args.source,args.tag,read_object(args.recipe))
        args.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    else: bind_snapshot(read_object(args.snapshot),args.source,args.stage)


if __name__=='__main__': main()
