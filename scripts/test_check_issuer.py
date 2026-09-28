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
from runtime.integration import digest, GateClosed


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
        program = b'import pathlib,sys\nassert (pathlib.Path(sys.argv[1])/"value.py").read_text()=="VALUE=2\\n"\nprint("host acceptance ran")\n'
        private(self.directory/'acceptance.py', program)
        private(self.directory/'review.json', self.review)
        now = datetime.now(timezone.utc)
        self.record = {'schema':'nortropic-issuer-request/1', 'task':self.task, 'subject':self.subject,
                       'review':self.review, 'review_sha256':c.sha((self.directory/'review.json').read_bytes()),
                       'acceptance_program_sha256':c.sha(program), 'accepted_at':now.isoformat(),
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
    def local_runner(workspace, program):
        # Real program/process and Git bytes; this test adapter does NOT claim sandbox qualification.
        run=subprocess.run(['/opt/homebrew/bin/python3.12','-I','-B',str(program),str(workspace/'source')],
                           capture_output=True)
        return {'returncode':run.returncode,'timed_out':False,'output':run.stdout,'output_sha256':c.sha(run.stdout)}

    def test_real_acceptance_issues_bound_checks_and_reconciles_without_duplicate(self):
        with patch.object(c,'run_isolated',self.local_runner):
            receipt=self.issue(); again=self.issue()
        self.assertEqual(len(self.client.posts),2)
        self.assertEqual(receipt,again)
        self.assertEqual(receipt['binding'], c.binding(self.task,self.subject,self.review))
        self.assertTrue(self.client.authenticated)

    def test_failed_actual_acceptance_never_authenticates_or_issues(self):
        program=b'raise SystemExit(3)\n'
        private(self.directory/'acceptance.py',program)
        self.record['acceptance_program_sha256']=c.sha(program);private(self.directory/'request.json',self.record)
        with patch.object(c,'run_isolated',self.local_runner), self.assertRaisesRegex(GateClosed,'acceptance failed'):
            self.issue()
        self.assertFalse(self.client.authenticated);self.assertEqual(self.client.posts,[])

    def test_arbitrary_success_cannot_replace_missing_acceptance(self):
        (self.directory/'acceptance.py').unlink()
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
        private(self.directory/'acceptance.py',b'print("forged")')
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
