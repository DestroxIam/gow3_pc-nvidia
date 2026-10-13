# SPDX-License-Identifier: GPL-2.0-or-later
"""Portable Game layout. Never extracts, moves or downloads game content."""
from pathlib import Path
def usable(path):
    path=Path(path)
    return (path/'eboot.bin').is_file() and (path/'sce_sys').is_dir() and (path/'sce_module').is_dir()
def find_game(port):
    root=Path(port)/'Game'
    if usable(root):return root
    if not root.is_dir():return None
    candidates=[p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and usable(p)]
    preferred=[p for p in candidates if p.name=='CUSA01623']
    return preferred[0] if len(preferred)==1 else candidates[0] if len(candidates)==1 else None
def resolve_settings(settings,port):
    result=dict(settings)
    if not result.get('game_dir') or not usable(result['game_dir']):
        found=find_game(port)
        if found:result['game_dir']=str(found)
    return result
