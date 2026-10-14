"""Headless launch tests: temporary files and fake processes, never a live game."""
import configparser
import hashlib
import io
import json
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

from paths import ROOT
sys.path.insert(0, str(ROOT / 'launcher'))
import gow3_dlss_control as control
import gow3_launcher_dlss as launcher


def process(output=b'boot\n', code=0):
    result = mock.Mock()
    result.stdout = io.BytesIO(output)
    result.wait.return_value = code
    return result


class ProfileTest(unittest.TestCase):
    def test_generated_native_fg_config_keeps_nr_disabled_and_base_config_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            port = Path(folder)
            (port/'scripts').mkdir()
            shutil.copy2(ROOT/'scripts/graphics_options.py', port/'scripts/graphics_options.py')
            original = b'[graphics]\nrender_resolution = 4K\nfsr1 = 1\nrcas = 1\n'
            (port/'gow3.ini').write_bytes(original)
            runtime = port/'bin-native-effects'
            (runtime/'OptiScaler/streamline').mkdir(parents=True)
            for name in control.FG_DLLS:
                (runtime/'OptiScaler/streamline'/name).touch()
            for name in ('renderer-build.json','gow3-probe.exe','winmm.dll','OptiScaler.ini'):
                (runtime/name).touch()
            settings = {'nvidia_mode':'dlaa','dlss5_enabled':True,'dlssg_mode':'2x'}
            with mock.patch.object(control, 'gpu_name', return_value='NVIDIA GeForce RTX 5070'):
                env = control.configure_environment({}, settings, port)
            cfg = configparser.ConfigParser()
            cfg.read(runtime/'OptiScaler.ini')
            self.assertFalse(cfg.getboolean('DlssNr','Enabled'))
            self.assertTrue(cfg.getboolean('DlssNr','NativeFrameGenerationOnly'))
            self.assertEqual(env['GOW3_UPSCALE_PRESET'], '0')
            self.assertEqual(Path(env['GOW3_PROBE']), runtime/'gow3-probe.exe')
            self.assertNotIn('GOW3_NVIDIA_QUALITY', env)
            self.assertEqual((port/'gow3.ini').read_bytes(), original)
            self.assertTrue(settings['dlss5_enabled'])

    def test_dlaa_excludes_reconstruction_and_retains_saved_dlss_quality(self):
        saved = {'nvidia_mode':'dlaa', 'nvidia_quality':'ultra_performance'}
        profile = control.effective_profile(saved)
        self.assertIsNone(profile['quality'])
        self.assertEqual(profile['dimensions']['input'], profile['dimensions']['output'])
        self.assertEqual(profile['dimensions']['preset'], 0)
        self.assertIn('qualidade DLSS não se aplica', control.profile_summary(saved))
        self.assertEqual(control.preferences(saved)['nvidia_quality'], 'ultra_performance')
        dlss = control.effective_profile({**saved, 'nvidia_mode':'dlss'})
        self.assertEqual(dlss['quality'], 'ultra_performance')
        self.assertEqual(dlss['dimensions']['input'], (1280, 720))

    def test_native_suspends_nr_with_or_without_fg(self):
        for fg, folder in [('off','bin-native-dlss'), ('2x','bin-native-effects')]:
            p = control.effective_profile({'dlss5_enabled':True, 'dlssg_mode':fg})
            self.assertTrue(p['nr_requested'])
            self.assertTrue(p['nr_suspended'])
            self.assertFalse(p['nr_enabled'])
            self.assertEqual(p['runtime_folder'], folder)
        capture = control.effective_profile({'dlss5_enabled':True, 'nvidia_pipeline':'capture'})
        self.assertTrue(capture['nr_enabled'])
        self.assertIsNone(capture['dimensions'])
        self.assertIn('imagem pronta', control.profile_summary({'nvidia_pipeline':'capture'}))

    def test_native_fg_checks_selected_runtime_not_capture_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            port = Path(folder)
            runtime = port/'bin-native-effects'
            (runtime/'OptiScaler/streamline').mkdir(parents=True)
            for name in control.FG_DLLS:
                (runtime/'OptiScaler/streamline'/name).touch()
            for name in ('renderer-build.json','gow3-probe.exe','winmm.dll','OptiScaler.ini'):
                (runtime/name).touch()
            settings = {'nvidia_mode':'dlss', 'dlssg_mode':'2x', 'dlss5_enabled':True}
            control.validate(settings, port, name='NVIDIA GeForce RTX 5070')
            (runtime/'OptiScaler/streamline/sl.dlss_g.dll').unlink()
            with self.assertRaisesRegex(ValueError, r'bin-native-effects/OptiScaler/streamline: sl.dlss_g.dll'):
                control.validate(settings, port, name='NVIDIA GeForce RTX 5070')
            (runtime/'OptiScaler/streamline/sl.dlss_g.dll').touch()
            (runtime/'winmm.dll').unlink()
            with self.assertRaisesRegex(ValueError, 'bin-native-effects: winmm.dll'):
                control.validate(settings, port, name='NVIDIA GeForce RTX 5070')

    def test_nr_and_gpu_requirements_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'nvngx_dlssnr.dll'):
                control.validate({'dlss5_enabled':True,'nvidia_pipeline':'capture'}, folder, name='RTX 5070')
            with self.assertRaisesRegex(ValueError, 'GeForce RTX'):
                control.validate({}, folder, name='AMD Radeon')


