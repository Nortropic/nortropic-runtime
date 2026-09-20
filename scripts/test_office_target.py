"""AP04 transition checks: real Git inputs, native sandbox, counted remote gates."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import run, candidate, task, targets, inspection
from runtime.integration import Publisher, GateClosed, digest
from runtime.profile import ROOT, sandbox_command, environment
from scripts.test_integration import fixture, CountedPublisher


class OfficeTests(unittest.TestCase):
    def test_named_target_scope_and_active_entry(self):
        value={'id':'office-test','target':targets.OFFICE,'base':'a'*40,
               'allowed_paths':['tools/kontor_result.py'],'attempt_seconds':120,
               'automatic_retries':0,'steps':[{'provider':'codex','prompt':'bounded'}],
               'acceptance_sha256':'b'*64,'runtime_revision':'c'*40}
        self.assertEqual(task.validate(value),value)
        for change in ({'target':'other/repo'},{'allowed_paths':['tools/kontor.py']},
                       {'allowed_paths':['acceptance/x.py']},{'allowed_paths':['tools/../escape']},
                       {'runtime_revision':'main'}):
            with self.subTest(change=change), self.assertRaises(ValueError):task.validate({**value,**change})
        with self.assertRaises(ValueError):targets.repository('https://example.invalid/repo')

    def test_input_binds_project_and_runtime_and_freezes_office_base(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            root=Path(directory); runtime=root/'runtime'; office=root/'office'; state=root/'state'; evidence=root/'evidence'
            for repo,name in ((runtime,targets.RUNTIME),(office,targets.OFFICE)):
                repo.mkdir();candidate.git(repo,'init','-q');candidate.git(repo,'config','user.name','Test');candidate.git(repo,'config','user.email','test@invalid.example')
                candidate.git(repo,'remote','add','origin',targets.origin(name))
                (repo/'AGENTS.md').write_text('immutable instructions')
                candidate.git(repo,'add','.');candidate.git(repo,'commit','-qm','base')
            (office/'tasks').mkdir();(office/'acceptance').mkdir()
            verifier=b'def verify(path): return {"passed": True}\n'
            (office/'acceptance/test.py').write_bytes(verifier);(office/'tasks/test.md').write_text('office work')
            accepted={'id':'office-test','target':targets.OFFICE,'base':candidate.git(office,'rev-parse','HEAD'),
                      'allowed_paths':['tools/kontor_result.py'],'attempt_seconds':120,'automatic_retries':0,
                      'steps':[{'provider':'codex','prompt':'bounded'}], 'runtime_revision':candidate.git(runtime,'rev-parse','HEAD'),
                      'acceptance':'acceptance/test.py','brief':'tasks/test.md','acceptance_sha256':hashlib.sha256(verifier).hexdigest()}
            path=office/'tasks/test.json';path.write_text(json.dumps(accepted))
            candidate.git(office,'add','.');candidate.git(office,'commit','-qm','accepted input')
            def repo(target):return {targets.OFFICE:office,targets.RUNTIME:runtime}[target]
            with patch.object(run,'ROOT',runtime),patch.object(run,'repository',side_effect=repo),patch.object(run,'task_directory',return_value=state),patch.object(run,'evidence_directory',return_value=evidence),patch.object(run,'check_unfinished_writers'):
                self.assertEqual(run.read_input(path)[0],accepted)
                run.prepare(path)
                self.assertEqual(candidate.git(state/'candidate','rev-parse','HEAD'),accepted['base'])
                manifest=json.loads((evidence/'accepted.json').read_text())
                self.assertEqual(manifest['input_source'],candidate.git(office,'rev-parse','HEAD'))
                self.assertEqual(manifest['runtime_source'],accepted['runtime_revision'])
                self.assertEqual((state/'acceptance.py').read_bytes(),verifier)
                with self.assertRaisesRegex(ValueError,'already exists'):run.prepare(path)
                (office/'acceptance/test.py').write_text('changed')
                with self.assertRaises(ValueError):run.read_input(path)
                candidate.git(office,'checkout','--','acceptance/test.py')
                bad={**accepted,'target':targets.RUNTIME};path.write_text(json.dumps(bad));candidate.git(office,'commit','-am','wrong target','-q')
                with self.assertRaisesRegex(ValueError,'differs from input'):run.read_input(path)
            source=state/'candidate';(source/'tools/kontor_result.py').write_text('result implementation')
            with patch.object(candidate,'repository',side_effect=repo),patch.object(candidate,'task_directory',return_value=state):
                result=candidate.prepare(accepted,1,source)
            frozen=state/result['workspace_name']
            self.assertEqual(candidate.git(frozen,'remote','get-url','origin'),targets.origin(targets.OFFICE))
            self.assertEqual(candidate.git(frozen,'rev-parse','HEAD^'),accepted['base'])
            with self.assertRaises(GateClosed):Publisher(frozen).inspect_candidate(accepted,{'base':accepted['base'],'candidate':result['candidate']})
            Publisher(frozen,targets.OFFICE).inspect_candidate(accepted,{'base':accepted['base'],'candidate':result['candidate']})

    def test_new_target_negative_publication_gates(self):
        for mutation in ('review','base','cross_target'):
            values=list(fixture());values[0]['target']=targets.OFFICE
            for i in (1,2,3):values[i]['task_sha256']=digest(values[0])
            publisher=CountedPublisher()
            if mutation=='review':values[3]['verdict']='inconclusive'
            elif mutation=='base':publisher.changed_base_at=1
            else:values[0]['target']='other/repo'
            with self.assertRaises(GateClosed):publisher.publish(*values)
            self.assertEqual(publisher.mutations,[])

    def test_native_exact_file_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            root=Path(directory);ws=root/'candidate';(ws/'tools').mkdir(parents=True);(ws/'.scratch').mkdir()
            for name in ('AGENTS.md','tools/kontor.py','tools/kontor_result.py'):(ws/name).write_text('unchanged')
            outside=root/'acceptance.py';outside.write_text('host authority')
            (ws/'tools/escape').symlink_to(outside)
            code='''from pathlib import Path
import json
out={}
Path('tools/kontor_result.py').write_text('allowed')
for name in ['AGENTS.md','tools/kontor.py','tools/new.py','tools/escape',OUTSIDE]:
 try: Path(name).write_text('escape');out[name]=False
 except PermissionError: out[name]=True
print(json.dumps(list(out.values())))
'''.replace('OUTSIDE',repr(str(outside)))
            result=subprocess.run(sandbox_command(ws,['/opt/homebrew/bin/python3.12','-c',code],writable=True,allowed_paths=['tools/kontor_result.py']),env=environment(),capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),[True]*5)
            self.assertEqual(outside.read_text(),'host authority')
            self.assertEqual((ws/'tools/kontor_result.py').read_text(),'allowed')

    def test_inspection_missing_is_read_only_and_unavailable(self):
        with patch.object(inspection,'load',side_effect=ValueError('Missing frozen input')),patch('subprocess.Popen',side_effect=AssertionError('No processes')):
            report=inspection.inspect('office-test')
            self.assertEqual(report['observation'],'unavailable')
            self.assertFalse(report['verified_delivery'])

    def test_inspection_cross_checks_completed_receipts_without_effects(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            root=Path(directory);state=root/'state';state.mkdir();evidence=root/'evidence';evidence.mkdir()
            value,subject,tests,review=fixture();value['target']=targets.OFFICE
            verifier=b'host verifier';brief=b'accepted brief'
            value['acceptance_sha256']=hashlib.sha256(verifier).hexdigest()
            for item in (subject,tests,review):
                item['task_sha256']=digest(value);item['acceptance_sha256']=value['acceptance_sha256']
            (state/'acceptance.py').write_bytes(verifier);(state/'brief.md').write_bytes(brief)
            def write(name,value):
                path=evidence/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
            manifest={'task':value,'task_sha256':digest(value),'runtime_source':'d'*40,'input_source':'e'*40,'brief_sha256':hashlib.sha256(brief).hexdigest()}
            write('accepted.json',manifest)
            integration={'merged':True,'candidate':subject['candidate'],'merge_commit':'c'*40,'tree':'d'*40,'url':'https://github.com/'+targets.OFFICE+'/pull/1'}
            native={'phase':'completed','results':[{'attempt':1,'candidate':subject['candidate'],'thread_id':'author-thread'}],'review':review,'integration':integration}
            write('state.json',native);write('integration.json',integration);write('review-1/decision.json',review)
            hashes={'tools/value.txt':'f'*64}
            write('attempt-1/acceptance.json',{'passed':True,'candidate_files_sha256':hashes})
            frozen={'candidate':subject['candidate'],'base':value['base'],'task_sha256':digest(value),'candidate_files_sha256':hashes}
            write('attempt-1/candidate.json',frozen)
            def snapshot():return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
            with patch.object(inspection,'load',return_value=value),patch.object(inspection,'task_directory',return_value=state),patch.object(inspection,'evidence_directory',return_value=evidence),patch.object(inspection,'ROOT',root),patch('subprocess.Popen',side_effect=AssertionError('No processes')):
                before=snapshot();report=inspection.inspect(value['id'])
                self.assertTrue(report['verified_delivery'],report);self.assertFalse(report['live']);self.assertFalse(report['remote_current'])
                self.assertEqual(before,snapshot())
                for name,invalid in [('integration.json',{**integration,'candidate':'a'*40}),('review-1/decision.json',{}),('attempt-1/acceptance.json',{'passed':False}),('accepted.json',{**manifest,'task_sha256':'0'*64})]:
                    path=evidence/name;original=path.read_bytes();write(name,invalid)
                    self.assertFalse(inspection.inspect(value['id'])['verified_delivery'],name)
                    path.write_bytes(original)
                (state/'acceptance.py').write_bytes(b'changed')
                self.assertFalse(inspection.inspect(value['id'])['verified_delivery'])
