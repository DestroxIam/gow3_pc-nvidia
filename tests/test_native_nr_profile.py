"""Native NR gate/config tests using dummy runtime files in disposable fixtures only."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from paths import ROOT
sys.path.insert(0,str(ROOT/'launcher'))
import gow3_dlss_control as control
import gow3_launcher_dlss as launcher


class NativeNrProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.port=Path(self.temp.name)
        (self.port/'scripts').mkdir()
        shutil.copy2(ROOT/'scripts/graphics_options.py',self.port/'scripts/graphics_options.py')
        self.base=b'[graphics]\nrender_resolution=4K\nfsr1=1\nrcas=1\n'
        (self.port/'gow3.ini').write_bytes(self.base)
        self.effects=self.port/'bin-native-effects'
        (self.effects/'OptiScaler/streamline').mkdir(parents=True)
        for name in control.FG_DLLS:
            (self.effects/'OptiScaler/streamline'/name).write_bytes(b'fixture only')
        for name in ('winmm.dll','gow3-probe.exe','gow3_dlss.dll','nvngx_dlss.dll'):
            (self.effects/name).write_bytes(b'fixture candidate')
        (self.effects/'OptiScaler.ini').write_text(
            '[FrameGen]\nEnabled=true\nFGInput=upscaler\nFGOutput=dlssg\n'
            '[DlssNr]\nEnabled=false\nRunBeforeSR=true\nNativeUpscaler=true\n'
            '[VulkanInterop]\nInputsInGeneral=false\n[Log]\nLogLevel=4\n',encoding='utf-8')
        self.model=self.effects/'OptiScaler/nvngx_dlssnr.dll'
        self.forwarder=self.effects/'OptiScaler/nvngx.dll_dlssnr.dll'
        self.model.write_bytes(b'fixture user model')
        self.forwarder.write_bytes(b'fixture forwarder')
        self.marker={'native_nr_after_sr':True,
            'optiscaler_sha256':hashlib.sha256((self.effects/'winmm.dll').read_bytes()).hexdigest(),
            'probe_sha256':hashlib.sha256((self.effects/'gow3-probe.exe').read_bytes()).hexdigest()}
        self.write_marker()
        pure=self.port/'bin-native-dlss'
        pure.mkdir()
        for name in ('gow3-probe.exe','gow3_dlss.dll','nvngx_dlss.dll'):
            (pure/name).write_bytes(b'fixture pure SR')
        (pure/'renderer-build.json').write_text('{}',encoding='utf-8')
        self.settings={**control.DEFAULTS,'dlss5_enabled':True,'dlssg_mode':'off'}

    def write_marker(self):
        (self.effects/'renderer-build.json').write_text(json.dumps(self.marker),encoding='utf-8')

    def configured(self,settings=None,name='NVIDIA GeForce RTX 5070'):
        with mock.patch.object(control,'gpu_name',return_value=name):
            env=control.configure_environment({}, settings or self.settings,self.port)
        ini=configparser.ConfigParser()
        ini.read(self.effects/'OptiScaler.ini')
        return env,ini

    def test_verified_candidate_routes_nr_without_fg_to_effects(self):
        profile=control.effective_profile(self.settings,self.port)
        self.assertEqual(profile['runtime_folder'],'bin-native-effects')
        self.assertTrue(profile['nr_enabled'])
        self.assertFalse(profile['nr_suspended'])
        self.assertEqual(profile['nr_stage'],'after_sr')
        env,ini=self.configured()
        self.assertEqual(Path(env['GOW3_PROBE']),self.effects/'gow3-probe.exe')
        self.assertEqual(env['GOW3_UPSCALER'],'dlss')
        self.assertEqual(ini['Upscalers']['VulkanUpscaler'],'dlss_12')
        self.assertTrue(ini.getboolean('VulkanInterop','InputsInGeneral'))
        self.assertTrue(ini.getboolean('DlssNr','Enabled'))
        self.assertTrue(ini.getboolean('DlssNr','NativeFrameGenerationOnly'))
        for key in ('NativeMotion','NativeInput','NativeUpscaler','NativeDepthFinder','RunBeforeSR','UseProxy','DeferredDLSS'):
            self.assertFalse(ini.getboolean('DlssNr',key),key)
        self.assertEqual(ini['DlssNr']['Passes'],'1')
        self.assertFalse(ini.getboolean('FrameGen','Enabled'))
        self.assertEqual(ini['FrameGen']['FGInput'],'nofg')
        self.assertEqual(ini['FrameGen']['FGOutput'],'nofg')
        self.assertEqual(ini['Log']['LogLevel'],'2')
        self.assertEqual((self.port/'gow3.ini').read_bytes(),self.base)
        self.assertTrue(self.settings['dlss5_enabled'])

    def test_old_or_malformed_manifest_and_old_dll_remain_suspended(self):
        for marker in ({}, {'native_nr_after_sr':'true',**{'optiscaler_sha256':self.marker['optiscaler_sha256']}},
                       {'native_nr_after_sr':True}, {'native_nr_after_sr':True,'optiscaler_sha256':'0'*64}, []):
            with self.subTest(marker=marker):
                (self.effects/'renderer-build.json').write_text(json.dumps(marker),encoding='utf-8')
                profile=control.effective_profile(self.settings,self.port)
                self.assertFalse(profile['nr_enabled'])
                self.assertTrue(profile['nr_suspended'])
                self.assertEqual(profile['runtime_folder'],'bin-native-dlss')
                control.validate(self.settings,self.port,name='RTX 5070')
                self.assertFalse(control.nr_control_state(self.settings,self.port,'RTX 5070')['can_enable'])
        self.write_marker()
        (self.effects/'winmm.dll').write_bytes(b'old DLL')
        capability=control.native_nr_capability(self.port)
        self.assertFalse(capability['available'])
        self.assertIn('does not match',capability['reason'])

    def test_missing_or_empty_model_and_missing_forwarder_block_requested_new_nr(self):
        for missing in (self.model,self.forwarder):
            with self.subTest(missing=missing.name):
                data=missing.read_bytes()
                missing.unlink()
                profile=control.effective_profile(self.settings,self.port)
                self.assertTrue(profile['native_nr_capability']['verified_build'])
                self.assertFalse(profile['nr_enabled'])
                self.assertFalse(control.nr_control_state(self.settings,self.port,'RTX 5070')['can_enable'])
                with self.assertRaisesRegex(ValueError,missing.name):
                    control.validate(self.settings,self.port,name='RTX 5070')
                missing.write_bytes(data)
        self.model.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'nvngx_dlssnr.dll'):
            control.validate(self.settings,self.port,name='RTX 5070')
        self.assertTrue(self.settings['dlss5_enabled'])

    def test_empty_or_missing_dll_cannot_enable_gate(self):
        dll=self.effects/'winmm.dll'
        dll.write_bytes(b'')
        self.marker['optiscaler_sha256']=hashlib.sha256(b'').hexdigest()
        self.write_marker()
        self.assertFalse(control.native_nr_capability(self.port)['available'])
        self.assertIn('empty',control.native_nr_capability(self.port)['reason'])
        dll.unlink()
        self.assertFalse(control.native_nr_capability(self.port)['available'])

    def test_missing_or_malformed_probe_manifest_hash_suspends_verified_opti(self):
        for expected in (None,'','not-a-hash','0'*63,True):
            with self.subTest(expected=expected):
                if expected is None: self.marker.pop('probe_sha256',None)
                else: self.marker['probe_sha256']=expected
                self.write_marker()
                capability=control.native_nr_capability(self.port)
                self.assertEqual(capability['optiscaler_sha256'],self.marker['optiscaler_sha256'])
                self.assertFalse(capability['verified_build'])
                self.assertFalse(capability['available'])
                self.assertIn('probe_sha256',capability['reason'])
                profile=control.effective_profile(self.settings,self.port)
                self.assertTrue(profile['nr_suspended'])
                self.assertEqual(profile['runtime_folder'],'bin-native-dlss')

    def test_mismatched_or_missing_probe_suspends_verified_opti(self):
        probe=self.effects/'gow3-probe.exe'
        original=probe.read_bytes()
        probe.write_bytes(b'old unverified renderer')
        capability=control.native_nr_capability(self.port)
        self.assertEqual(capability['optiscaler_sha256'],self.marker['optiscaler_sha256'])
        self.assertNotEqual(capability['probe_sha256'],self.marker['probe_sha256'])
        self.assertFalse(capability['verified_build'])
        self.assertIn('gow3-probe.exe does not match',capability['reason'])
        self.assertFalse(control.nr_control_state(self.settings,self.port,'RTX 5070')['can_enable'])
        probe.unlink()
        self.assertFalse(control.native_nr_capability(self.port)['available'])
        self.assertIn('gow3-probe.exe',control.native_nr_capability(self.port)['reason'])
        probe.write_bytes(b'')
        self.assertFalse(control.native_nr_capability(self.port)['verified_build'])
        self.assertIn('empty',control.native_nr_capability(self.port)['reason'])
        probe.write_bytes(original)
        self.assertTrue(control.native_nr_capability(self.port)['available'])
        self.assertTrue(self.settings['dlss5_enabled'])

    def test_launch_validation_refreshes_cached_probe_hash(self):
        probe=self.effects/'gow3-probe.exe'
        self.assertTrue(control.native_nr_capability(self.port)['verified_build'])
        previous=probe.stat()
        probe.write_bytes(b'x'*previous.st_size)
        os.utime(probe,ns=(previous.st_atime_ns,previous.st_mtime_ns))
        control.validate(self.settings,self.port,name='RTX 5070')
        self.assertFalse(control.effective_profile(self.settings,self.port)['nr_enabled'])

    def test_launch_validation_rehashes_even_if_ui_cached_identical_stat(self):
        dll=self.effects/'winmm.dll'
        self.assertTrue(control.native_nr_capability(self.port)['available'])
        previous=dll.stat()
        dll.write_bytes(b'x'*previous.st_size)
        os.utime(dll,ns=(previous.st_atime_ns,previous.st_mtime_ns))
        # Validation always refreshes the hash, regardless of any UI cache identity.
        control.validate(self.settings,self.port,name='RTX 5070')
        self.assertFalse(control.effective_profile(self.settings,self.port)['nr_enabled'])

    def test_saved_quality_and_presets_remain_controls_not_validation_claims(self):
        settings={**self.settings,'nvidia_mode':'dlaa','nvidia_quality':'ultra_performance','nvidia_nr_passes':'3',
                  'nvidia_nr_style':'cinematic','nvidia_nr_intensity':'150'}
        profile=control.effective_profile(settings,self.port)
        self.assertIsNone(profile['quality'])
        self.assertEqual(profile['dimensions']['input'],profile['dimensions']['output'])
        _,ini=self.configured(settings)
        self.assertEqual(ini['DlssNr']['Passes'],'3')
        self.assertEqual(ini['DlssNr']['Style'],'2')
        self.assertEqual(ini['DlssNr']['Intensity'],'1.5')
        state=control.nr_control_state(settings,self.port,'RTX 5070')
        self.assertTrue(state['selected'])
        self.assertIn('Mais passadas/presets são experimentais',state['text'])
        self.assertIn('BEFORE-SR permanece bloqueado',state['text'])

    def test_fg_nr_combo_is_explicitly_unverified(self):
        settings={**self.settings,'dlssg_mode':'2x'}
        profile=control.effective_profile(settings,self.port)
        self.assertFalse(profile['fg_nr_combination_tested'])
        _,ini=self.configured(settings)
        self.assertTrue(ini.getboolean('FrameGen','Enabled'))
        self.assertEqual(ini['FrameGen']['FGInput'],'upscaler')
        self.assertEqual(ini['FrameGen']['FGOutput'],'dlssg')
        self.assertIn('FG + NR ainda não validado',control.nr_control_state(settings,self.port,'RTX 5070')['text'])

    def test_older_gpu_requires_explicit_experimental_opt_in(self):
        for gpu in ('RTX 3080','RTX 4070'):
            with self.subTest(gpu=gpu):
                self.assertFalse(control.nr_control_state(self.settings,self.port,gpu)['can_enable'])
                with self.assertRaisesRegex(ValueError,'physically tested'):
                    control.validate(self.settings,self.port,name=gpu)
                settings={**self.settings,'nvidia_older_nr':True}
                control.validate(settings,self.port,name=gpu)
                state=control.nr_control_state(settings,self.port,gpu)
                self.assertTrue(state['can_enable'])
                self.assertIn('sem validação física',state['text'])

    def test_omitted_port_retains_safe_legacy_behavior(self):
        profile=control.effective_profile(self.settings)
        self.assertFalse(profile['nr_enabled'])
        self.assertEqual(profile['runtime_folder'],'bin-native-dlss')

    def test_headless_ui_enables_native_switch_only_with_verified_capability(self):
        app=launcher.Launcher.__new__(launcher.Launcher)
        values={key:mock.Mock(get=mock.Mock(return_value=value)) for key,value in self.settings.items()}
        values['gpu_id']=mock.Mock(get=mock.Mock(return_value='0'))
        app.var=lambda key,_group:values[key]
        app.ttk=SimpleNamespace(Combobox=type('FixtureCombo',(),{}))
        for attribute in ('nvidia_gpu_label','nvidia_build_label','nvidia_dlss_quality','nvidia_image_status',
            'nvidia_output_choice','nvidia_nr_effective','nvidia_nr_status','nvidia_nr_switch',
            'nvidia_fg_provider_choice','nvidia_fg_choice','nvidia_ada_switch','nvidia_older_switch','nvidia_compatibility'):
            setattr(app,attribute,mock.Mock())
        app.nvidia_quality_widgets=[]
        app.nvidia_nr_widgets=[]
        with mock.patch.object(launcher,'PORT_DIR',self.port),mock.patch.object(control,'gpu_name',return_value='RTX 5070'):
            app.refresh_nvidia()
            app.nvidia_nr_switch.configure.assert_called_with(state='normal')
            app.nvidia_nr_effective.set.assert_called_with(True)
            self.assertIn('selecionado para a próxima abertura',app.nvidia_nr_status.configure.call_args.kwargs['text'])
            self.assertIn('no menu',app.nvidia_nr_status.configure.call_args.kwargs['text'])
            self.assertIn('gameplay ainda não confirmada',app.nvidia_nr_status.configure.call_args.kwargs['text'])
            self.model.unlink()
            app.refresh_nvidia()
            app.nvidia_nr_switch.configure.assert_called_with(state='disabled')
            app.nvidia_nr_effective.set.assert_called_with(False)
            self.assertIn('nvngx_dlssnr.dll',app.nvidia_nr_status.configure.call_args.kwargs['text'])
        values['dlss5_enabled'].set.assert_not_called()  # UI suspension must preserve preference


if __name__=='__main__':unittest.main()
