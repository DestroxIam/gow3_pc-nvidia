"""Disposable Git trees/binaries only; never installs, copies live files or launches games."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from paths import ROOT
sys.path.insert(0,str(ROOT/'packaging/windows'))
import runtime_provenance as provenance

RECIPE={'commands':[['cmake','-S','.','-B','out/native','-G','Ninja'],
                    ['cmake','--build','out/native']],
        'toolchain':{'compiler':'fixture compiler 1.0','cmake':'fixture 3.0'},
        'configuration':'Release','generator':'Ninja'}


class SourceSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.source=self.work/'source';self.source.mkdir()
        self.git('init','--quiet')
        self.put('src/a.cpp',b'original');self.put('scripts/build.py',b'original')
        self.put('.gitignore',b'out/\n.env*\n')
        self.git('add','.');self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                                    'commit','--quiet','-m','fixture')
        self.git('tag','windows-v2.1.8')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.source),*args],stderr=subprocess.PIPE)

    def put(self,name,data):
        file=self.source/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)

    def snapshot(self):return provenance.source_snapshot(self.source,'windows-v2.1.8',RECIPE)

    def test_all_source_roots_staged_deletion_unstaged_changes_and_new_source(self):
        clean=self.snapshot();self.assertFalse(clean['source_dirty'])
        self.put('src/a.cpp',b'changed outside GPU');self.git('add','src/a.cpp')
        self.git('rm','scripts/build.py')
        self.put('src/a.cpp',b'staged plus unstaged')
        self.put('gpu/new.comp',b'new shader')
        dirty=self.snapshot();self.assertTrue(dirty['source_dirty'])
        self.assertNotEqual(clean['tracked_source_diff_sha256'],dirty['tracked_source_diff_sha256'])
        self.assertNotEqual(clean['untracked_source_sha256'],dirty['untracked_source_sha256'])
        self.assertNotEqual(clean['source_tree_sha256'],dirty['source_tree_sha256'])
        self.put('out/runtime.exe',b'generated');self.put('.env.local',b'fixture-only private settings')
        self.assertEqual(self.snapshot(),dirty)

    def test_unchanged_build_binds_but_midbuild_source_edit_is_rejected(self):
        snapshot=self.snapshot();stage=self.work/'stage';stage.mkdir()
        (stage/'gow3-probe.exe').write_bytes(b'fixture compiled executable')
        manifest=provenance.bind_snapshot(snapshot,self.source,stage)
        self.assertEqual(manifest['probe_sha256'],provenance.sha256(stage/'gow3-probe.exe'))
        self.put('scripts/build.py',b'changed during compile')
        original=(stage/'source-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'changed during'):
            provenance.bind_snapshot(snapshot,self.source,stage)
        self.assertEqual((stage/'source-manifest.json').read_bytes(),original)

    def test_dependency_changes_affect_tree_digest(self):
        dep=self.work/'dependency';dep.mkdir()
        def git(*args):return subprocess.check_output(['git','-C',str(dep),*args],stderr=subprocess.PIPE)
        git('init','--quiet');(dep/'dep.cpp').write_bytes(b'original dependency')
        git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                         'commit','--quiet','-m','dependency')
        self.git('-c','protocol.file.allow=always','submodule','add','--quiet',str(dep),'external/dep')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-am','dependency')
        clean=self.snapshot()
        (self.source/'external/dep/new.h').write_bytes(b'new dependency source')
        changed=self.snapshot()
        self.assertTrue(changed['source_dirty'])
        self.assertNotEqual(clean['source_tree_sha256'],changed['source_tree_sha256'])


class ReceiptBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.pure=self.work/'pure';self.effects=self.work/'effects'
        self.pure.mkdir();self.effects.mkdir()
        self.base={'source_commit':'a'*40,'upstream_commit':'b'*40,'upstream_tag':'windows-v2.1.8',
            'source_dirty':True,'tracked_source_diff_sha256':'c'*64,'untracked_source_sha256':'d'*64,
            'source_tree_sha256':'e'*64,'build_recipe':RECIPE,
            'probe_sha256':hashlib.sha256(b'fixture probe').hexdigest()}
        self.opti={'upstream_commit':'f'*40,'upstream_archive_sha256':'1'*64,'overlay_sha256':'2'*64,
                   'source_tree_sha256':'3'*64,'build_recipe':RECIPE}
        self.effect_manifest={**self.base,'optiscaler_sha256':hashlib.sha256(b'fixture proxy').hexdigest(),
                              'optiscaler_source':self.opti}
        for stage,manifest in [(self.pure,self.base),(self.effects,self.effect_manifest)]:
            (stage/'gow3-probe.exe').write_bytes(b'fixture probe')
            (stage/'source-manifest.json').write_text(json.dumps(manifest))
        (self.effects/'winmm.dll').write_bytes(b'fixture proxy')
        self.receipt={'native_sr_gameplay':True,'native_nr_after_sr':False,
            'probe_sha256':self.base['probe_sha256'],'optiscaler_sha256':self.effect_manifest['optiscaler_sha256'],
            'source_manifest_sha256':provenance.sha256(self.pure/'source-manifest.json'),
            'effects_source_manifest_sha256':provenance.sha256(self.effects/'source-manifest.json')}

    def test_receipt_matches_manifest_and_binaries_without_inventing_provenance(self):
        result=provenance.verified_stage(self.pure,self.receipt)
        self.assertEqual(result['source_commit'],self.base['source_commit'])
        self.assertEqual(result['upstream_tag'],'windows-v2.1.8')
        effects=provenance.verified_stage(self.effects,self.receipt,'effects_source_manifest_sha256',True)
        self.assertEqual(effects['optiscaler_source'],self.opti)

    def test_same_binary_with_changed_source_head_does_not_match_old_receipt(self):
        (self.pure/'source-manifest.json').write_text(json.dumps({**self.base,'source_commit':'9'*40}))
        with self.assertRaisesRegex(ValueError,'manifest does not match'):
            provenance.verified_stage(self.pure,self.receipt)

    def test_missing_proof_and_legacy_incomplete_manifest_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'source_manifest_sha256'):
            provenance.verified_stage(self.pure,{'probe_sha256':self.base['probe_sha256']})
        (self.pure/'source-manifest.json').write_text(json.dumps({'source_commit':'a'*40}))
        self.receipt['source_manifest_sha256']=provenance.sha256(self.pure/'source-manifest.json')
        with self.assertRaisesRegex(ValueError,'upstream_commit'):
            provenance.verified_stage(self.pure,self.receipt)

    def test_mismatched_probe_proxy_and_missing_opti_source_are_rejected(self):
        for name in ('gow3-probe.exe','winmm.dll'):
            with self.subTest(name=name):
                path=self.effects/name;old=path.read_bytes();path.write_bytes(b'untested binary')
                with self.assertRaisesRegex(ValueError,'does not match'):
                    provenance.verified_stage(self.effects,self.receipt,'effects_source_manifest_sha256',True)
                path.write_bytes(old)
        manifest={**self.effect_manifest};manifest.pop('optiscaler_source')
        (self.effects/'source-manifest.json').write_text(json.dumps(manifest))
        self.receipt['effects_source_manifest_sha256']=provenance.sha256(self.effects/'source-manifest.json')
        with self.assertRaisesRegex(ValueError,'optiscaler_source'):
            provenance.verified_stage(self.effects,self.receipt,'effects_source_manifest_sha256',True)

    def test_recipe_private_paths_rejected(self):
        with self.assertRaisesRegex(ValueError,'relative paths'):
            provenance.build_recipe({'commands':[['C:/Users/Fixture/clang.exe','source.cpp']],
                                     'toolchain':{'compiler':'fixture 1.0'}})

    def test_private_installer_dry_run_only_consumes_owned_fixture_stage_and_receipt(self):
        installer=ROOT.parent/'install-verified-crash-fixes.py'
        if not installer.is_file(): self.skipTest('Private installer is not shipped in public source')
        target=self.work/'install-verified-crash-fixes.py';shutil.copy2(installer,target)
        modules=self.work/'gow3-publish/packaging/windows';modules.mkdir(parents=True)
        for name in ('runtime_provenance.py','publication_policy.py','upstream_base_upgrade.py'):
            shutil.copy2(ROOT/'packaging/windows'/name,modules/name)
        receipt_path=self.work/'receipt.json';receipt_path.write_text(json.dumps(self.receipt))
        command=[sys.executable,str(target),'--native-runtime',str(self.pure),'--effects',str(self.effects),
                 '--receipt',str(receipt_path)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'Dry-run fixture must validate')
        plan=json.loads(result.stdout)
        self.assertEqual(plan['runtime_provenance']['bin-native-dlss']['source_commit'],self.base['source_commit'])
        self.assertFalse(plan['native_nr_after_sr'])
        self.assertNotIn('backup',plan)
        (self.effects/'winmm.dll').write_bytes(b'untested proxy')
        failed=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(failed.returncode,0)
        self.assertIn('does not match',failed.stderr)


if __name__=='__main__':unittest.main()
