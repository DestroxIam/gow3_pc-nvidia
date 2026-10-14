"""GoW3 NVIDIA launch profile; UI and instant launch use the same settings."""
import configparser
import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

DEFAULTS = {
    'nvidia_mode': 'dlss', 'nvidia_quality': 'performance',
    'nvidia_output_res': '3840x2160',
    'nvidia_pipeline': 'renderer',
    'dlss5_enabled': False, 'dlss5_quality': 'balanced', 'dlss5_strength': '100',
    'nvidia_nr_style': 'natural', 'nvidia_nr_passes': '1', 'nvidia_nr_intensity': '100',
    'nvidia_nr_colour': '100', 'nvidia_fg_provider': 'dlssg', 'dlssg_mode': '2x',
    'nvidia_ada_mfg': False, 'nvidia_older_nr': False, 'nvidia_fps_overlay': True,
}
MODEL_SCALE = {'light': '0.33', 'balanced': '0.5', 'high': '0.67', 'native': '1.0'}
QUALITIES = ('ultra_quality', 'quality', 'balanced', 'performance', 'ultra_performance')
OUTPUT_RESOLUTIONS = ('1280x720','1920x1080','2560x1440','3840x2160')
NATIVE_PRESETS = {'ultra_quality':5,'quality':1,'balanced':2,'performance':3,'ultra_performance':4}
NATIVE_RATIOS = {'ultra_quality':1.3,'quality':1.5,'balanced':1.7,'performance':2.0,'ultra_performance':3.0}

def renderer_dimensions(values):
    p=preferences(values)
    output=tuple(map(int,p['nvidia_output_res'].split('x')))
    ratio=1.0 if p['nvidia_mode']=='dlaa' else NATIVE_RATIOS[p['nvidia_quality']]
    internal=tuple(max(2,math.floor(v/ratio/2+.5)*2) for v in output)
    return {'input':internal,'output':output,'preset':0 if p['nvidia_mode']=='dlaa' else NATIVE_PRESETS[p['nvidia_quality']]}
FG_COUNTS = {'off': 0, **{f'{n}x': n-1 for n in range(2,7)}}
FG_DLLS = ('sl.interposer.dll', 'sl.common.dll', 'sl.dlss_g.dll', 'sl.reflex.dll', 'sl.pcl.dll', 'nvngx_dlssg.dll')

def preferences(values):
    p = {**DEFAULTS, **{k:v for k,v in values.items() if k in DEFAULTS}}
    for key in ('dlss5_enabled', 'nvidia_ada_mfg', 'nvidia_older_nr', 'nvidia_fps_overlay'):
        p[key] = p[key] is True
    for key, choices in {
        'nvidia_mode': ('off','dlaa','dlss'), 'nvidia_quality': QUALITIES,
        'nvidia_output_res':OUTPUT_RESOLUTIONS,
        'nvidia_pipeline':('renderer','capture'),
        'dlss5_quality': MODEL_SCALE, 'nvidia_nr_style': ('standard','natural','cinematic'),
        'nvidia_nr_passes': ('1','2','3'), 'nvidia_fg_provider': ('dlssg','xefg'), 'dlssg_mode': FG_COUNTS,
    }.items():
        if p[key] not in choices: p[key] = DEFAULTS[key]
    for key, maximum in (('dlss5_strength',100),('nvidia_nr_intensity',200),('nvidia_nr_colour',100)):
        try: p[key] = str(max(0,min(maximum,round(float(p[key])))))
        except (TypeError,ValueError): p[key] = DEFAULTS[key]
    return p

