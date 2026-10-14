"""Publication checks use disposable dummy source/runtime files, never installed DLLs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from paths import ROOT
PACKAGING=ROOT/'packaging/windows'
sys.path.insert(0,str(PACKAGING))
from publication_policy import allowed_publication, allowed_source, renderer_sync_report, fsr_recipe_report
from runtime_provenance import sha256, json_digest
spec=importlib.util.spec_from_file_location('optiscaler_source_package',PACKAGING/'package-optiscaler-source.py')
source_package=importlib.util.module_from_spec(spec);spec.loader.exec_module(source_package)


class SourcePackageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.source=self.work/'source';self.source.mkdir()
        self.upstream=self.work/'pinned.zip'
        with zipfile.ZipFile(self.upstream,'w') as archive:
            for name,data in {'LICENSE':b'GPL fixture','OptiScaler/native/VirtualUpscalerDriver.cpp':b'old',
                'OptiScaler/include/imgui/imgui_impl_vulkan.cpp':b'old backend',
                'external/vendor/LICENSE.txt':b'vendor notice','external/vendor/sdk.lib':b'pinned SDK input',
                'external/vendor/lib/x64/sdk.lib':b'pinned x64 SDK input',
                'OptiScaler/shaders/example.spv':b'pinned shader input'}.items():
                archive.writestr(source_package.UPSTREAM_ROOT+'/'+name,data)

    def put(self,name,data=b'fixture source'):
        file=self.source/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)

    def test_all_new_fixes_backend_project_tests_and_docs_are_archived(self):
        names=['OptiScaler/native/VirtualUpscalerDriver.cpp','OptiScaler/include/imgui/imgui_impl_vulkan.cpp',
               'external/imgui/backends/imgui_impl_dx12.cpp','OptiScaler/OptiScaler.vcxproj',
               'tests/imgui_mapped_range_cpu.cpp','tests/build_imgui_mapped_range_cpu.cmd',
               'docs/GOW3-ON12-INPUT-CONTRACT.md','tests/private-native-nr/02-on12-nr-after.ini']
        names += [f'OptiScaler/dlssnr/NewFix{n}.h' for n in range(24)]
        for name in names:self.put(name)
        output=self.work/'corresponding.zip'
        manifest=source_package.package_source(self.upstream,self.source,output)
        self.assertEqual({entry['path'] for entry in manifest['overlay']},set(names))
        with zipfile.ZipFile(output) as archive:
            for name in names:self.assertEqual(archive.read(source_package.PREFIX+name),b'fixture source')
            self.assertIn(source_package.PREFIX+'external/vendor/sdk.lib',archive.namelist())
            self.assertIn(source_package.PREFIX+'external/vendor/lib/x64/sdk.lib',archive.namelist())
            self.assertIn(source_package.PREFIX+'OptiScaler/shaders/example.spv',archive.namelist())
            self.assertIn(source_package.PREFIX+'GOW3-SOURCE-MANIFEST.json',archive.namelist())
        self.assertEqual(manifest['archive_sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertTrue(output.with_name(output.name+'.sha256').exists())

    def test_models_game_logs_backups_and_build_outputs_are_never_copied(self):
        blocked=['OptiScaler/nvngx_dlssnr.dll','OptiScaler/nvngx_dlssnr_310.dll','tests/game.pkg',
                 'tests/run.log','OptiScaler/x64/Release/fix.cpp','tests/probe.exe','tests/model.onnx',
                 'tests/image.raw','tests/cached.obj','OptiScaler/native/fix.cpp.original',
                 'OptiScaler/resource_build_date.h','tests/source-manifest.bin','Game/eboot.bin']
        for name in blocked:self.put(name,b'must not ship')
        self.put('OptiScaler/dlssnr/fix.cpp')
        files,manifest=source_package.collect_source(self.upstream,self.source)
        for name in blocked:self.assertNotIn(name,files)
        self.assertEqual([entry['path'] for entry in manifest['overlay']],['OptiScaler/dlssnr/fix.cpp'])

    def test_unsafe_archive_path_fails_before_output(self):
        with zipfile.ZipFile(self.upstream,'a') as archive:
            archive.writestr(source_package.UPSTREAM_ROOT+'/../outside.cpp','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            source_package.collect_source(self.upstream,self.source)

    def test_checksums_preserve_binary_entry_and_replace_source_entry(self):
        sums=self.work/'SHA256SUMS.txt';sums.write_text('binaryhash  preview.zip\noldhash  source.zip\n')
        output=self.work/'source.zip'
        manifest=source_package.package_source(self.upstream,self.source,output,sums)
        self.assertEqual(sums.read_text().splitlines(),['binaryhash  preview.zip',manifest['archive_sha256']+'  source.zip'])

    def test_audit_only_creates_no_archive(self):
        target=self.work/'must-not-exist.zip'
        result=subprocess.run([sys.executable,str(PACKAGING/'package-optiscaler-source.py'),
            '--upstream-zip',str(self.upstream),'--source',str(self.source),'--output',str(target),'--audit-only'],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(target.exists());self.assertFalse(target.with_suffix('.audit.json').exists())

    def test_full_overlay_digest_and_actual_recipe_change_with_backend_source(self):
        recipe={'commands':[['msbuild','OptiScaler/OptiScaler.vcxproj','/p:Configuration=Release','/p:Platform=x64']],
                'toolchain':{'compiler':'fixture MSVC 14.44','sdk':'fixture 10.0.26100.0'}}
        self.put('OptiScaler/include/imgui/imgui_impl_vulkan.cpp',b'backend fix one')
        _,first=source_package.collect_source(self.upstream,self.source,recipe)
        self.assertEqual(first['build_recipe'],recipe)
        self.assertEqual(first['overlay_sha256'],json_digest(first['overlay']))
        self.put('OptiScaler/include/imgui/imgui_impl_vulkan.cpp',b'backend fix two')
        self.put('OptiScaler/dlssnr/queue_lifecycle.cpp',b'new lifecycle fix')
        _,second=source_package.collect_source(self.upstream,self.source,recipe)
        self.assertNotEqual(first['overlay_sha256'],second['overlay_sha256'])
        self.assertNotEqual(first['source_tree_sha256'],second['source_tree_sha256'])


class PublicationPolicyTest(unittest.TestCase):
    def test_clean_dependency_plus_declared_patch_matches_parent_without_mutating_either_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);public=root/'public';parent=root/'parent'
            child='gpu/third_party/fsr-vulkan';source=parent/child;source.mkdir(parents=True)
            def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],stderr=subprocess.PIPE)
            git(source,'init','--quiet');(source/'provider.c').write_bytes(b'original\n')
            git(source,'add','.');git(source,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                                      'commit','--quiet','-m','fixture')
            target=public/child;target.parent.mkdir(parents=True)
            subprocess.run(['git','clone','--quiet',str(source),str(target)],check=True,capture_output=True)
            (source/'provider.c').write_bytes(b'compiled dependency fix\n')
            patch=public/'gpu/patches/fsr-vulkan/0001-fixture.patch';patch.parent.mkdir(parents=True)
            patch.write_bytes(git(source,'diff').replace(b'\n',b'\r\n'))
            indexes=[path/'.git/index' for path in (source,target)]
            before=[path.read_bytes() for path in indexes]
            result=fsr_recipe_report(public,parent)
            self.assertTrue(result['matched'])
            self.assertEqual([path.read_bytes() for path in indexes],before)
            self.assertEqual((target/'provider.c').read_bytes().replace(b'\r\n',b'\n'),b'original\n')
            self.assertEqual((source/'provider.c').read_bytes(),b'compiled dependency fix\n')
            (source/'provider.c').write_bytes(b'fix missing from declared patch\n')
            self.assertFalse(fsr_recipe_report(public,parent)['matched'])
            (source/'provider.c').write_bytes(b'compiled dependency fix\n')
            (target/'provider.c').write_bytes(b'unrecorded public dependency change\n')
            self.assertFalse(fsr_recipe_report(public,parent)['matched'])

    def test_runtime_models_and_player_state_excluded_forwarder_allowed(self):
        for name in ('OptiScaler/nvngx_dlssnr.dll','OptiScaler/nvngx_dlssnr_310.dll','user/last_run.log',
                     'Game/game.iso','OptiScaler/weights.safetensors','OptiScaler/model.bin','logs/private.txt'):
            self.assertFalse(allowed_publication(name),name)
        self.assertTrue(allowed_publication('OptiScaler/nvngx.dll_dlssnr.dll'))
        self.assertTrue(allowed_source('OptiScaler/include/imgui/imgui_impl_vulkan.cpp'))
        self.assertTrue(allowed_source('external/imgui/backends/imgui_impl_dx12.cpp'))

    def test_renderer_cpp_headers_and_shaders_must_be_synced_without_copying(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);parent=base/'parent';public=base/'public'
            names=['gpu/shadps4/video_core/renderer_vulkan/new.cpp','gpu/shim/new.h',
                   'gpu/shadps4/video_core/renderer_vulkan/shaders/new.comp','tests/test_new.cpp',
                   'gpu/shadps4/CMakeLists.txt','gpu/shadps4/core/libraries/avplayer/new.cpp',
                   'src/new_runtime.c','gpu/third_party/fsr-vulkan/src/new_provider.c']
            for name in names:
                file=parent/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('new source')
            result=renderer_sync_report(public,parent)
            self.assertFalse(result['matched']);self.assertEqual(set(result['mismatches']),set(names))
            self.assertFalse(public.exists())
            for name in names:
                file=public/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('new source')
            self.assertTrue(renderer_sync_report(public,parent)['matched'])


class PortablePackageTest(unittest.TestCase):
    def test_explicit_effects_candidate_and_model_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);root=work/'public';normal=work/'normal';native=work/'native';effects=work/'effects';out=work/'out'
            def put(base,name,data=b'fixture'):
                file=base/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
            for name in ('run.py','LICENSE','README.md','README.pt-BR.md','CHANGELOG.md','patches/optiscaler/LICENSE',
                         'Game/README.md','Game/.gitkeep','docs/NVIDIA.md'):
                put(root,name)
            put(root,'out/nvidia-launcher-dist/God of War III/God of War III.exe')
            put(root,'Game/other-game.dat',b'exclude');put(root,'docs/run.log',b'exclude')
            put(native,'gow3-probe.exe',b'new probe')
            for base,proxy in ((normal/'bin-dlss5',b'old proxy'),(effects,b'new validated proxy')):
                put(base,'winmm.dll',proxy);put(base,'gow3-probe.exe',b'new probe')
                put(base,'OptiScaler.ini',b'[DlssNr]\nEnabled=true\n')
                put(base,'OptiScaler/nvngx_dlssnr.dll',b'proprietary model excluded')
                put(base,'OptiScaler/nvngx.dll_dlssnr.dll',b'forwarder')
            marker={'native_nr_after_sr':True,'native_nr_fg_tested_multipliers':[2,6],'probe_sha256':hashlib.sha256(b'new probe').hexdigest(),
                    'optiscaler_sha256':hashlib.sha256(b'new validated proxy').hexdigest()}
            put(effects,'renderer-build.json',json.dumps(marker).encode())
            recipe={'commands':[['cmake','--build','out/native']],'toolchain':{'compiler':'fixture compiler 1.0'}}
            identity={'source_commit':'a'*40,'upstream_commit':'b'*40,'upstream_tag':'windows-v2.1.8',
                'source_dirty':True,'tracked_source_diff_sha256':'c'*64,'untracked_source_sha256':'d'*64,
                'source_tree_sha256':'e'*64,'build_recipe':recipe,'probe_sha256':marker['probe_sha256']}
            put(native,'source-manifest.json',json.dumps(identity).encode())
            opti={'upstream_commit':source_package.UPSTREAM_COMMIT,'upstream_archive_sha256':'f'*64,
                'overlay_sha256':'1'*64,'source_tree_sha256':'2'*64,'build_recipe':recipe}
            effects_identity={**identity,'optiscaler_sha256':marker['optiscaler_sha256'],'optiscaler_source':opti}
            put(effects,'source-manifest.json',json.dumps(effects_identity).encode())
            receipt={'native_sr_gameplay':True,'native_nr_after_sr':True,'native_nr_fg_tested_multipliers':[2],
                **{key:marker[key] for key in ('probe_sha256','optiscaler_sha256')},
                'source_manifest_sha256':sha256(native/'source-manifest.json'),
                'effects_source_manifest_sha256':sha256(effects/'source-manifest.json')}
            receipt_path=work/'receipt.json';receipt_path.write_text(json.dumps(receipt))
            upstream=work/'base.zip'
            with zipfile.ZipFile(upstream,'w') as archive:archive.writestr('gow3-windows/bin/gow3-probe.exe',b'original')
            command=[sys.executable,str(PACKAGING/'package-nvidia-preview.py'),'--source-root',str(root),
                '--base-zip',str(upstream),'--runtime-root',str(normal),'--native-runtime',str(native),
                '--native-effects-runtime',str(effects),'--receipt',str(receipt_path),'--output',str(out)]
            out.mkdir();(out/'SHA256SUMS.txt').write_text('sourcehash  corresponding-source.zip\n')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            stage=out/'gow3-windows-nvidia'
            self.assertEqual((stage/'bin-native-effects/winmm.dll').read_bytes(),b'new validated proxy')
            staged=json.loads((stage/'bin-native-effects/renderer-build.json').read_text())
            self.assertTrue(staged['native_nr_after_sr'])
            self.assertEqual(staged['native_nr_fg_tested_multipliers'],[2])
            self.assertEqual(staged['source_commit'],identity['source_commit'])
            self.assertEqual(staged['tracked_source_diff_sha256'],identity['tracked_source_diff_sha256'])
            self.assertEqual(staged['optiscaler_source'],opti)
            self.assertFalse((stage/'bin-native-effects/OptiScaler/nvngx_dlssnr.dll').exists())
            self.assertTrue((stage/'bin-native-effects/OptiScaler/nvngx.dll_dlssnr.dll').exists())
            self.assertFalse((stage/'Game/other-game.dat').exists())
            self.assertFalse((stage/'docs/run.log').exists())
            self.assertIn('sourcehash  corresponding-source.zip',(out/'SHA256SUMS.txt').read_text())
            repeated=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(repeated.returncode,0)
            self.assertIn('fresh output directory',repeated.stderr)
            # Source/receipt proof is required even when the NR capability itself is disabled.
            marker['native_nr_after_sr']=False
            put(effects,'renderer-build.json',json.dumps(marker).encode())
            put(effects,'source-manifest.json',json.dumps({**effects_identity,'source_commit':'9'*40}).encode())
            command[-1]=str(work/'stale-source-output')
            stale=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(stale.returncode,0)
            self.assertIn('manifest does not match',stale.stderr)
            self.assertFalse((work/'stale-source-output').exists())
            put(effects,'source-manifest.json',json.dumps(effects_identity).encode())
            marker['native_nr_after_sr']=True
            marker['probe_sha256']='0'*64
            put(effects,'renderer-build.json',json.dumps(marker).encode())
            command[-1]=str(work/'bad-output')
            rejected=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('hashes do not match',rejected.stderr)
            self.assertFalse((work/'bad-output/gow3-windows-nvidia-preview-1.zip').exists())


if __name__=='__main__':unittest.main()
