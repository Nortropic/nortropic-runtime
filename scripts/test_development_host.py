"""Isolated host-boundary negatives; no model calls or remote writes."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

from runtime import development_host as host
from runtime.integration import digest


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
    def tearDown(self): self.temp.cleanup()

    def test_whole_proposal_capacity_reserved_before_any_preparation(self):
        from runtime.development_activity import development_step
        scope = SimpleNamespace(inspect=lambda: {'control':'active'})
        with patch('runtime.development_activity.active_scope', return_value=(scope, {})), \
             patch('runtime.development_activity.inspect_capacity', AsyncMock(return_value={'available':False,'reason':'watch due'})) as capacity, \
             patch.object(host,'base_context') as prepare:
            self.assertTrue(development_step({'contract_sha256':'a'*64,'operation':'propose','key':'fixture'})['capacity_wait'])
        capacity.assert_awaited_once_with(1500)
        prepare.assert_not_called()

    def git_fixture(self):
        repo = self.root/'repo'; (repo/'tools').mkdir(parents=True)
        (repo/'tools/development_result.py').write_text('import kontor_result\ndef reconcile(goal,reports): return {"value": kontor_result.VALUE}\n')
        (repo/'tools/kontor_result.py').write_text('VALUE = "bound"\n')
        for args in [('init',), ('add','.'), ('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-m','fixture')]:
            subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
        return repo, host.git(repo,'rev-parse','HEAD')

    def test_mutated_checkout_A_and_dependency_do_not_execute(self):
        repo, revision = self.git_fixture()
        (repo/'tools/development_result.py').write_text('raise RuntimeError("unbound A")\n')
        (repo/'tools/kontor_result.py').write_text('raise RuntimeError("unbound dependency")\n')
        # Real existing native sandbox, fresh Git extraction, no model.
        result = host.apply_integrated_a(repo,revision,self.root/'execution',{},[])
        self.assertEqual(result, {'value':'bound'})
        binding = json.loads((self.root/'execution/binding.json').read_text())
        self.assertEqual(binding['revision'], revision)

    def test_extracted_source_or_dependency_tampering_prevents_launch(self):
        repo, revision = self.git_fixture()
        for index, name in enumerate(('development_result.py','kontor_result.py')):
            destination = self.root/('execution'+str(index))
            def command(workspace, argv, **kw):
                target = workspace/'tools'/name
                target.chmod(0o600); target.write_text('raise RuntimeError("tampered")\n')
                return argv
            with patch('runtime.profile.sandbox_command', side_effect=command), patch.object(host.subprocess, 'run') as run:
                # Git also uses subprocess.run, so provide Git bytes before this patched launch check.
                with patch.object(host, 'git', side_effect=lambda repo,*args,raw=False: (
                        '100644 blob '+ 'a'*40 +'\t'+args[-1] if args[0]=='ls-tree'
                        else b'VALUE="fixture"\n')):
                    with self.assertRaisesRegex(ValueError,'source changed'):
                        host.apply_integrated_a(repo,revision,destination,{},[])
                run.assert_not_called()

    def recovery_fixture(self, phase, action):
        self.task = {'id':'fixture','target':'Nortropic/nortropic-projektkontor','base':'a'*40,
                     'steps':[{'provider':'codex'}], 'acceptance_sha256':'b'*64}
        latest = {'candidate':'c'*40, 'phase_acceptance_passed':True,'provider_completed':True,'thread_id':'implementation'}
        self.state = {'phase':phase,'attempts':1,'results':[latest], 'review_number':1,'review_recovery':action}
        self.scope = SimpleNamespace(directory=self.root/'scope', inspect=lambda:{'tasks':{'fixture':{'task_sha256':digest(self.task)}}})
        for nonce in ('first','second'):
            path = self.scope.directory/'calls'/nonce/'workspace'; path.mkdir(parents=True)
            (path/'CONTEXT.json').write_text(json.dumps({'task':self.task,'actual_child_wait':self.state}))
        self.answer = {'action':action,'reason':'specific diagnosis','changed_prerequisite':'model claims it is fixed'}

    def recover(self, nonce):
        with patch.object(host,'call_result', return_value={'answer':self.answer}), patch.object(host,'load',return_value=self.task):
            return host.recovery_request(self.scope,'fixture',self.state,nonce)

    def test_model_paraphrase_cannot_retry_unchanged_host_or_missing_review(self):
        for phase,action in [('waiting_diagnosis','retry'),('waiting_review','review_only')]:
            with self.subTest(action=action):
                # Separate fixture home for each wait.
                self.root = self.root/action; self.root.mkdir()
                self.recovery_fixture(phase,action)
                self.assertTrue(self.recover('first')['hold'])
                self.answer['changed_prerequisite'] = 'same supposed fix in other words'
                self.assertTrue(self.recover('second')['hold'])
                self.assertFalse(list(self.scope.directory.glob('calls/*/recovery.json')))

    def test_bound_rejection_allows_one_repair_but_not_paraphrased_repeat(self):
        self.recovery_fixture('waiting_review','repair')
        self.state['review'] = {'task_id':'fixture','task_sha256':digest(self.task),'candidate':'c'*40,
            'acceptance_sha256':'b'*64,'scope':'whole_task','terminal_status':'completed',
            'verdict':'rejected','blocking_findings':['Frozen requirement X fails for empty input'],
            'summary':'Concrete bounded candidate defect','reviewer_run':'independent'}
        for nonce in ('first','second'):
            (self.scope.directory/'calls'/nonce/'workspace/CONTEXT.json').write_text(json.dumps({'task':self.task,'actual_child_wait':self.state}))
        self.assertEqual(self.recover('first')['action'],'repair')
        self.answer['reason'] = 'different wording'
        self.answer['changed_prerequisite'] = 'another paraphrase'
        with self.assertRaisesRegex(ValueError,'Repeated unchanged'):
            self.recover('second')

    def test_missing_review_is_not_candidate_defect_even_if_native_hint_says_repair(self):
        self.recovery_fixture('waiting_review','repair')
        self.assertTrue(self.recover('first')['hold'])


if __name__ == '__main__': unittest.main()