def read_capabilities(port):
    try: return json.loads((Path(port)/'user'/'dlss5_capabilities.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

@lru_cache(maxsize=8)
def gpu_name(port, gpu_id=''):
    try:
        result = subprocess.run([str(Path(port)/'bin'/'gow3-gpu-capabilities.exe'),'--list'],
            capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        rows = [line.split('\t') for line in result.stdout.splitlines()]
        rows = [row for row in rows if len(row)>=3 and row[0].isdigit()]
        selected = next((row for row in rows if row[0]==str(gpu_id)),None)
        if selected: return selected[1]
        default = next((row for row in rows if len(row)>4 and row[4]=='1'),None)
        if default: return default[1]
        discrete = next((row for row in rows if 'discrete' in row[2].lower()),None)
        if discrete: return discrete[1]
        if rows: return rows[0][1]
    except (OSError,subprocess.SubprocessError): pass
    return 'GPU nÃ£o identificada'

def hardware(name):
    match = re.search(r'RTX\s+(\d{2})\d{2}', name, re.I)
    generation = int(match.group(1)) if match else 0
    return {'name':name, 'rtx':bool(match), 'generation':generation,
            'native_fg':generation>=40, 'native_mfg':generation>=50}

def recommended(name):
    p = dict(DEFAULTS); h = hardware(name)
    if not h['rtx']:
        p.update(nvidia_mode='off',dlss5_enabled=False,dlssg_mode='off')
    elif h['generation']<50:
        p.update(dlss5_enabled=False,dlssg_mode='off',nvidia_fg_provider='xefg' if h['generation']<40 else 'dlssg')
    return p

@lru_cache(maxsize=8)
def _runtime_hash(path, size, modified, changed):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def native_nr_capability(port=None, refresh=False):
    """Opt-in build gate, not a claim that every GPU/preset/FG combination was tested."""
    result = {'verified_build':False, 'available':False, 'reason':'Native NR AFTER-SR requires a verified runtime manifest.',
              'model_present':False, 'forwarder_present':False, 'optiscaler_sha256':None, 'probe_sha256':None,
              'native_nr_fg_tested_multipliers':[]}
    if port is None: return result
    runtime = Path(port)/'bin-native-effects'
    try:
        marker = json.loads((runtime/'renderer-build.json').read_text(encoding='utf-8'))
        if not isinstance(marker, dict) or marker.get('native_nr_after_sr') is not True: return result
        if refresh: _runtime_hash.cache_clear()
        for field, name in (('optiscaler_sha256','winmm.dll'), ('probe_sha256','gow3-probe.exe')):
            expected = marker.get(field)
            if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
                result['reason'] = f'Native NR suspended: renderer-build.json needs {field} for {name}.'
                return result
            binary = runtime/name
            stat = binary.stat()
            if stat.st_size<=0: raise ValueError(f'{name} is empty')
            actual = _runtime_hash(str(binary.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            result[field] = actual
            if actual.lower()!=expected.lower():
                result['reason'] = f'Native NR suspended: {name} does not match the verified runtime hash ({field}).'
                return result
        result['verified_build'] = True
        tested=marker.get('native_nr_fg_tested_multipliers',[])
        result['native_nr_fg_tested_multipliers']=[2] if isinstance(tested,list) and any(type(v) is int and v==2 for v in tested) else []
        for field, name in (('model_present','nvngx_dlssnr.dll'), ('forwarder_present','nvngx.dll_dlssnr.dll')):
            file = runtime/'OptiScaler'/name
            result[field] = file.is_file() and file.stat().st_size>0
        missing = [name for field, name in (('model_present','nvngx_dlssnr.dll'), ('forwarder_present','nvngx.dll_dlssnr.dll'))
                   if not result[field]]
        if missing:
            result['reason'] = 'Native NR requires user-provided model / forwarder in bin-native-effects/OptiScaler: ' + ', '.join(missing)
        else:
            result.update(available=True, reason='Native NR AFTER-SR runtime hashes verified and user model present. Confirm SDK/NR execution in this run; other passes/presets remain experimental.')
    except (OSError, ValueError) as error:
        result['reason'] = 'Native NR suspended: runtime capability could not be verified (' + str(error) + ').'
    return result

def effective_profile(settings, port=None):
    """Requested next launch; this is not proof of SDK execution or GPU support."""
    p = preferences(settings)
    native = p['nvidia_pipeline']=='renderer' and p['nvidia_mode']!='off'
    capability = native_nr_capability(port) if native else None
    native_nr = bool(native and p['dlss5_enabled'] and capability['available'])
    nr = p['dlss5_enabled'] and (not native or native_nr)
    folder = ('bin-native-dlss' if p['dlssg_mode']=='off' and not native_nr else 'bin-native-effects') if native else (
        'bin-dlss5' if p['nvidia_mode']!='off' or nr or p['dlssg_mode']!='off' else 'bin')
    return {'runtime_folder':folder, 'pipeline':'renderer' if native else ('capture' if folder=='bin-dlss5' else 'base'),
            'image_mode':p['nvidia_mode'], 'quality':p['nvidia_quality'] if p['nvidia_mode']=='dlss' else None,
            'dimensions':renderer_dimensions(p) if native else None,
            'nr_requested':p['dlss5_enabled'], 'nr_enabled':nr, 'nr_suspended':p['dlss5_enabled'] and native and not native_nr,
            'nr_stage':'after_sr' if native_nr else ('capture' if nr else None), 'native_nr_capability':capability,
            'nr_passes':p['nvidia_nr_passes'] if nr else None,
            'fg_nr_combination_tested':bool(native_nr and p['nvidia_fg_provider']=='dlssg' and
                p['dlssg_mode']=='2x' and p['nvidia_nr_passes']=='1' and
                2 in capability['native_nr_fg_tested_multipliers']) if nr and p['dlssg_mode']!='off' else None,
            'fg_provider':p['nvidia_fg_provider'] if p['dlssg_mode']!='off' else None, 'fg_mode':p['dlssg_mode']}

def profile_summary(settings, port=None):
    profile = effective_profile(settings, port)
    mode = profile['image_mode']
    text = {'dlaa':'DLAA selecionado · reconstrução DLSS desligada · qualidade DLSS não se aplica.',
            'dlss':'DLSS selecionado · DLAA desligado · preset ' + str(profile['quality']) + '.',
            'off':'DLSS e DLAA desligados.'}[mode]
    dims = profile['dimensions']
    if dims:
        text += f" {dims['input'][0]} × {dims['input'][1]} interno → {dims['output'][0]} × {dims['output'][1]} alvo da imagem. A resolução apresentada pelo FG não foi medida."
    elif mode!='off':
        text += ' Compatibilidade processa a imagem pronta; a resolução interna não é calculada por esta guia.'
    return text + ' Aplicado na próxima abertura; confirme a execução no registro do jogo.'

def nr_control_state(settings, port, name):
    p=preferences(settings); profile=effective_profile(p,port); h=hardware(name)
    native=profile['pipeline']=='renderer'
    gpu_allowed=h['rtx'] and (h['generation']>=50 or p['nvidia_older_nr'])
    can_enable=bool(profile['native_nr_capability']['available'] and gpu_allowed) if native else True
    selected=bool(profile['nr_enabled'] and (gpu_allowed if native else True))
    if native:
        capability=profile['native_nr_capability']
        if not capability['available']:
            text='NR nativo suspenso · ' + capability['reason'] + ' Preferência salva preservada.'
        elif not h['rtx']:
            text='NR AFTER-SR requer uma GeForce RTX identificada; execução ainda não confirmada.'
        elif not gpu_allowed:
            text='NR AFTER-SR: RTX 30/40 não foram fisicamente validadas; marque o teste experimental para habilitar.'
        else:
            text=('NR AFTER-SR selecionado para a próxima abertura.' if selected else 'NR AFTER-SR disponível; desligado.')
            text+=' Uma passada é o perfil de teste. Confirme SDK/NR no registro desta partida; mais passadas/presets são experimentais. '
            text+='A inferência adiciona custo de GPU; não garante aumento de FPS. BEFORE-SR permanece bloqueado.'
            if p['dlssg_mode']!='off':
                text+=(' FG 2× + NR em uma passada foi observado no runtime aprovado; isso não valida todos os presets/escalas ou GPUs.'
                       if profile['fg_nr_combination_tested'] else ' Esta combinação FG + NR não foi validada; não extrapole o teste de 2× com uma passada.')
            if h['generation']<50: text+=' RTX 30/40: teste experimental, sem validação física.'
    else:
        text=('NR de Compatibilidade selecionado para a próxima abertura · experimental; requer modelo separado.'
              if selected else 'Neural Rendering desligado.')
    return {'can_enable':can_enable, 'selected':selected, 'text':text}

def validate(settings, port, name=None):
    p = preferences(settings); h = hardware(name or gpu_name(str(port),str(settings.get('gpu_id',''))))
    active = p['nvidia_mode']!='off' or p['dlss5_enabled'] or p['dlssg_mode']!='off'
    if active and not h['rtx']: raise ValueError('Os recursos NVIDIA exigem uma GeForce RTX. Desative-os e use o FSR na guia Display.')
    native=p['nvidia_pipeline']=='renderer' and p['nvidia_mode']!='off'
    capability = native_nr_capability(port, refresh=True) if native else None
    if native and p['dlss5_enabled'] and capability['verified_build'] and not capability['available']:
        raise ValueError(capability['reason'])
    if native and p['dlss5_enabled'] and capability['available'] and h['generation']<50 and not p['nvidia_older_nr']:
        raise ValueError('Native NR AFTER-SR has only been physically tested on RTX 5070. RTX 30/40 require the explicit experimental test option.')
    if p['dlss5_enabled'] and not native and h['generation']<50 and not p['nvidia_older_nr']:
        raise ValueError('Neural Rendering nÃ£o foi validado nas RTX 30/40 com este modelo. Use o perfil recomendado ou marque o teste experimental.')
    if p['dlss5_enabled'] and not native and not (Path(port)/'bin-dlss5/OptiScaler/nvngx_dlssnr.dll').is_file():
        raise ValueError('Neural Rendering requires a user-supplied nvngx_dlssnr.dll. See docs/NVIDIA.md.')
    if p['dlssg_mode']!='off':
        if p['nvidia_mode']=='off': raise ValueError('Escolha DLAA ou DLSS para fornecer a entrada da geraÃ§Ã£o de quadros.')
        count = FG_COUNTS[p['dlssg_mode']]
        if p['nvidia_fg_provider']=='dlssg':
            if not h['native_fg']: raise ValueError('A RTX 30 nÃ£o oferece geraÃ§Ã£o NVIDIA nativa. Escolha XeFG 2Ã— experimental ou desligue a geraÃ§Ã£o.')
            if not h['native_mfg'] and count>1 and not p['nvidia_ada_mfg']:
                raise ValueError('Na RTX 40, use 2Ã— ou habilite explicitamente o MFG experimental.')
            folder = effective_profile(p,port)['runtime_folder']
            missing = [f for f in FG_DLLS if not (Path(port)/folder/'OptiScaler'/'streamline'/f).is_file()]
            if missing:
                raise ValueError(f'Geração de quadros incompleta em {folder}/OptiScaler/streamline: ' + ', '.join(missing))
        elif count>1:
            raise ValueError('O perfil XeFG deste configurador permite 2Ã—. Os multiplicadores 3Ã—â€“6Ã— pertencem ao perfil NVIDIA.')
    profile = effective_profile(p,port)
    folder = profile['runtime_folder']
    runtime = Path(port)/folder
    if profile['pipeline']=='renderer' and not (runtime/'renderer-build.json').is_file():
        raise ValueError(f'Renderizador DLSS nativo não instalado em {folder}. Reinstale esta versão ou escolha Compatibilidade.')
    if folder!='bin':
        required = ('gow3-probe.exe','gow3_dlss.dll','nvngx_dlss.dll') if folder=='bin-native-dlss' else (
            'gow3-probe.exe','winmm.dll','OptiScaler.ini')
        missing = [file for file in required if not (runtime/file).is_file()]
        if missing:
            raise ValueError(f'Instalação NVIDIA incompleta em {folder}: ' + ', '.join(missing))
    return p

def configure_environment(env, settings, port):
    port=Path(port); p=validate(settings,port)
    profile=effective_profile(p,port)
    if p['nvidia_pipeline']=='renderer' and p['nvidia_mode']!='off':
        folder=profile['runtime_folder']
        if not (port/folder/'renderer-build.json').is_file():
            raise ValueError('Renderizador DLSS nativo nÃ£o instalado. Reinstale esta versÃ£o ou escolha Compatibilidade.')
    if profile['runtime_folder']=='bin-native-dlss':
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('gow3_native_graphics_options',port/'scripts/graphics_options.py')
        graphics=module_from_spec(spec);spec.loader.exec_module(graphics)
        config=port/'user/NVIDIA-renderer.ini';config.parent.mkdir(exist_ok=True)
        config.write_bytes((port/'gow3.ini').read_bytes());dimensions=renderer_dimensions(p)
        graphics.write_keys(config,{'render_resolution':'native','upscaler':'dlss','preset':str(dimensions['preset']),
                                   'output_res':p['nvidia_output_res'],'fsr1':'0','rcas':'0','jitter':'1'})
        for key in ('GOW3_RENDER_RES','GOW3_NVIDIA_QUALITY'):env.pop(key,None)
        env.update(GOW3_CONFIG=str(config),GOW3_UPSCALER='dlss',GOW3_EXPERIMENTAL_UPSCALER='1',
                   GOW3_PROBE=str(port/'bin-native-dlss/gow3-probe.exe'),GOW3_SCENE_STENCIL_BITS='1',
                   GOW3_UPSCALE_PRESET=str(dimensions['preset']),GOW3_JITTER='1',GOW3_FSR1='0',GOW3_RCAS='0')
        return env
    for key in ('GOW3_PROBE','GOW3_NVIDIA_QUALITY','GOW3_FSR1','GOW3_RCAS'):
        env.pop(key,None)
    nvidia=p['nvidia_mode']!='off'; fg=p['dlssg_mode']!='off'; nr=profile['nr_enabled']
    if not (nvidia or fg or nr): return env
    native=nvidia and p['nvidia_pipeline']=='renderer' and (port/'bin-native-effects/renderer-build.json').is_file()
    runtime=port/('bin-native-effects' if native else 'bin-dlss5')
    for file in ('gow3-probe.exe','winmm.dll','OptiScaler.ini'):
        if not (runtime/file).is_file(): raise ValueError('InstalaÃ§Ã£o NVIDIA incompleta: '+file)
    cfg=configparser.ConfigParser(interpolation=None,strict=False); cfg.optionxform=str
    cfg.read(runtime/'OptiScaler.ini',encoding='utf-8-sig')
    updates={
      'Upscalers':{'Dx12Upscaler':'dlss','VulkanUpscaler':'dlss'},
      'FrameGen':{'External':'false','Enabled':str(fg).lower(),'FGInput':'upscaler',
                  'FGOutput':p['nvidia_fg_provider'] if fg else 'xefg','FGNvngxReplacement':'None','StreamlineIgnoreOTA':'true'},
      'DLSSG':{'InterpolationCount':str(FG_COUNTS[p['dlssg_mode']] or 1),'ForceDMFG':'false',
               'UseGamesReflexMarkers':'false','AdaMfgUnlock':str(p['nvidia_ada_mfg']).lower(),'AmpereMfgUnlock':'false'},
      'XeFG':{'InterpolationCount':'1'},
      'DlssNr':{'Enabled':str(nr).lower(),'NativeMotion':'true','NativeDepthFinder':'true','NativeUpscaler':str(nvidia).lower(),
                'NativeInput':str(not nvidia).lower(),'NativeFrameGenerationOnly':'false','FinishedPicture':str(not nvidia).lower(),
                'RunBeforeSR':str(nvidia).lower(),'Passes':p['nvidia_nr_passes'],'UnlockPasses':'false',
                'WorkingScale':MODEL_SCALE[p['dlss5_quality']],'Preset':'0',
                'Style':str(('standard','natural','cinematic').index(p['nvidia_nr_style'])),
                'Intensity':str(int(p['nvidia_nr_intensity'])/100),
                'TransferStrength':str(int(p['dlss5_strength'])/100),'ColourStrength':str(int(p['nvidia_nr_colour'])/100),
                'ToggleKey':'0x75','ApplyModel':'true'},
      'Menu':{'ShortcutKey':'0x24','FGShortcutKey':'-1','ShowFps':str(p['nvidia_fps_overlay']).lower(),
              'FpsOverlayPos':'0','FpsOverlayType':'1','FpsScale':'1.0'},
      'Log':{'LogToFile':'true','LogLevel':'4','LogToConsole':'false','LogToNGX':'false','LogToDebug':'false',
             'SingleFile':'true','OpenConsole':'false','LogFileName':str(port/'user'/'NVIDIA.log')}
    }
    if native:
        updates['DlssNr'].update(Enabled='false',NativeMotion='false',NativeDepthFinder='false',NativeUpscaler='false',
                                NativeInput='false',NativeFrameGenerationOnly='true',FinishedPicture='false',RunBeforeSR='true')
        if profile['nr_stage']=='after_sr':
            updates['Upscalers']['VulkanUpscaler']='dlss_12'  # DLSS_on12 native-input bridge
            updates['VulkanInterop']={'InputsInGeneral':'true','DredDiagnostics':'false'}
            updates['DLSS']={'Enabled':'true'}
            updates['DlssNr'].update(Enabled='true',RunBeforeSR='false',DeferredDLSS='false',UseProxy='false',
                Precision='0',ModelResolutionAuto='false',SpatialCompression='false',DetailReuse='false',
                LocalStructure='1.0',LocalTone='1.0',SkinStructure='1.0',AutoMask='true',ColourEncoding='auto',
                LutFile='',AutoCapture='false',ProbeD3D11='false',ProxyProbe='false',FrameStats='false')
            updates['Sharpness']={'OverrideSharpness':'true','Sharpness':'0'}
            updates['CAS']={'Enabled':'false'}
            updates['OutputScaling']={'Enabled':'false'}
            updates['Hotfix']={'RestoreComputeSignature':'false','RestoreGraphicSignature':'false',
                              'ColorResourceBarrier':'auto','OutputResourceBarrier':'auto'}
            if not fg:
                updates['FrameGen'].update(FGInput='nofg',FGOutput='nofg')
            updates['Log'].update(LogLevel='2',LogAsync='false')
    # Clear inherited per-pass look overrides so the selected preset really controls all passes.
    if cfg.has_section('DlssNr'):
        for key in list(cfg['DlssNr']):
            if re.match(r'Pass[23](Preset|Style|Intensity|LocalStructure|LocalTone|SkinStructure|AutoMask)$',key):
                cfg['DlssNr'][key]='auto'
    for section,keys in updates.items():
        if not cfg.has_section(section): cfg.add_section(section)
        cfg[section].update(keys)
    destination=runtime/'OptiScaler.ini'; temporary=destination.with_suffix('.ini.pending')
    with temporary.open('w',encoding='utf-8') as f: cfg.write(f)
    os.replace(temporary,destination)
    env.update(GOW3_PROBE=str(runtime/'gow3-probe.exe'),GOW3_UPSCALER='none',GOW3_EXPERIMENTAL_UPSCALER='0')
    if nvidia:
        env.update(GOW3_NVIDIA_QUALITY='dlaa' if p['nvidia_mode']=='dlaa' else p['nvidia_quality'],GOW3_FSR1='0',GOW3_RCAS='0')
    if native:
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('gow3_native_graphics_options',port/'scripts/graphics_options.py')
        graphics=module_from_spec(spec);spec.loader.exec_module(graphics)
        config=port/'user/NVIDIA-renderer.ini';config.parent.mkdir(exist_ok=True)
        config.write_bytes((port/'gow3.ini').read_bytes())
        dimensions=renderer_dimensions(p)
        graphics.write_keys(config,{'render_resolution':'native','upscaler':'dlss','preset':str(dimensions['preset']),
                                   'output_res':p['nvidia_output_res'],'fsr1':'0','rcas':'0','jitter':'1'})
        for key in ('GOW3_RENDER_RES','GOW3_NVIDIA_QUALITY'):env.pop(key,None)
        env.update(GOW3_CONFIG=str(config),GOW3_UPSCALER='dlss',GOW3_EXPERIMENTAL_UPSCALER='1',
                   GOW3_SCENE_STENCIL_BITS='1',GOW3_UPSCALE_PRESET=str(dimensions['preset']),GOW3_JITTER='1')
    return env

def running_game(port):
    """Check only our installed runtime paths, without stopping other programs."""
    if os.name!='nt': return False
    import ctypes.wintypes as wt
    k=ctypes.WinDLL('kernel32',use_last_error=True); ps=ctypes.WinDLL('psapi',use_last_error=True)
    k.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD]; k.OpenProcess.restype=wt.HANDLE
    k.QueryFullProcessImageNameW.argtypes=[wt.HANDLE,wt.DWORD,wt.LPWSTR,ctypes.POINTER(wt.DWORD)]
    k.CloseHandle.argtypes=[wt.HANDLE]
    ids=(wt.DWORD*4096)(); size=wt.DWORD()
    if not ps.EnumProcesses(ids,ctypes.sizeof(ids),ctypes.byref(size)): return False
    targets={str(Path(port)/folder/'gow3-probe.exe').lower() for folder in ('bin','bin-dlss5','bin-native-dlss','bin-native-effects')}
    for pid in ids[:size.value//ctypes.sizeof(wt.DWORD)]:
        handle=k.OpenProcess(0x1000,False,pid)
        if not handle: continue
        try:
            text=ctypes.create_unicode_buffer(32768); n=wt.DWORD(len(text))
            if k.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(n)) and text.value.lower() in targets: return True
        finally: k.CloseHandle(handle)
    return False
