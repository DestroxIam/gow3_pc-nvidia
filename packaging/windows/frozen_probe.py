"""Frozen --script role smoke probe: imports/native helpers only, never run.py/game/UI."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import types


def code_signature(code):
    def value(item):
        if isinstance(item,types.CodeType):return code_signature(item)
        if isinstance(item,frozenset):return {'frozenset':sorted((value(v) for v in item),key=repr)}
        if isinstance(item,tuple):return [value(v) for v in item]
        if isinstance(item,bytes):return {'bytes':item.hex()}
        if isinstance(item,(str,int,float,bool)) or item is None:return item
        return repr(item)
    return {'code':code.co_code.hex(),'constants':[value(c) for c in code.co_consts],
            'names':code.co_names,'vars':code.co_varnames,'free':code.co_freevars,'cells':code.co_cellvars,
            'flags':code.co_flags,'args':(code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount),
            'exceptions':code.co_exceptiontable.hex()}


def main():
    import importlib.metadata
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if not getattr(sys,'frozen',False):raise RuntimeError('Probe requires the frozen role host')
    internal=Path(sys._MEIPASS).resolve();origins={};checks={}
    for name in ('dataclasses','iced_x86','iced_x86._iced_x86_py','PIL.Image','PIL.ImageFont','PIL._imaging','PIL._imagingft'):
        module=importlib.import_module(name);origin=Path(module.__file__).resolve()
        if not origin.is_relative_to(internal):raise RuntimeError('Module escaped frozen environment: '+name)
        origins[name]=origin.relative_to(internal).as_posix()
    import iced_x86
    from PIL import Image,ImageFont
    if iced_x86.Decoder(64,b'\x90').decode().mnemonic!=iced_x86.Mnemonic.NOP:
        raise RuntimeError('iced_x86 native decode failed')
    if Image.new('RGB',(2,2)).size!=(2,2):raise RuntimeError('Pillow image failed')
    ImageFont.load_default()
    for name in ('graphics_options','isa_rewrite','patches','prepare','gow3_dlss_control','gow3_launcher_dlss'):
        module=importlib.import_module(name)
        path=args.source/('launcher' if name.startswith('gow3_') else 'scripts')/(name+'.py')
        loaded=module.__loader__.get_code(name)
        wanted=compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0)
        checks[name]=code_signature(loaded)==code_signature(wanted)
    launcher=importlib.import_module('gow3_launcher_dlss')
    if launcher.VERSION!='2.1.8-nvidia-dev':raise RuntimeError('Wrong frozen launcher version')
    result={'passed':all(checks.values()),'launcher_version':launcher.VERSION,'python_version':sys.version.split()[0],
            'versions':{name:importlib.metadata.version(name) for name in ('Pillow','iced-x86','PyInstaller')},
            'module_origins':origins,'source_checks':checks,'role':'--script; imports only; no game launch'}
    args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if not result['passed']:raise RuntimeError('Frozen code differs from current 2.1.8 NVIDIA sources')


if __name__=='__main__':
    try:main()
    except Exception as error:
        if '--report' in sys.argv:
            path=Path(sys.argv[sys.argv.index('--report')+1])
            previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            previous.update(passed=False,error=type(error).__name__+': '+str(error))
            path.write_text(json.dumps(previous,indent=2),encoding='utf-8')
        sys.exit(1)
