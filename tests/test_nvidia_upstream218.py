"""Upstream 2.1.8 behaviors on the NVIDIA entry, without a live game/runtime."""
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from paths import ROOT
sys.path.insert(0,str(ROOT/'launcher'))
import gow3_launcher_dlss as launcher
import gow3_dlss_control as control
import test_launcher_game_files as upstream_dump_tests
from gow3_redesign import PlayButton


class NvidiaUpstream218Test(unittest.TestCase):
    def test_upstream_dump_repair_and_validation_cases_on_nvidia_helpers(self):
        result=unittest.TestResult()
        suite=unittest.defaultTestLoader.loadTestsFromModule(upstream_dump_tests)
        # Upstream fixtures use ttk's state query; our themed canvas tracks the same state explicitly.
        with mock.patch.object(upstream_dump_tests,'launcher',launcher), mock.patch.object(
                PlayButton,'instate',lambda button,states: button.disabled if 'disabled' in states else not button.disabled,create=True):
            suite.run(result)
        self.assertGreaterEqual(result.testsRun,2)
        self.assertTrue(result.wasSuccessful(),str(result.errors)+str(result.failures))

    def test_no_msaa_environment_automatic_clears_inherited_override(self):
        settings={**launcher.APP_DEFAULTS,'nvidia_mode':'off','dlssg_mode':'off','dlss5_enabled':False}
        for option in ('','0','1'):
            with self.subTest(option=option),mock.patch.dict(os.environ,{'GOW3_NO_MSAA':'1'},clear=True):
                env=launcher.game_environment({**settings,'no_msaa':option})
                if option: self.assertEqual(env['GOW3_NO_MSAA'],option)
                else: self.assertFalse('GOW3_NO_MSAA' in env,'Automatic MSAA must clear the inherited override')
                self.assertEqual(env['PYTHONIOENCODING'],'utf-8')

    def test_extended_gpu_rows_and_default_gpu_are_accepted_by_nvidia_helper(self):
        data='0\tAMD Radeon\tdiscrete\toff\t0\n1\tNVIDIA GeForce RTX 5070\tdiscrete\ton\t1\n'
        with mock.patch.object(control.subprocess,'run',return_value=SimpleNamespace(stdout=data)):
            control.gpu_name.cache_clear()
            self.assertEqual(control.gpu_name('fixture-only'),'NVIDIA GeForce RTX 5070')
            self.assertEqual(control.gpu_name('fixture-only','0'),'AMD Radeon')
        control.gpu_name.cache_clear()

    def test_invalid_log_path_still_consumes_output_and_preserves_exit(self):
        messages=[];proc=SimpleNamespace(stdout=io.BytesIO(b'continues\n'),wait=lambda:7)
        with tempfile.TemporaryDirectory() as folder:
            code=launcher.record_game_output(proc,Path(folder)/'invalid\0folder',messages.append)
        self.assertEqual(code,7)
        self.assertIn('continues\n',messages)
        self.assertTrue(any('Could not save' in text for text in messages))


if __name__=='__main__':unittest.main()
