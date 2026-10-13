#!/usr/bin/env python3
"""Freeze the preview launcher without collecting game content."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[2]
hidden=('argparse','base64','collections','configparser','hashlib','json','math','re','shutil','struct','tempfile',
        'xml.etree.ElementTree','urllib.request','ctypes.wintypes','importlib.util','gow3_lang','gow3_dlss_control',
        'gow3_redesign','game_layout','button_icons','gow3_vulkan','gow3_assets')
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--log-level','WARN','--windowed',
         '--name','God of War III','--icon',str(root/'launcher/gow3.ico'),
         '--distpath',str(root/'out/nvidia-launcher-dist'),'--workpath',str(root/'out/nvidia-launcher-work'),
         '--specpath',str(root/'out/nvidia-launcher-work'),'--paths',str(root/'scripts'),'--paths',str(root/'launcher')]
for name in hidden:command+=['--hidden-import',name]
command+=[str(root/'launcher/gow3_launcher_win.py')]
subprocess.run(command,cwd=root,check=True)
print('NVIDIA launcher frozen in out/nvidia-launcher-dist/God of War III')
