"""Upstream replacement/rollback checks in disposable directories, never a live --apply."""
import hashlib
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from paths import ROOT
sys.path.insert(0,str(ROOT/'packaging/windows'))
import upstream_base_upgrade as upgrade
from runtime_provenance import sha256


class BaseUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.stage=self.work/'stage/gow3-windows';self.stage.mkdir(parents=True)
        names=upgrade.REQUIRED|{'_internal/python314.dll','_internal/iced_x86/_iced_x86_py.pyd',
            '_internal/new_module.pyd','scripts/__init__.py','bin/SDL3.dll',
            'patches/God_of_War_III_Remastered.xml'}
        self.data={name:(b'' if name=='scripts/__init__.py' else b'new upstream fixture') for name in names}
        self.protected={'Game/game.pkg','user/savedata/save.bin','gow3.ini','settings.json',
                        'launcher/gow3_launcher_dlss.py','bin-native-dlss/gow3-probe.exe',
                        'bin-native-effects/winmm.dll','bin-dlss5/OptiScaler.ini',
                        'bin/gow3_dlss.dll','bin/nvngx_dlss.dll','patches/optiscaler/LICENSE'}
        self.data.update({name:b'never update player or NVIDIA file' for name in self.protected})
        for name,data in self.data.items():self.put(self.stage,name,data)
        self.archive=self.work/'upstream.zip'
        with zipfile.ZipFile(self.archive,'w') as archive:
            for name,data in self.data.items():archive.writestr('gow3-windows/'+name,data)
        self.recipe={'upstream_tag':'windows-v2.1.8','upstream_commit':'a'*40,
                     'package_script_sha256':'b'*64,'status':'fixture documented recipe'}
        self.manifest_path=self.stage.parent/'upstream-base-manifest.json'
        manifest=upgrade.prepare_manifest(self.stage,self.archive,sha256(self.archive),self.recipe)
        self.manifest_path.write_text(json.dumps(manifest))
        self.receipt={'upstream_base_manifest_sha256':sha256(self.manifest_path)}
        self.plan=upgrade.verified_plan(self.stage,self.receipt)

    def put(self,root,name,data):
        file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)

    def old_port(self):
        port=self.work/'installed';port.mkdir()
        for entry in self.plan['files']:self.put(port,entry['path'],b'original base fixture')
        self.put(port,'_internal/stale_module.pyd',b'obsolete shadowing module')
        for name in self.protected:self.put(port,name,b'preserved original data')
        return port

    def test_complete_frozen_base_and_isa_dependency_selected_protected_paths_excluded(self):
        names={entry['path'] for entry in self.plan['files']}
        self.assertTrue(upgrade.REQUIRED<=names)
        self.assertIn('_internal/iced_x86/_iced_x86_py.pyd',names)
        self.assertFalse(names&self.protected)
        with self.assertRaises(ValueError):upgrade.allowed_base('../outside.exe')

    def test_backups_precede_update_and_old_frozen_modules_do_not_survive(self):
        port=self.old_port();backup=self.work/'backup'
        upgrade.install_base(self.stage,port,backup,self.plan)
        self.assertEqual((backup/'God of War III.exe').read_bytes(),b'original base fixture')
        self.assertEqual((backup/'_internal/stale_module.pyd').read_bytes(),b'obsolete shadowing module')
        self.assertFalse((port/'_internal/stale_module.pyd').exists())
        self.assertEqual((port/'God of War III.exe').read_bytes(),b'new upstream fixture')
        for name in self.protected:self.assertEqual((port/name).read_bytes(),b'preserved original data',name)

    def test_midcopy_failure_restores_old_root_and_frozen_environment(self):
        port=self.old_port();backup=self.work/'backup';copy=upgrade.shutil.copy2
        def fail_new(src,dst,*args,**kwargs):
            if Path(src)==self.stage/'God of War III.exe':raise OSError('fixture interrupted copy')
            return copy(src,dst,*args,**kwargs)
        with mock.patch.object(upgrade.shutil,'copy2',side_effect=fail_new),self.assertRaisesRegex(OSError,'interrupted'):
            upgrade.install_base(self.stage,port,backup,self.plan)
        self.assertEqual((port/'God of War III.exe').read_bytes(),b'original base fixture')
        self.assertEqual((port/'_internal/stale_module.pyd').read_bytes(),b'obsolete shadowing module')
        for name in self.protected:self.assertEqual((port/name).read_bytes(),b'preserved original data',name)

    def test_hash_mismatch_incomplete_stage_and_changed_manifest_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'verified archive hash'):
            upgrade.prepare_manifest(self.stage,self.archive,'0'*64,self.recipe)
        old=(self.stage/'run.py').read_bytes();(self.stage/'run.py').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError,'changed after'):
            upgrade.verified_plan(self.stage,self.receipt)
        (self.stage/'run.py').write_bytes(old)
        (self.stage/'_internal/iced_x86/_iced_x86_py.pyd').unlink()
        with self.assertRaisesRegex(ValueError,'iced_x86'):
            upgrade.inventory(self.stage)
        self.manifest_path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'manifest does not match'):
            upgrade.verified_plan(self.stage,self.receipt)

    def test_parent_full_inventory_without_sizes_is_filtered_and_verified(self):
        manifest={'tag':'windows-v2.1.8','archive_sha256':sha256(self.archive),
                  'packaging_recipe':self.recipe,'files':[{'path':name,'sha256':hashlib.sha256(data).hexdigest()}
                                                       for name,data in self.data.items()]}
        self.manifest_path.write_text(json.dumps(manifest))
        plan=upgrade.verified_plan(self.stage,{'upstream_base_manifest_sha256':sha256(self.manifest_path)})
        self.assertEqual(plan['files'],self.plan['files'])

    def test_optional_private_installer_dry_run_includes_base_plan_without_applying(self):
        installer=ROOT.parent/'install-verified-crash-fixes.py'
        if not installer.is_file():self.skipTest('Private installer not shipped in public source')
        from test_runtime_provenance import RECIPE
        identity={'source_commit':'a'*40,'upstream_commit':'b'*40,'upstream_tag':'windows-v2.1.8',
            'source_dirty':True,'tracked_source_diff_sha256':'c'*64,'untracked_source_sha256':'d'*64,
            'source_tree_sha256':'e'*64,'build_recipe':RECIPE,'probe_sha256':hashlib.sha256(b'fake probe').hexdigest()}
        opti={'upstream_commit':'f'*40,'upstream_archive_sha256':'1'*64,'overlay_sha256':'2'*64,
              'source_tree_sha256':'3'*64,'build_recipe':RECIPE}
        pure=self.work/'pure';effects=self.work/'effects'
        self.put(pure,'gow3-probe.exe',b'fake probe');self.put(effects,'gow3-probe.exe',b'fake probe')
        self.put(effects,'winmm.dll',b'fake proxy')
        self.put(pure,'source-manifest.json',json.dumps(identity).encode())
        proxy_hash=sha256(effects/'winmm.dll')
        self.put(effects,'source-manifest.json',json.dumps({**identity,'optiscaler_sha256':proxy_hash,'optiscaler_source':opti}).encode())
        receipt={**self.receipt,'native_sr_gameplay':True,'native_nr_after_sr':False,
                 'probe_sha256':identity['probe_sha256'],'optiscaler_sha256':proxy_hash,
                 'source_manifest_sha256':sha256(pure/'source-manifest.json'),
                 'effects_source_manifest_sha256':sha256(effects/'source-manifest.json')}
        receipt_path=self.work/'receipt.json';receipt_path.write_text(json.dumps(receipt))
        copied=self.work/'install-verified-crash-fixes.py';shutil.copy2(installer,copied)
        modules=self.work/'gow3-publish/packaging/windows';modules.mkdir(parents=True)
        for name in ('runtime_provenance.py','publication_policy.py','upstream_base_upgrade.py'):
            shutil.copy2(ROOT/'packaging/windows'/name,modules/name)
        result=subprocess.run([sys.executable,str(copied),'--receipt',str(receipt_path),
            '--native-runtime',str(pure),'--effects',str(effects),'--upstream-stage',str(self.stage),
            '--upstream-manifest',str(self.manifest_path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'Optional base dry-run fixture must validate')
        plan=json.loads(result.stdout)
        self.assertEqual(plan['upstream_base_upgrade']['upstream_tag'],'windows-v2.1.8')
        self.assertNotIn('backup',plan)
        self.assertFalse((self.work/'installed').exists())


if __name__=='__main__':unittest.main()
