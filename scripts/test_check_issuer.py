"""Real Git/acceptance execution; explicit fake GitHub App transport, never live issuance."""
from datetime import datetime, timedelta, timezone
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import check_issuer as c
from runtime.integration import digest, GateClosed, Publisher


class FakeApp:
    def __init__(self, base, head):
        self.base, self.head = base, head
        self.runs, self.posts = [], []
        self.authenticated = False
        self.wrong_app = False
    def authenticate(self, repository): self.authenticated = True
    def api(self, repository, path, method='GET', body=None):
        if path == 'commits/main': return {'sha': self.base}
        if '/check-runs?' in path: return {'total_count': len(self.runs), 'check_runs': self.runs}
        if path == 'check-runs' and method == 'POST':
            self.posts.append(body)
            run = {**body, 'id': len(self.runs)+1, 'app': {'id': 999 if self.wrong_app else 17}}
            self.runs.append(run); return run
        raise AssertionError(path)


def private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    path.chmod(0o600)


class IssuerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.host = Path(self.temp.name) / 'runtime'; self.host.mkdir()
        self.issuer = c.HostIssuer(self.host)
        def git(*args): return c.git(self.host, *args).decode().strip()
        self.git = git
        git('init', '-q'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@invalid.test')
        git('remote', 'add', 'origin', 'https://github.com/Nortropic/nortropic-runtime.git')
        (self.host/'value.py').write_text('VALUE=1\n'); git('add', 'value.py'); git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        (self.host/'value.py').write_text('VALUE=2\n'); git('commit', '-qam', 'candidate')
        head = git('rev-parse', 'HEAD')
        self.task = {'id': 'fixture', 'target': c.TARGETS[0], 'base': base,
                     'steps': [{'provider': 'codex'}], 'allowed_paths': ['value.py'], 'acceptance_sha256': 'a'*64}
        self.subject = {'task_id':'fixture', 'task_sha256': digest(self.task), 'base':base, 'candidate':head,
                        'completed_steps':[0], 'implementation_runs':['author'], 'acceptance_sha256':'a'*64}
        self.review = {k:self.subject[k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
        self.review.update(scope='whole_task', terminal_status='completed', verdict='approved',
                           blocking_findings=[], reviewer_run='separate-review')
        self.directory = self.issuer.home / 'requests/fixture'
        program = b'import json,sys\nsys.path.insert(0,sys.argv[1])\nimport value\ncase=json.load(sys.stdin)\nprint(json.dumps({"value":value.VALUE + case["add"]}))\n'
        contract = {'schema':'nortropic-behavior-acceptance/1', 'cases':[
            {'id':'add-positive','input':{'add':3},'expected':{'value':5},'timeout_seconds':10},
            {'id':'add-negative','input':{'add':-7},'expected':{'value':-5},'timeout_seconds':10}]}
        private(self.directory/'acceptance.json', contract)
        private(self.directory/'probe.py', program)
        private(self.directory/'review.json', self.review)
        now = datetime.now(timezone.utc)
        self.record = {'schema':'nortropic-issuer-request/1', 'task':self.task, 'subject':self.subject,
                       'review':self.review, 'review_sha256':c.sha((self.directory/'review.json').read_bytes()),
                       'probe_program_sha256':c.sha(program),
                       'acceptance_contract_sha256':c.sha((self.directory/'acceptance.json').read_bytes()), 'accepted_at':now.isoformat(),
                       'expires_at':(now+timedelta(hours=1)).isoformat()}
        private(self.directory/'request.json', self.record)
        code_root=Path(c.__file__).resolve().parents[1]
        hashes={p:c.sha((code_root/p).read_bytes()) for p in c.CODE}
        adoption={'verdict':'approved', 'blocking_findings':[], 'code_sha256':hashes,
                  'reviewer_run':'review-adoption', 'implementation_run':'author-adoption'}
        private(self.issuer.home/'adoption-review.json', adoption)
        private(self.issuer.home/'authority.json', {'schema':'nortropic-issuer-authority/1',
            'app_id':17, 'installation_id':19, 'adopted_code_root':str(code_root), 'code_sha256':hashes,
            'adoption_review_sha256':c.sha((self.issuer.home/'adoption-review.json').read_bytes())})
        self.client = FakeApp(base,head)

    def issue(self): return self.issuer.issue(self.host,self.task,self.subject,self.review,self.client)

    @staticmethod
    def local_runner(workspace, program, input_data=b'', timeout=120):
        # Real program/process and Git bytes; this test adapter does NOT claim sandbox qualification.
        run=subprocess.run(['/opt/homebrew/bin/python3.12','-I','-B',str(program),str(workspace/'source')],
                           capture_output=True, input=input_data, timeout=timeout)
        return {'returncode':run.returncode,'timed_out':False,'output':run.stdout,'output_sha256':c.sha(run.stdout), 'stderr':run.stderr, 'stderr_sha256':c.sha(run.stderr)}

    def test_real_acceptance_issues_bound_checks_and_reconciles_without_duplicate(self):
        with patch.object(c,'run_isolated',self.local_runner):
            receipt=self.issue(); again=self.issue()
        self.assertEqual(len(self.client.posts),2)
        self.assertEqual(receipt,again)
        self.assertEqual(receipt['binding'], c.binding(self.task,self.subject,self.review))
        self.assertTrue(self.client.authenticated)

    def test_failed_actual_acceptance_never_authenticates_or_issues(self):
        program=b'raise SystemExit(3)\n'
        private(self.directory/'probe.py',program)
        self.record['probe_program_sha256']=c.sha(program);private(self.directory/'request.json',self.record)
        with patch.object(c,'run_isolated',self.local_runner), self.assertRaisesRegex(GateClosed,'acceptance failed'):
            self.issue()
        self.assertFalse(self.client.authenticated);self.assertEqual(self.client.posts,[])

    def replace_candidate(self, source):
        (self.host/'value.py').write_text(source)
        self.git('commit','-qam','replacement','--amend')
        self.subject['candidate']=self.git('rev-parse','HEAD')
        self.review['candidate']=self.subject['candidate']
        self.client.head=self.subject['candidate']
        self.record.update(subject=self.subject,review=self.review)
        private(self.directory/'review.json', self.review)
        self.record['review_sha256']=c.sha((self.directory/'review.json').read_bytes())
        private(self.directory/'request.json',self.record)

    def test_candidate_exit_zero_and_arbitrary_success_cannot_end_host_assertions(self):
        for source in ('import os; os._exit(0)\nVALUE=999\n',
                       'import os; print("true",flush=True); os._exit(0)\nVALUE=999\n',
                       'VALUE=999\n'):
            with self.subTest(source=source):
                self.replace_candidate(source)
                with patch.object(c,'run_isolated',self.local_runner), self.assertRaisesRegex(GateClosed,'behavior differs'):
                    self.issue()
                self.assertFalse(self.client.authenticated); self.assertEqual(self.client.posts,[])

    def test_ordinary_publisher_issues_for_real_integration_worktree(self):
        worktree=self.host/'.runtime/ap11/integrations/fixture'
        self.git('worktree','add','--detach',str(worktree),self.subject['candidate'])
        with patch.object(c,'HostIssuer',return_value=self.issuer), \
             patch.object(c,'AppTransport',return_value=self.client), \
             patch.object(c,'current_main',return_value=self.subject['base']), \
             patch.object(c,'run_isolated',self.local_runner):
            receipt=Publisher(worktree,self.task['target']).issue_checks(self.task,self.subject,self.review)
        self.assertEqual(receipt['candidate'],self.subject['candidate'])
        self.assertEqual(len(self.client.posts),2)

    def test_unrelated_clone_with_same_origin_cannot_replace_host_repository(self):
        clone=self.host.parent/'unrelated'
        self.git('clone','-q',str(self.host),str(clone))
        c.git(clone,'remote','set-url','origin','https://github.com/'+self.task['target']+'.git')
        with patch.object(c,'run_isolated') as execute, self.assertRaisesRegex(GateClosed,'fixed host mapping'):
            self.issuer.issue(clone,self.task,self.subject,self.review,self.client)
        execute.assert_not_called(); self.assertFalse(self.client.authenticated)

    def test_private_expectation_is_not_copied_to_candidate_workspace_or_input(self):
        def observed(workspace,program,input_data,timeout):
            self.assertEqual(sorted(p.name for p in workspace.iterdir()),['.scratch','probe.py','source'])
            self.assertNotIn(b'expected',input_data)
            return self.local_runner(workspace,program,input_data,timeout)
        with patch.object(c,'run_isolated',observed): self.issue()

    def test_changed_private_expectation_refuses_before_execution(self):
        private(self.directory/'acceptance.json', {'passed':True})
        with patch.object(c,'run_isolated') as run, self.assertRaisesRegex(GateClosed,'changed'): self.issue()
        run.assert_not_called(); self.assertFalse(self.client.authenticated)

    def digitala_fixture(self, bad_pins=False):
        repository=self.host.parent/'nortropic-digitala'
        self.git('clone','-q',str(self.host),str(repository))
        def git(*args):return c.git(repository,*args).decode().strip()
        git('config','user.name','Fixture');git('config','user.email','fixture@invalid.test')
        git('remote','set-url','origin','https://github.com/Nortropic/nortropic-digitala.git')
        (repository/'steg').mkdir()
        (repository/'steg/steg.json').write_text(json.dumps({'steg':{'example':{'underlag':[
            {'klass':'profession','fil':'value.py'}]}}}))
        pin='0'*64 if bad_pins else c.sha((repository/'value.py').read_bytes())
        (repository/'steg/PINNAR.sha256').write_text(pin+'  value.py\n')
        git('add','steg');git('commit','--amend','-qm','Digitala candidate')
        self.task.update(target='Nortropic/nortropic-digitala',allowed_paths=['value.py','steg/steg.json','steg/PINNAR.sha256'])
        self.subject.update(candidate=git('rev-parse','HEAD'),task_sha256=digest(self.task))
        self.review.update(candidate=self.subject['candidate'],task_sha256=digest(self.task))
        private(self.directory/'review.json',self.review)
        self.record.update(task=self.task,subject=self.subject,review=self.review,
                           review_sha256=c.sha((self.directory/'review.json').read_bytes()))
        log=b'Ran 2 tests in 0.1s\n\nOK\n'
        suite={'schema':'nortropic-measured-suite/1','candidate':self.subject['candidate'],
            'tree':git('rev-parse','HEAD^{tree}'),
            'command':['python','-B','-m','unittest','discover','-s','verktyg','-p','test_*.py'],
            'log_sha256':c.sha(log),'returncode':0,'test_count':2,'credential_free_execution':True}
        private(self.directory/'suite.json',suite);private(self.directory/'suite.log',log)
        self.record['suite_sha256']=c.sha((self.directory/'suite.json').read_bytes())
        private(self.directory/'request.json',self.record)
        self.client.head=self.subject['candidate']
        return c.DigitalaPublisher(self.issuer)

    def test_digitala_sealed_entry_runs_protected_flow_without_candidate_host_suite(self):
        from scripts.test_integration import protection_fixture
        publisher=self.digitala_fixture(); mutations=[]; pr={}
        protection=protection_fixture()
        for check in protection['required_status_checks']['checks']:check['app_id']=17
        def api(path,method='GET',body=None):
            if method!='GET':mutations.append((method,path))
            if path=='branches/main/protection':return protection
            if path.startswith('pulls?'):return []
            if path=='pulls' and method=='POST':
                pr.update(number=1,head={'sha':self.subject['candidate']},base={'ref':'main'},state='open')
                return pr
            if path=='pulls/1':return pr
            if path=='pulls/1/merge':pr['merged']=True;return {'merged':True}
            if '/check-runs?' in path:return {'total_count':len(self.client.runs),'check_runs':self.client.runs}
            raise AssertionError(path)
        real_git=publisher.git
        def git(*args):
            if args[0]=='push':mutations.append(('git','push'));return ''
            return real_git(*args)
        actual_run=subprocess.run
        def guarded_run(argv,*args,**kwargs):
            self.assertFalse(any(part in ('unittest','verktyg/pinna.py','verktyg/publicera.py') for part in argv))
            return actual_run(argv,*args,**kwargs)
        with patch.object(publisher,'api',api), patch.object(publisher,'git',git), \
             patch.object(publisher,'require_base'), \
             patch.object(publisher,'reconcile',return_value={'merged':True,'candidate':self.subject['candidate']}), \
             patch.object(c,'AppTransport',return_value=self.client), \
             patch.object(c,'current_main',return_value=self.subject['base']), \
             patch.object(c,'run_isolated',self.local_runner), patch.object(subprocess,'run',guarded_run):
            receipt=publisher.publish_sealed('fixture')
        self.assertTrue(receipt['merged']);self.assertEqual(len(self.client.posts),2)
        self.assertIn(('PUT','pulls/1/merge'),mutations)
        self.assertEqual(receipt['suite_sha256'],self.record['suite_sha256'])

    def test_digitala_pin_mismatch_and_unsealed_suite_refuse_before_publication(self):
        publisher=self.digitala_fixture(bad_pins=True)
        with patch.object(publisher,'api') as api, self.assertRaisesRegex(GateClosed,'pins differ'):
            publisher.publish_sealed('fixture')
        api.assert_not_called();self.assertFalse(self.client.authenticated)
        private(self.directory/'suite.log',b'candidate claims passed')
        with patch.object(publisher,'api') as api, self.assertRaisesRegex(GateClosed,'Sealed suite'):
            publisher.publish_sealed('fixture')
        api.assert_not_called();self.assertFalse(self.client.authenticated)

    def test_arbitrary_success_cannot_replace_missing_acceptance(self):
        (self.directory/'probe.py').unlink()
        self.record['passed']=True;private(self.directory/'request.json',self.record)
        with self.assertRaises(OSError): self.issue()
        self.assertFalse(self.client.authenticated)

    def test_wrong_candidate_task_review_and_expired_request_refuse_before_execution(self):
        for change in ('candidate','task','review','expiry'):
            with self.subTest(change=change):
                altered=copy.deepcopy(self.record)
                if change=='candidate':altered['subject']['candidate']='b'*40
                if change=='task':altered['task']['acceptance_sha256']='c'*64
                if change=='review':altered['review']['verdict']='changes_required'
                if change=='expiry':altered['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
                private(self.directory/'request.json',altered)
                with patch.object(c,'run_isolated') as execute, self.assertRaises(GateClosed):self.issue()
                execute.assert_not_called();self.assertFalse(self.client.authenticated)

    def test_self_review_changed_acceptance_and_unadopted_code_are_refused(self):
        self.review['reviewer_run']='author';self.record['review']=self.review
        private(self.directory/'review.json',self.review)
        self.record['review_sha256']=c.sha((self.directory/'review.json').read_bytes())
        private(self.directory/'request.json',self.record)
        with self.assertRaisesRegex(GateClosed,'Independent'): self.issue()
        private(self.directory/'probe.py',b'print("forged")')
        with self.assertRaisesRegex(GateClosed,'changed'):self.issue()
        private(self.issuer.home/'authority.json',{})
        with self.assertRaisesRegex(GateClosed,'adopted'):self.issue()

    def test_wrong_app_and_replayed_binding_refuse(self):
        with patch.object(c,'run_isolated',self.local_runner):
            self.client.wrong_app=True
            with self.assertRaisesRegex(GateClosed,'differs'):self.issue()
            self.client.wrong_app=False;self.client.runs=[];self.client.posts=[]
            self.issue()
            self.client.runs[0]['external_id']='nortropic-check/1:'+'f'*64
            with self.assertRaisesRegex(GateClosed,'differs'):self.issue()
        self.assertEqual(len(self.client.posts),2)

    def test_moved_main_refuses_before_acceptance(self):
        self.client.base='0'*40
        with patch.object(c,'run_isolated') as run,self.assertRaisesRegex(GateClosed,'current main'):self.issue()
        run.assert_not_called()

    def test_symlink_or_public_authority_file_refused(self):
        path=self.directory/'request.json';path.chmod(0o644)
        with self.assertRaisesRegex(GateClosed,'private'):self.issue()
        original=path.read_bytes();path.unlink();(self.directory/'other').write_bytes(original)
        path.symlink_to('other')
        with self.assertRaisesRegex(GateClosed,'symlinks'):self.issue()

    def test_sealed_host_suite_requires_exact_measurement_and_keeps_candidate_execution_out(self):
        log=b'Ran 2 tests in 0.1s\n\nOK\n'
        record={'schema':'nortropic-measured-suite/1','candidate':self.subject['candidate'],
                'tree':self.git('rev-parse','HEAD^{tree}'),
                'command':['python','-B','-m','unittest','discover','-s','scripts','-p','test_*.py','-v'],
                'log_sha256':c.sha(log),'returncode':0,'test_count':2,'credential_free_execution':True}
        private(self.directory/'suite.json',record);private(self.directory/'suite.log',log)
        self.record['suite_sha256']=c.sha((self.directory/'suite.json').read_bytes())
        private(self.directory/'request.json',self.record)
        with patch.object(c,'HostIssuer',return_value=self.issuer), patch.object(c,'run_isolated') as run:
            receipt=c.sealed_construction_suite(self.host,self.subject['candidate'],'scripts','fixture',2)
            self.assertEqual(receipt.stdout,log);run.assert_not_called()
            with self.assertRaises(GateClosed):
                c.sealed_construction_suite(self.host,self.subject['candidate'],'scripts','fixture',3)
            private(self.directory/'suite.log',b'forged green')
            with self.assertRaises(GateClosed):
                c.sealed_construction_suite(self.host,self.subject['candidate'],'scripts','fixture',2)


if __name__ == '__main__':unittest.main()
