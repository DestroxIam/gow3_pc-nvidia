"""Freeze failures are fatal even when PyInstaller reports exit zero; no build in tests."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from paths import ROOT
spec=importlib.util.spec_from_file_location('nvidia_freezer',ROOT/'packaging/windows/build-nvidia-launcher.py')
freezer=importlib.util.module_from_spec(spec);spec.loader.exec_module(freezer)
sys.path.insert(0,str(ROOT/'packaging/windows'))
from frozen_probe import code_signature


class FreezeTest(unittest.TestCase):
    def test_missing_hard_import_fails_before_native_checks_or_freeze(self):
        with mock.patch.object(freezer.importlib.util,'find_spec',return_value=None), \
             mock.patch.object(freezer.importlib,'import_module') as imports:
            with self.assertRaisesRegex(RuntimeError,'graphics_options'):
                freezer.preflight(('graphics_options',))
            imports.assert_not_called()

    def test_native_extension_load_failure_is_fatal(self):
        with mock.patch.object(freezer.importlib.util,'find_spec',return_value=object()), \
             mock.patch.object(freezer.importlib,'import_module',side_effect=OSError('fixture missing native DLL')):
            with self.assertRaisesRegex(RuntimeError,'native/standard import failed'):
                freezer.preflight(())

    def test_pyinstaller_hidden_import_error_is_fatal_even_with_exit_zero(self):
        result=SimpleNamespace(returncode=0,stdout='',stderr='101 ERROR: Hidden import "iced_x86" not found!')
        with mock.patch.object(freezer.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(RuntimeError,'exit 0'):
                freezer.checked_pyinstaller(['fixture-only'],{})

    def test_source_signatures_ignore_relocation_and_set_order_but_detect_code_change(self):
        source='OPTIONS={"quality","performance","balanced"}\ndef f(): return 2\n'
        self.assertEqual(code_signature(compile(source,'original.py','exec')),
                         code_signature(compile(source,'_internal/relocated.py','exec')))
        self.assertNotEqual(code_signature(compile(source,'original.py','exec')),
                            code_signature(compile(source.replace('return 2','return 3'),'original.py','exec')))


if __name__=='__main__':unittest.main()
