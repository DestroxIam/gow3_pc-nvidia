#!/usr/bin/env python3
"""Pinned OptiScaler source plus the full source-only overlay; no production side effects on import."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from publication_policy import allowed_source, relative_path, update_checksum

UPSTREAM_COMMIT='ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69'
UPSTREAM_ROOT='OptiScaler-F5-DLSSNR-Multipass-'+UPSTREAM_COMMIT
PREFIX='OptiScaler-GoW3-source/'

def digest(data): return hashlib.sha256(data).hexdigest()

def collect_source(upstream_zip, source):
    source=Path(source)
    if not source.is_dir(): raise ValueError('Source overlay does not exist')
    files={}; pinned={}; excluded=[]
    with zipfile.ZipFile(upstream_zip) as original:
        for item in original.infolist():
            if item.is_dir(): continue
            full=relative_path(item.filename)
            if len(full.parts)<2 or full.parts[0]!=UPSTREAM_ROOT:
                raise ValueError('Upstream archive must be rooted at '+UPSTREAM_ROOT)
            relative='/'.join(full.parts[1:])
            if not allowed_source(relative,pinned=True):
                excluded.append(relative); continue
            if relative in files: raise ValueError('Duplicate upstream entry: '+relative)
            files[relative]=pinned[relative]=original.read(item)
    if not files or 'LICENSE' not in files: raise ValueError('Pinned source archive is incomplete: LICENSE required')
    overlay=[]
    for path in sorted(source.rglob('*')):
        if not path.is_file(): continue
        relative=path.relative_to(source).as_posix()
        if not allowed_source(relative):
            excluded.append(relative); continue
        if path.is_symlink(): raise ValueError('Symlink source overlay is not allowed: '+relative)
        data=path.read_bytes()
        if pinned.get(relative)!=data:
            overlay.append({'path':relative,'change':'modified' if relative in pinned else 'added',
                            'size':len(data),'sha256':digest(data)})
        files[relative]=data
    manifest={'upstream_commit':UPSTREAM_COMMIT,'upstream_archive_sha256':digest(Path(upstream_zip).read_bytes()),
              'overlay':overlay,'excluded_paths':sorted(set(excluded)), 'file_count':len(files),
              'nr_model_included':False,'game_files_included':False,
              'runtime_validation':'Parent-owned; this source snapshot does not certify a runtime binary.'}
    return files,manifest

def package_source(upstream_zip,source,output,checksum_file=None):
    files,manifest=collect_source(upstream_zip,source)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    notice=('# Corresponding optional-mod source\n\n'
        'Upstream janblade/OptiScaler-F5-DLSSNR-Multipass, commit '+UPSTREAM_COMMIT+'.\n'
        'This archive overlays every allowed added/modified source, shader, project, test and documentation file. '
        'GOW3-SOURCE-MANIFEST.json records their hashes, including ImGui backend changes. '
        'The earlier three-patch bundle alone is not the full current overlay.\n\n'
        'GPL-3.0; retain LICENSE and dependency/vendor notices. Clone the pinned repository recursively '
        'and initialize its dependencies before overlaying these files if dependencies are missing. '
        'Build Release x64 with MSVC 14.44 and Windows SDK 10.0.26100.0. '
        'No runtime executables, DLLs, NR model weights, game files, captures or logs are supplied. '
        'Pinned vendor link libraries and shader build inputs retain their upstream licenses. '
        'Runtime pairing/validation and the release capability flags belong to the parent.\n')
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as result:
        for name,data in sorted(files.items()): result.writestr(PREFIX+name,data)
        result.writestr(PREFIX+'GOW3-SOURCE-NOTICE.md',notice)
        result.writestr(PREFIX+'GOW3-SOURCE-MANIFEST.json',json.dumps(manifest,indent=2))
    manifest['archive_sha256']=digest(output.read_bytes())
    output.with_suffix('.audit.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    checksums=Path(checksum_file) if checksum_file else output.with_name(output.name+'.sha256')
    update_checksum(checksums,output.name,manifest['archive_sha256'])
    return manifest

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-zip',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--checksum-file',type=Path,help='Update this archive entry, retaining other release checksums')
    parser.add_argument('--audit-only',action='store_true',help='Inventory without creating/changing any archive')
    args=parser.parse_args(argv)
    if args.audit_only: _,manifest=collect_source(args.upstream_zip,args.source)
    elif args.output: manifest=package_source(args.upstream_zip,args.source,args.output,args.checksum_file)
    else: parser.error('--output is required unless --audit-only is selected')
    print(json.dumps({'upstream_commit':UPSTREAM_COMMIT,'files':manifest['file_count'],
        'overlay_files':len(manifest['overlay']),'overlay_paths':[entry['path'] for entry in manifest['overlay']],
        'nr_model_included':False,'game_files_included':False,'audit_only':args.audit_only,
        'archive_sha256':manifest.get('archive_sha256')},indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
