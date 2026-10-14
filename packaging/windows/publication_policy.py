"""Shared, fail-closed publication paths and corresponding-source file policy."""
from pathlib import Path, PurePosixPath

BLOCKED_PARTS={'eboot.bin','sce_module','sce_sys','savedata','savedata_backups','settings.json',
               'user','out','cache','logs','__pycache__','.git','.env','.vs','.idea'}
BLOCKED_SUFFIXES={'.iso','.pkg','.prx','.sprx','.raw','.log','.pdb','.obj','.ilk','.exp','.pyc',
                  '.dmp','.safetensors','.onnx','.weights','.pth','.pt','.tflite','.bin','.original'}
SOURCE_SUFFIXES={'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx','.inl','.inc','.ixx',
                 '.hlsl','.hlsli','.glsl','.vert','.frag','.comp','.geom','.tesc','.tese',
                 '.md','.txt','.rst','.html','.ini','.json','.yml','.yaml','.xml','.props',
                 '.targets','.vcxproj','.filters','.sln','.rc','.def','.cmake','.py','.ps1',
                 '.sh','.bat','.cmd','.reg','.patch','.diff','.natvis','.cube','.png','.jpg',
                 '.jpeg','.gif','.svg','.ico','.ttf','.otf'}
SOURCE_ROOTS={'optiscaler','external','tests','docs','tools','licenses','images','luts','.github','redist'}
SOURCE_NAMES={'license','copying','notice','authors','cmakelists.txt','makefile',
              '.gitmodules','.gitignore','.gitattributes','.clang-format'}
BUILD_PARTS={'x64','x86','release','debug','build','dist','node_modules','__pycache__'}
GENERATED_NAMES={'resource_build_commit.h','resource_build_date.h'}

def update_checksum(path, archive_name, archive_hash):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    lines=path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    lines=[line for line in lines if not line.endswith('  '+archive_name)]
    lines.append(archive_hash+'  '+archive_name)
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')

def relative_path(value):
    text=str(value).replace('\\','/')
    path=PurePosixPath(text)
    if not text or path.is_absolute() or any(part in {'','..'} or ':' in part or '\0' in part
                                             for part in text.split('/')):
        raise ValueError('Unsafe publication path: '+text)
    return path

def allowed_publication(value):
    path=relative_path(value); parts={part.lower() for part in path.parts}; name=path.name.lower()
    model_dll=name.endswith('.dll') and 'dlssnr' in name and name!='nvngx.dll_dlssnr.dll'
    return not (parts & BLOCKED_PARTS or path.suffix.lower() in BLOCKED_SUFFIXES or model_dll)

def allowed_source(value, pinned=False):
    path=relative_path(value)
    if not allowed_publication(path) or (not pinned and {p.lower() for p in path.parts}&BUILD_PARTS):
        return False
    if path.name.lower() in GENERATED_NAMES: return False
    if len(path.parts)>1 and path.parts[0].lower() not in SOURCE_ROOTS: return False
    if path.name.lower() in SOURCE_NAMES: return True
    # Existing vendor link libraries and compiled shader assets are build inputs in the
    # pinned upstream archive; never take new/locally built binaries from the overlay.
    if pinned and path.suffix.lower() in {'.lib','.a','.spv','.cso'}: return True
    return path.suffix.lower() in SOURCE_SUFFIXES

def renderer_sync_report(public_root, renderer_root):
    """Check, never copy, the renderer source/shaders/tests the parent must integrate."""
    public_root=Path(public_root); renderer_root=Path(renderer_root)
    folders=('gpu/shadps4/video_core','gpu/shadps4/shader_recompiler','gpu/shim','gpu/patches','tests')
    suffixes={'.cpp','.cc','.cxx','.c','.h','.hpp','.inl','.inc','.glsl','.hlsl','.hlsli',
              '.comp','.frag','.vert','.geom','.tesc','.tese','.patch','.cmake'}
    checked=[]; mismatches=[]
    for folder in folders:
        directory=renderer_root/folder
        if not directory.is_dir(): continue
        for path in sorted(directory.rglob('*')):
            relative=path.relative_to(renderer_root)
            if not path.is_file() or (path.suffix.lower() not in suffixes and path.name!='CMakeLists.txt') or not allowed_publication(relative): continue
            if path.is_symlink(): raise ValueError('Symlink in renderer source: '+str(relative))
            destination=public_root/relative
            checked.append(relative.as_posix())
            if not destination.is_file() or destination.read_bytes()!=path.read_bytes():
                mismatches.append(relative.as_posix())
    for name in ('CMakeLists.txt','gpu/CMakeLists.txt','gpu/shadps4/CMakeLists.txt'):
        path=renderer_root/name
        if not path.is_file(): continue
        if path.is_symlink(): raise ValueError('Symlink in renderer source: '+name)
        checked.append(name)
        if not (public_root/name).is_file() or (public_root/name).read_bytes()!=path.read_bytes(): mismatches.append(name)
    if not checked: raise ValueError('No renderer source found for the synchronization check')
    return {'checked_files':len(checked),'mismatches':mismatches,'matched':not mismatches}
