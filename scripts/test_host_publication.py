"""Actual separate-process boundary, synthetic issuer only; no App or network.

The old issuer's acceptance/transport semantics are covered separately. Here a
small frozen observation double proves import selection, closed task selection,
private adoption and caller receipt checks without credentials or GitHub effects.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime import host_publication as caller
from runtime.integration import Publisher, GateClosed, digest, check_binding

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/host_publication.py'
spec = importlib.util.spec_from_file_location('launcher_source', SOURCE)
launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)


def private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    path.chmod(0o600)


FIXTURE = b'''import json,os
from pathlib import Path
def read_object(path): return json.loads(path.read_bytes())
def binding(task,subject,review): return review['fixture_binding']
class HostIssuer:
    def __init__(self,host):
        self.host=host;self.home=host/'.runtime/ap11/check-issuer'
    def authority(self): return read_object(self.home/'authority.json')
    def request(self,identifier,task,subject,review):
        if identifier != task['id']: raise ValueError('wrong task')
    def issue(self,repository,task,subject,review):
        assert os.environ['NR_HOST_ROOT'] == str(self.host)
        assert 'PYTHONPATH' not in os.environ and 'PYTHONHOME' not in os.environ and 'UNTRUSTED_TOKEN' not in os.environ
        (self.home/'invoked').write_text(str(repository))
        return read_object(self.home/'fixture-receipt.json')
class DigitalaPublisher:
    def __init__(self,issuer): self.issuer=issuer
    def publish_sealed(self,identifier):
        record=read_object(self.issuer.home/'requests'/identifier/'request.json')
        return {'fixture_only':True,'task':record['task']['id'],'candidate':record['subject']['candidate']}
'''


class HostPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.host = Path(self.temp.name).resolve() / 'host'; self.host.mkdir()
        self.home = self.host / '.runtime/ap11/check-issuer'
        self.entry = self.home / 'launch.py'
        private(self.entry, SOURCE.read_bytes())
        self.root = self.home / 'adopted' / ('d'*40)
        for name in launcher.CODE: private(self.root/name, FIXTURE if name=='runtime/check_issuer.py' else b'')
        hashes = {p:launcher.sha((self.root/p).read_bytes()) for p in launcher.CODE}
        review = {'verdict':'approved','blocking_findings':[],'code_sha256':hashes,
                  'reviewer_run':'fixture-review','implementation_run':'fixture-implementation'}
        private(self.home/'adoption-review.json',review)
        authority = {'schema':'nortropic-issuer-authority/1','app_id':17,'installation_id':19,
                     'adopted_code_root':str(self.root),'code_sha256':hashes,
                     'adoption_review_sha256':launcher.sha((self.home/'adoption-review.json').read_bytes())}
        private(self.home/'authority.json',authority)
        self.adoption = {'schema':'nortropic-launcher-adoption/1','verdict':'approved','blocking_findings':[],
                         'reviewer_run':'launcher-review','implementation_run':'launcher-implementation',
                         'issuer_authority_sha256':launcher.sha((self.home/'authority.json').read_bytes()),
                         'launcher_sha256':launcher.sha(SOURCE.read_bytes())}
        private(self.home/'launcher-adoption.json',self.adoption)
        self.task={'id':'fixture','target':'Nortropic/nortropic-runtime','acceptance_sha256':'a'*64}
        self.subject={'candidate':'b'*40}
        self.review={'fixture_binding':'unused'}
        # The double returns this sealed binding; real issuer recomputes it.
        self.expected=check_binding(self.task,self.subject,self.review)
        sealed_review={'fixture_binding':self.expected}
        private(self.home/'requests/fixture/request.json',{'task':self.task,'subject':self.subject,'review':sealed_review})
        self.receipt={'schema':'nortropic-issued-checks/1','candidate':'b'*40,'binding':self.expected,
                      'task_sha256':digest(self.task),'acceptance_sha256':'a'*64,'app_id':17,
                      'checks':{'runtime/tests':{'id':1,'app_id':17},'runtime/review':{'id':2,'app_id':17}}}
        private(self.home/'fixture-receipt.json',self.receipt)
        python=self.host/'.runtime/temporal-venv/bin/python';python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)

    def invoke(self,*args):
        return subprocess.run([sys.executable,'-I','-B',str(self.entry),*args],capture_output=True,
                              env={'PATH':'/usr/bin:/bin','NR_HOST_ROOT':'/not-authority',
                                   'PYTHONPATH':'/not-code','PYTHONHOME':'/not-python','UNTRUSTED_TOKEN':'fixture-only'})

    def issue(self):
        with patch.object(caller,'ROOT',self.host):
            return Publisher(self.host,self.task['target']).issue_checks(self.task,self.subject,self.review)

    def test_ordinary_publisher_uses_actual_separate_frozen_process(self):
        self.assertEqual(self.issue(),self.receipt)
        self.assertEqual((self.home/'invoked').read_text(),str(self.host))

    def test_digitala_operation_selects_only_sealed_task(self):
        result=self.invoke('digitala','--task','fixture')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'fixture_only':True,'task':'fixture','candidate':'b'*40})

    def test_caller_binding_mismatch_refuses_before_issuer_effect(self):
        result=self.invoke('issue','--task','fixture','--candidate','c'*40,'--binding',self.expected)
        self.assertEqual(result.returncode,2);self.assertFalse((self.home/'invoked').exists())
        result=self.invoke('issue','--task','fixture','--candidate','b'*40,'--binding','nortropic-check/1:'+'f'*64)
        self.assertEqual(result.returncode,2);self.assertFalse((self.home/'invoked').exists())

    def test_issue_is_only_runtime_office_and_cannot_skip_digitala_gates(self):
        path=self.home/'requests/fixture/request.json'
        record=json.loads(path.read_bytes())
        for target in ('Nortropic/nortropic-digitala','Nortropic/nortropic-kundstart','other/project'):
            record['task']['target']=target;private(path,record)
            result=self.invoke('issue','--task','fixture','--candidate','b'*40,'--binding',self.expected)
            with self.subTest(target=target):
                self.assertEqual(result.returncode,2);self.assertFalse((self.home/'invoked').exists())
        record['task']['target']='Nortropic/nortropic-projektkontor';private(path,record)
        result=self.invoke('issue','--task','fixture','--candidate','b'*40,'--binding',self.expected)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.home/'invoked').read_text(),str(self.host.parent/'nortropic-projektkontor'))

    def test_changed_closure_refuses_before_import(self):
        private(self.root/'runtime/check_issuer.py',b'raise RuntimeError("UNTRUSTED IMPORT")\n')
        result=self.invoke('digitala','--task','fixture')
        self.assertEqual(result.returncode,2);self.assertNotIn(b'UNTRUSTED IMPORT',result.stderr)

    def test_self_reviewed_or_changed_launcher_is_not_executed_by_caller(self):
        self.adoption['reviewer_run']=self.adoption['implementation_run']
        private(self.home/'launcher-adoption.json',self.adoption)
        with patch.object(caller.subprocess,'run') as run, self.assertRaises(GateClosed): self.issue()
        run.assert_not_called()
        self.adoption['reviewer_run']='separate';private(self.home/'launcher-adoption.json',self.adoption)
        private(self.entry,b'raise RuntimeError("wrong launcher")\n')
        with patch.object(caller.subprocess,'run') as run, self.assertRaises(GateClosed): self.issue()
        run.assert_not_called()

    def test_wrong_receipt_binding_candidate_or_success_shape_is_refused(self):
        for key,value in [('candidate','c'*40),('binding','wrong'),('app_id',True),('checks',{}),('task_sha256','f'*64)]:
            receipt=copy.deepcopy(self.receipt);receipt[key]=value
            private(self.home/'fixture-receipt.json',receipt)
            with self.subTest(key=key), self.assertRaises(GateClosed): self.issue()

    def test_symlink_authority_and_unqualified_bytecode_refused(self):
        authority=self.home/'authority.json';copy_path=self.home/'other.json'
        authority.rename(copy_path);authority.symlink_to(copy_path)
        self.assertEqual(self.invoke('digitala','--task','fixture').returncode,2)
        authority.unlink();copy_path.rename(authority)
        private(self.root/'runtime/__pycache__/check_issuer.cpython-312.pyc',b'unqualified')
        self.assertEqual(self.invoke('digitala','--task','fixture').returncode,2)

    def test_closed_options_and_unknown_task_refuse(self):
        for args in [('shell','--task','fixture'),('digitala','--task','../fixture'),
                     ('digitala','--task','missing'),('digitala','--task','fixture','--candidate','b'*40)]:
            with self.subTest(args=args): self.assertEqual(self.invoke(*args).returncode,2)
        self.assertFalse((self.home/'invoked').exists())

    def test_source_checkout_cannot_be_the_installed_launcher(self):
        with self.assertRaises(ValueError):launcher.qualified_root(SOURCE)

    def test_old_authority_hash_and_missing_launcher_refuse_without_fallback(self):
        value=json.loads((self.home/'authority.json').read_bytes());value['installation_id']=20
        private(self.home/'authority.json',value)
        result=self.invoke('digitala','--task','fixture')
        self.assertEqual(result.returncode,2);self.assertFalse((self.home/'invoked').exists())
        self.entry.unlink()
        with patch.object(caller.subprocess,'run') as run, self.assertRaises(GateClosed): self.issue()
        run.assert_not_called()


if __name__=='__main__': unittest.main()
