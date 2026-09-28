"""Publication regressions adapted from selected old caller checks (D016).

Real local Git objects test scope/identity; remote effects use a counted fake.
These tests do not claim a live protected merge or authenticate review receipts.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.integration import GateClosed, Publisher, digest, require_gate, check_binding


def fixture():
    task={'id':'fixture','target':'Nortropic/nortropic-runtime','base':'a'*40,'steps':[{'provider':'codex'}],
          'allowed_paths':['tools/value.txt'],'acceptance_sha256':'f'*64}
    subject={'task_id':task['id'],'task_sha256':digest(task),'base':task['base'],
             'candidate':'b'*40,'completed_steps':[0],
             'implementation_runs':['author-thread'], 'acceptance_sha256':task['acceptance_sha256']}
    common={k:subject[k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
    common.update(scope='whole_task',terminal_status='completed')
    tests={**common,'passed':True}
    review={**common,'verdict':'approved','blocking_findings':[],'reviewer_run':'review-thread'}
    return task,subject,tests,review


def protection_fixture():
    # Synthetic server authority only; no real App is selected or configured.
    return {'required_status_checks': {'strict': True, 'checks': [
        {'context': 'runtime/tests', 'app_id': 101},
        {'context': 'runtime/review', 'app_id': 202}]},
        'enforce_admins': {'enabled': True}, 'allow_force_pushes': {'enabled': False},
        'allow_deletions': {'enabled': False}, 'required_linear_history': {'enabled': True},
        'required_pull_request_reviews': {}}


def checks_fixture():
    return {'total_count': 2, 'check_runs': [
        {'id': i, 'name': name, 'app': {'id': app}, 'head_sha': 'b'*40,
         'status': 'completed', 'conclusion': 'success',
         'external_id': check_binding(fixture()[0], fixture()[1], fixture()[3])}
        for i, name, app in ((1, 'runtime/tests', 101), (2, 'runtime/review', 202))]}


class CountedPublisher(Publisher):
    def __init__(self):
        self.mutations=[];self.pr=None;self.base_checks=0
        self.protection = protection_fixture()
        self.checks = checks_fixture()
        self.protection_reads = 0; self.change_issuer_at = None
        self.changed_base_at=None;self.lost_head=False;self.merged=False;self.lose_merge_response=False
    def inspect_candidate(self,task,subject): return 'tree'
    def issue_checks(self,task,subject,review): return {'fixture_only': True}
    def require_base(self,base):
        self.base_checks+=1
        if self.base_checks==self.changed_base_at: raise GateClosed('changed base')
    def reconcile(self,pr,subject,tree):
        if not pr.get('merged'): raise GateClosed('not merged')
        return {'merged':True,'candidate':subject['candidate']}
    def git(self,*args):
        self.mutations.append(('git',args));return ''
    def api(self,path,method='GET',body=None):
        if method!='GET': self.mutations.append((method,path))
        if path == 'branches/main/protection':
            self.protection_reads += 1
            if self.protection_reads == self.change_issuer_at:
                self.protection['required_status_checks']['checks'][0]['app_id'] = 303
            return self.protection
        if path.endswith('/check-runs?filter=latest&per_page=100'): return self.checks
        if path.startswith('pulls?'): return [self.pr] if self.pr else []
        if path=='pulls' and method=='POST':
            self.pr={'number':1,'head':{'sha':'b'*40},'base':{'ref':'main'},'state':'open'}
            return self.pr
        if path=='pulls/1/merge':
            self.pr['merged']=True;self.merged=True
            if self.lose_merge_response:
                self.lose_merge_response=False
                raise TimeoutError('Simulated lost response after server merge')
            return {'merged':True}
        if path=='pulls/1':
            if self.lost_head: return {**self.pr,'head':{'sha':'c'*40}}
            return self.pr
        raise AssertionError(path)


class IntegrationTest(unittest.TestCase):
    def test_required_evidence_blocks_before_publication(self):
        changes=[(0,lambda e:e.update(target='other/project')),
                 (2,lambda e:e.update(passed=False)),
                 (2,lambda e:e.update(passed='true')),
                 (3,lambda e:e.update(verdict='inconclusive')),
                 (3,lambda e:e.update(verdict='rejected')),
                 (3,lambda e:e.update(blocking_findings=['defect'])),
                 (3,lambda e:e.update(reviewer_run='author-thread')),
                 (3,lambda e:e.update(candidate='c'*40)),
                 (2,lambda e:e.update(terminal_status='interrupted')),
                 (3,lambda e:e.update(terminal_status='missing')),
                 (2,lambda e:e.update(scope='phase_only')),
                 (2,lambda e:e.update(acceptance_sha256='e'*64)),
                 (1,lambda e:e.update(completed_steps=[])),
                 (1,lambda e:e.update(completed_steps=[False]))]
        for index,change in changes:
            with self.subTest(index=index,change=change):
                args=list(fixture());change(args[index]);publisher=CountedPublisher()
                with self.assertRaises(GateClosed): publisher.publish(*args)
                self.assertEqual(publisher.mutations,[])
        for index in (2,3):
            args=list(fixture());args[index]=None;publisher=CountedPublisher()
            with self.assertRaises(GateClosed):publisher.publish(*args)
            self.assertEqual(publisher.mutations,[])

    def test_partial_three_step_task_does_not_publish(self):
        task,subject,tests,review=fixture()
        task['steps']=[{'provider':'codex'},{'provider':'claude'},{'provider':'codex'}]
        subject['task_sha256']=tests['task_sha256']=review['task_sha256']=digest(task)
        publisher=CountedPublisher()
        with self.assertRaisesRegex(GateClosed,'not complete'):publisher.publish(task,subject,tests,review)
        self.assertEqual(publisher.mutations,[])

    def test_base_and_head_rechecked_and_merge_reconciled(self):
        publisher=CountedPublisher();publisher.changed_base_at=2
        with self.assertRaises(GateClosed):publisher.publish(*fixture())
        self.assertFalse(publisher.merged)
        publisher=CountedPublisher();publisher.lost_head=True
        with self.assertRaises(GateClosed):publisher.publish(*fixture())
        self.assertFalse(publisher.merged)
        publisher=CountedPublisher();publisher.lose_merge_response=True
        with self.assertRaises(TimeoutError): publisher.publish(*fixture())
        self.assertTrue(publisher.merged)
        before=list(publisher.mutations)
        self.assertTrue(publisher.publish(*fixture())['merged'])
        self.assertEqual(publisher.mutations,before,'recovery published twice')

    def test_server_must_bind_both_issuers_before_any_mutation(self):
        for value in (None, -1, 0, True, '101'):
            for index in (0, 1):
                with self.subTest(value=value, index=index):
                    p = CountedPublisher()
                    p.protection['required_status_checks']['checks'][index]['app_id'] = value
                    with self.assertRaisesRegex(GateClosed, 'issuer'):
                        p.publish(*fixture())
                    self.assertEqual(p.mutations, [])
        for entries in (None, [], [{'context': 'runtime/tests', 'app_id': 101}]*2,
                        protection_fixture()['required_status_checks']['checks']*2):
            p = CountedPublisher(); p.protection['required_status_checks']['checks'] = entries
            with self.assertRaises(GateClosed): p.publish(*fixture())
            self.assertEqual(p.mutations, [])

    def test_weaker_or_malformed_protection_blocks_before_mutation(self):
        changes = [lambda p: p.update(required_status_checks=None),
                   lambda p: p['required_status_checks'].update(strict=False),
                   lambda p: p.update(enforce_admins={'enabled': False}),
                   lambda p: p.update(allow_force_pushes={'enabled': True}),
                   lambda p: p.update(allow_deletions={'enabled': True}),
                   lambda p: p.pop('allow_deletions'),
                   lambda p: p.update(required_linear_history={'enabled': False}),
                   lambda p: p.update(required_pull_request_reviews=None)]
        for change in changes:
            p = CountedPublisher(); change(p.protection)
            with self.assertRaises(GateClosed): p.publish(*fixture())
            self.assertEqual(p.mutations, [])

    def test_wrong_issuer_head_and_non_successful_checks_never_merge(self):
        changes = [('app', {'id': 999}), ('app', {'id': True}), ('app', None),
                   ('head_sha', 'c'*40), ('head_sha', None), ('status', 'in_progress'),
                   ('conclusion', 'neutral'), ('conclusion', 'skipped'),
                   ('conclusion', 'failure'), ('conclusion', None), ('id', 0)]
        for key, value in changes:
            for index in (0, 1):
                with self.subTest(key=key, value=value, index=index):
                    p = CountedPublisher(); p.checks['check_runs'][index][key] = value
                    with self.assertRaises(GateClosed): p.publish(*fixture())
                    self.assertFalse(p.merged)
                    self.assertFalse(any(m[0] == 'POST' and m[1].startswith('statuses/') for m in p.mutations))

    def test_missing_ambiguous_truncated_or_status_only_readback_never_merges(self):
        good = checks_fixture()['check_runs']
        cases = [None, {}, {'state': 'success', 'statuses': [
            {'context': name, 'state': 'success'} for name in ('runtime/tests', 'runtime/review')]},
            {'total_count': 1, 'check_runs': good[:1]},
            {'total_count': 3, 'check_runs': good},
            {'total_count': 3, 'check_runs': good + [good[0]]},
            {'total_count': 1, 'check_runs': [None]},
            {'total_count': True, 'check_runs': good[:1]}]
        for response in cases:
            p = CountedPublisher(); p.checks = response
            with self.assertRaises(GateClosed): p.publish(*fixture())
            self.assertFalse(p.merged)

    def test_server_issuer_change_before_merge_is_not_silently_adopted(self):
        p = CountedPublisher(); p.change_issuer_at = 2
        with self.assertRaisesRegex(GateClosed, 'issuers changed'): p.publish(*fixture())
        self.assertFalse(p.merged)

    def test_exact_server_bound_checks_allow_merge_without_self_issued_status(self):
        p = CountedPublisher()
        result = p.publish(*fixture())
        self.assertTrue(result['merged'])
        self.assertEqual(p.protection_reads, 3)
        self.assertEqual(result['checks']['runtime/tests']['check_run_id'], 1)
        self.assertEqual(p.mutations, [('git', ('push', 'origin', 'b'*40+':refs/heads/runtime/'+'b'*40)),
                                      ('POST', 'pulls'), ('PUT', 'pulls/1/merge')])

    def test_same_head_with_wrong_task_acceptance_or_review_binding_is_refused(self):
        for value in (None, 'success', 'nortropic-check/1:' + '0'*64):
            p = CountedPublisher(); p.checks['check_runs'][0]['external_id'] = value
            with self.assertRaises(GateClosed): p.publish(*fixture())
            self.assertFalse(p.merged)

    def test_real_git_candidate_scope_and_immutable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
            git('init','-q');git('config','user.name','Runtime test');git('config','user.email','runtime@invalid.test')
            git('remote','add','origin',Publisher.ORIGIN)
            (repo/'seed').write_text('base\n');git('add','seed');git('commit','-qm','base')
            base=git('rev-parse','HEAD');(repo/'tools').mkdir();(repo/'tools/value.txt').write_text('accepted\n')
            git('add','tools');git('commit','-qm','candidate');candidate=git('rev-parse','HEAD')
            task,subject,_,_=fixture();task['base']=base;subject.update(base=base,candidate=candidate)
            publisher=Publisher(repo);tree=publisher.inspect_candidate(task,subject)
            (repo/'tools/value.txt').write_text('unreviewed mutable checkout\n')
            self.assertEqual(publisher.inspect_candidate(task,subject),tree)
            (repo/'gate.py').write_text('changed authority\n');git('add','gate.py');git('commit','--amend','--no-edit','-q')
            subject['candidate']=git('rev-parse','HEAD')
            with self.assertRaisesRegex(GateClosed,'file scope'):publisher.inspect_candidate(task,subject)

    def test_real_git_reconciliation_checks_tree_and_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
            git('init','-q');git('config','user.name','Runtime test');git('config','user.email','runtime@invalid.test')
            (repo/'value').write_text('base');git('add','value');git('commit','-qm','base');base=git('rev-parse','HEAD')
            (repo/'value').write_text('candidate');git('commit','-am','candidate','-q');candidate=git('rev-parse','HEAD')
            tree=git('rev-parse','HEAD^{tree}')
            merged=git('commit-tree',tree,'-p',base,'-m','squashed candidate')
            git('update-ref','refs/remotes/origin/main',merged)
            publisher=Publisher(repo)
            real_git=publisher.git
            publisher.git=lambda *args: '' if args[:1]==('fetch',) else real_git(*args)
            pr={'merged':True,'head':{'sha':candidate},'merge_commit_sha':merged,'html_url':'local-fixture'}
            subject={'base':base,'candidate':candidate}
            self.assertEqual(publisher.reconcile(pr,subject,tree)['merge_commit'],merged)
            with self.assertRaisesRegex(GateClosed,'tree differs'):
                publisher.reconcile(pr,subject,git('rev-parse',base+'^{tree}'))
            with self.assertRaisesRegex(GateClosed,'base does not match'):
                publisher.reconcile(pr,{'base':'c'*40,'candidate':candidate},tree)

    def test_rename_cannot_hide_out_of_scope_source_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
            git('init','-q');git('config','user.name','Runtime test');git('config','user.email','runtime@invalid.test')
            git('config','diff.renames','true');git('remote','add','origin',Publisher.ORIGIN)
            (repo/'protected-source').write_text('unchanged content\n')
            git('add','protected-source');git('commit','-qm','base');base=git('rev-parse','HEAD')
            (repo/'tools').mkdir();git('mv','protected-source','tools/value.txt');git('commit','-qm','rename')
            candidate=git('rev-parse','HEAD')
            self.assertEqual(git('diff','--name-only',base,candidate),'tools/value.txt')
            task,subject,_,_=fixture();task['base']=base;subject.update(base=base,candidate=candidate)
            with self.assertRaisesRegex(GateClosed,'file scope'):Publisher(repo).inspect_candidate(task,subject)