class DiagnosticsTest(unittest.TestCase):
    def test_gui_keeps_log_reader_alive_after_window_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            app = launcher.Launcher.__new__(launcher.Launcher)
            app.process = None
            app.app = {**launcher.APP_DEFAULTS, 'game_dir':folder, 'user_dir':folder, 'close_on_play':True}
            app.var = lambda key, _group:mock.Mock(get=lambda:app.app.get(key,''))
            for attribute in ('collect','set_log','nvidia_execution_status','root','status','play_button','append'):
                setattr(app, attribute, mock.Mock())
            diagnostics = {'runtime_sha256':'test hash', 'profile':{'pipeline':'renderer'}}
            with mock.patch.object(control, 'running_game', return_value=False), \
                 mock.patch.object(control, 'validate'), \
                 mock.patch.object(launcher, 'game_info', return_value=('God of War III','01.02')), \
                 mock.patch.object(launcher, 'missing_game_files', return_value=[]), \
                 mock.patch.object(launcher, 'game_environment', return_value={}), \
                 mock.patch.object(launcher, 'launch_diagnostics', return_value=diagnostics), \
                 mock.patch.object(launcher.subprocess, 'Popen', return_value=process()), \
                 mock.patch.object(launcher, 'GameJob'), \
                 mock.patch.object(launcher.threading, 'Thread') as thread:
                app.play()
            self.assertFalse(thread.call_args.kwargs['daemon'])
            self.assertEqual(thread.call_args.kwargs['args'][2], diagnostics)
            app.root.after.assert_called_once_with(5000, app.root.destroy)

    def test_actual_runtime_hash_and_allowlisted_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)/'private-test-probe.exe'
            runtime.write_bytes(b'test build')
            digest = hashlib.sha256(b'test build').hexdigest()
            (runtime.parent/'renderer-build.json').write_text(json.dumps({'probe_sha256':digest}), encoding='utf-8')
            env = {'GOW3_PROBE':str(runtime), 'GOW3_VK_VALIDATION':'1', 'TOKEN':'secret must not be logged'}
            info = launcher.launch_diagnostics({'nvidia_mode':'dlaa'}, env)
            self.assertEqual(info['runtime'], str(runtime))
            self.assertEqual(info['runtime_sha256'], digest)
            self.assertTrue(info['runtime_matches_manifest'])
            self.assertEqual(info['diagnostics_enabled']['GOW3_VK_VALIDATION'], '1')
            self.assertNotIn('secret', json.dumps(info))
            runtime.write_bytes(b'different test build')
            self.assertFalse(launcher.launch_diagnostics({}, env)['runtime_matches_manifest'])

    def test_logger_archives_preserves_output_and_reports_crash_code(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'last_run.log'
            path.write_text('previous crash\n', encoding='utf-8')
            forwarded = []
            code = launcher.record_game_output(process(b'scene\ninvalid: \xff\n', -1073741819), folder,
                forwarded.append, {'runtime_sha256':'test', 'profile':{'pipeline':'renderer'}})
            self.assertEqual(code, -1073741819)
            text = path.read_text(encoding='utf-8')
            self.assertIn('runtime_sha256', text)
            self.assertIn('scene\n', text)
            self.assertIn('0xC0000005', text)
            self.assertIn('\ufffd', text)
            archives = list((Path(folder)/'log').glob('run-*.log'))
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].read_text(), 'previous crash\n')

    def test_unwritable_log_does_not_stop_runtime_consumption(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder)/'file'
            blocked.touch()
            messages = []
            result = process(b'continues\n', 5)
            self.assertEqual(launcher.record_game_output(result, blocked, messages.append), 5)
            self.assertIn('continues\n', messages)
            self.assertTrue(any('Could not save' in m for m in messages))
            result.wait.assert_called_once()

    def test_write_failure_in_header_still_consumes_and_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            messages = []
            sink = mock.Mock()
            sink.write.side_effect = OSError('disk full')
            result = process(b'continues after header failure\n', 6)
            with mock.patch.object(Path, 'open', return_value=sink):
                self.assertEqual(launcher.record_game_output(result, folder, messages.append, {'runtime':'test'}), 6)
            self.assertIn('continues after header failure\n', messages)
            self.assertTrue(any('disk full' in message for message in messages))
            result.wait.assert_called_once()

    def test_midstream_exit_and_close_failures_preserve_process_exit_code(self):
        for failing_write in (2, 3, None):
            with self.subTest(failing_write=failing_write), tempfile.TemporaryDirectory() as folder:
                messages, written = [], []
                sink = mock.Mock()
                def write(text):
                    written.append(text)
                    if len(written)==failing_write:
                        raise ValueError('I/O operation on closed file')
                sink.write.side_effect = write
                sink.close.side_effect = OSError('close failed')
                result = process(b'first\nsecond\n', -1073741819)
                with mock.patch.object(Path, 'open', return_value=sink):
                    self.assertEqual(launcher.record_game_output(result, folder, messages.append), -1073741819)
                self.assertIn('first\n', messages)
                self.assertIn('second\n', messages)
                result.wait.assert_called_once()
                sink.close.assert_called_once()
                if failing_write is None:
                    self.assertIn('0xC0000005', written[-1])
                    self.assertTrue(any('close failed' in text for text in messages))
                else:
                    self.assertTrue(any('closed file' in text for text in messages))

    def test_closed_forwarding_console_does_not_break_file_or_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            result = process(b'capture survives closed console\n', 7)
            forward = mock.Mock(side_effect=ValueError('console closed'))
            self.assertEqual(launcher.record_game_output(result, folder, forward), 7)
            text = (Path(folder)/'last_run.log').read_text()
            self.assertIn('capture survives closed console', text)
            self.assertIn('0x00000007', text)
            result.wait.assert_called_once()

    def test_sdk_status_accepts_only_current_run_and_resets_restart_and_exit(self):
        app = launcher.Launcher.__new__(launcher.Launcher)
        app.output, app.ui_calls = queue.Queue(), queue.Queue()
        app.active_run_id = 'current'
        for attribute in ('root','append','status','nvidia_execution_status','job','refresh_status'):
            setattr(app, attribute, mock.Mock())
        app.process = mock.Mock()
        evaluated = 'GoW3 native DLSS: scene 1920x1080 -> output 3840x2160, evaluation 600'
        app.output.put(('old', evaluated))
        app.output.put(('current', '172 FPS 5.8 ms DLSS'))
        app.output.put(('current', 'GoW3 input state: camera 1 sample2 invalid'))
        app.drain_output()
        app.nvidia_execution_status.configure.assert_not_called()
        app.output.put(('current', evaluated))
        app.drain_output()
        self.assertIn('confirmada', app.nvidia_execution_status.configure.call_args.kwargs['text'])
        app.output.put(('current', 'restarting through run.py'))
        app.drain_output()
        self.assertIn('aguardando nova avaliação', app.nvidia_execution_status.configure.call_args.kwargs['text'])
        app.output.put(('current', (0,)))
        app.drain_output()
        self.assertIsNone(app.active_run_id)
        ended = app.nvidia_execution_status.configure.call_args
        app.output.put(('current', evaluated))
        app.drain_output()
        self.assertEqual(app.nvidia_execution_status.configure.call_args, ended)
        self.assertIn('Partida encerrada', ended.kwargs['text'])

    def test_closed_gui_still_records_without_queueing_ui_output(self):
        with tempfile.TemporaryDirectory() as folder:
            app = launcher.Launcher.__new__(launcher.Launcher)
            app.output = queue.Queue()
            closed = threading.Event()
            closed.set()
            app.read_output(process(b'after GUI closed\n'), Path(folder), {'pipeline':'renderer'}, closed)
            self.assertTrue(app.output.empty())
            self.assertIn('after GUI closed', (Path(folder)/'last_run.log').read_text())

    def test_shortcut_and_gui_record_same_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = {**launcher.APP_DEFAULTS, 'user_dir':folder}
            diagnostics = {'runtime_sha256':'test hash', 'profile':{'pipeline':'renderer'}}
            with mock.patch.object(launcher, 'attach_stdio'), \
                 mock.patch.object(control, 'running_game', return_value=False), \
                 mock.patch.object(launcher, 'game_environment', return_value={'GOW3_PROBE':'test'}), \
                 mock.patch.object(launcher, 'launch_diagnostics', return_value=diagnostics), \
                 mock.patch.object(launcher.subprocess, 'Popen', return_value=process()), \
                 mock.patch.object(launcher.sys, 'stdout', io.StringIO()):
                self.assertEqual(launcher.play_without_window(settings), 0)
            shortcut = (Path(folder)/'last_run.log').read_text()
            app = launcher.Launcher.__new__(launcher.Launcher)
            app.output = queue.Queue()
            app.read_output(process(), Path(folder), diagnostics)
            self.assertEqual((Path(folder)/'last_run.log').read_text(), shortcut)

    def test_overlay_or_ready_camera_is_not_sdk_confirmation(self):
        self.assertIsNone(launcher.runtime_evidence('172 FPS 5.8 ms DLSS'))
        self.assertIsNone(launcher.runtime_evidence('GoW3 input state: camera 1 sample2 invalid'))
        self.assertIsNone(launcher.runtime_evidence('GoW3 native DLSS: selected Performance'))
        self.assertIn('avaliação DLSS confirmada', launcher.runtime_evidence(
            'GoW3 native DLSS: scene 1920x1080 -> output 3840x2160, evaluation 600, camera/depth/jitter native'))
        self.assertIn('fallback', launcher.runtime_evidence('GoW3 temporal input invalid; spatial fallback'))
        self.assertIn('fallback', launcher.runtime_evidence('GoW3 native DLSS: skipped temporal input; last evaluation 600'))


if __name__=='__main__':
    unittest.main()
