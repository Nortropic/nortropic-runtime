"""Synthetic session-selection and closure fixtures, not a G2 pass."""
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import hashlib
import tomllib
from runtime.development_interactive import actual_session, selected_nonce, prepare_retry, interactive_command


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.workspace=self.root/'selected'
        self.folder=self.root/'.codex/sessions'/datetime.now(timezone.utc).strftime('%Y/%m/%d');self.folder.mkdir(parents=True)
    def tearDown(self):self.temp.cleanup()
    def history(self,name='one',complete=True,cwd=None):
        rows=[{'type':'session_meta','payload':{'id':name,'cwd':str(cwd or self.workspace),'source':'cli'}}]
        if complete:rows.append({'type':'event_msg','payload':{'type':'task_complete'}})
        (self.folder/('rollout-'+name+'.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    def read(self):
        with patch('runtime.development_interactive.Path.home',return_value=self.root):
            return actual_session(self.workspace,time.time()-60)
    def test_exact_cwd_and_actual_completed_turn_required(self):
        self.history('unrelated',cwd=self.root/'other');self.history(complete=False)
        with self.assertRaisesRegex(ValueError,'no actual completed'):self.read()
    def test_fresh_selected_history_and_identity_retained(self):
        self.history();identity,raw,source=self.read()
        self.assertEqual(identity,'one');self.assertEqual(source,'cli');self.assertIn(b'task_complete',raw)
    def test_multiple_matching_sessions_are_not_assumed_one_interactive_exit(self):
        self.history();self.history('two')
        with self.assertRaisesRegex(ValueError,'Exactly one'):self.read()

    def test_process_local_trust_retains_sandbox_and_refuses_project_layers(self):
        self.workspace.mkdir()
        fixed=['codex','-c','default_permissions="nr"','-c','approval_policy="never"','exec','--json','-']
        with patch('runtime.development_interactive.command',return_value=fixed),patch('runtime.development_interactive.ROOT',self.root),patch('runtime.development_interactive.Path.home',return_value=self.root):
            argv=interactive_command(self.workspace,'fixture')
            self.assertEqual(argv[:5],fixed[:5]);self.assertNotIn('exec',argv)
            self.assertIn('tui.show_tooltips=false',argv)
            settings=tomllib.loads(argv[6]);self.assertEqual(settings,{'projects':{str(self.root):{'trust_level':'trusted'}}})
            (self.workspace/'.codex').mkdir()
            with self.assertRaisesRegex(ValueError,'Project-local'):interactive_command(self.workspace,'fixture')

    def test_retry_keeps_failed_call_and_requires_exact_unchanged_selection(self):
        directory=self.root/'scope';stage=directory/'calls/interactive-start';stage.mkdir(parents=True)
        prior={'completed':False,'process_group_removed':True};(stage/'result.json').write_text(json.dumps(prior))
        (stage/'session-exit.json').write_text(json.dumps({'process_absent':True,'provider_pid':123}))
        scope=SimpleNamespace(directory=directory,inspect=lambda:{'control':'paused','tasks':{},'calls':[{'nonce':'interactive-start'}]})
        def prepare(*args):
            new=directory/'calls'/args[1];new.mkdir();raw=json.dumps({'actual':args[1]}).encode();(new/'input.json').write_bytes(raw)
            return {'nonce':args[1],'input_sha256':hashlib.sha256(raw).hexdigest()}
        with patch('runtime.development_interactive.active_scope',return_value=(scope,{})),patch('runtime.development_interactive.process_identity',return_value=''),patch('runtime.development_interactive.os.killpg',side_effect=ProcessLookupError),patch('runtime.development_interactive.host.base_context',return_value=({},{})),patch('runtime.development_interactive.host.prepare_call',side_effect=prepare):
            request=prepare_retry('fixed','Actual diagnosed trust startup; process-local correction')
            self.assertEqual(selected_nonce(scope),request['nonce'])
            with self.assertRaisesRegex(ValueError,'has not ended'):prepare_retry('fixed','repeat')
            first=directory/'calls/interactive-retry-1'
            (first/'result.json').write_text(json.dumps(prior))
            (first/'session-exit.json').write_bytes((stage/'session-exit.json').read_bytes())
            second=prepare_retry('fixed','Distinct observed native tooltip guard failure; process-local suppression')
            self.assertEqual(selected_nonce(scope),'interactive-retry-2')
            self.assertEqual(second['nonce'],'interactive-retry-2')
            # A third diagnosed retry exists (owner mandate 2026-09-21); it needs the second one ended, and it is the last.
            with self.assertRaisesRegex(ValueError,'has not ended'):prepare_retry('fixed','third before second ended')
            ended=directory/'calls/interactive-retry-2'
            (ended/'result.json').write_text(json.dumps(prior))
            (ended/'session-exit.json').write_bytes((stage/'session-exit.json').read_bytes())
            third=prepare_retry('fixed','Provider quota ended retry2 before any draft; owner-selected available executor')
            self.assertEqual(third['nonce'],'interactive-retry-3');self.assertEqual(selected_nonce(scope),'interactive-retry-3')
            # A fourth start exists ONLY through the separately reviewed extension bound in the active configuration
            # (test_discoverability); without it the three retries stay the end, whatever the third one answered.
            with self.assertRaisesRegex(ValueError,'No further interactive start'):prepare_retry('fixed','fourth')
            binding=(directory/'interactive-retry.json').read_bytes()
            (directory/'interactive-retry.json').unlink()
            with self.assertRaisesRegex(ValueError,'Earlier'):selected_nonce(scope)
            (directory/'interactive-retry.json').write_bytes(binding)
        self.assertEqual(json.loads((stage/'result.json').read_text()),prior)
        (stage/'result.json').write_text('{"completed":true}')
        with self.assertRaisesRegex(ValueError,'evidence changed'):selected_nonce(scope)

    def test_retry_refuses_running_previous_process_or_new_children(self):
        directory=self.root/'scope';stage=directory/'calls/interactive-start';stage.mkdir(parents=True)
        (stage/'result.json').write_text(json.dumps({'completed':False,'process_group_removed':True}))
        (stage/'session-exit.json').write_text(json.dumps({'process_absent':True,'provider_pid':123}))
        state={'control':'paused','tasks':{}}
        scope=SimpleNamespace(directory=directory,inspect=lambda:state)
        with patch('runtime.development_interactive.active_scope',return_value=(scope,{})),patch('runtime.development_interactive.process_identity',return_value='still present'):
            with self.assertRaisesRegex(ValueError,'absent'):prepare_retry('fixed','diagnosed')
            state['tasks']={'child':{}}
            with self.assertRaisesRegex(ValueError,'Only explicit'):prepare_retry('fixed','diagnosed')

    def test_real_context_gate_only_allows_exact_paused_pre_task_recovery_read(self):
        from runtime import development_host as host
        state={'control':'paused','tasks':{},'integrated':{}}
        scope=SimpleNamespace(inspect=lambda:state)
        # Reach the real gate; stop at the first subsequent policy read. No
        # source/network/model call and no mocked base_context hiding its gate.
        with patch.object(host,'policy',side_effect=LookupError('context gate passed')):
            for key in ('interactive-retry-1','interactive-retry-2','interactive-retry-3'):
                with self.subTest(key=key),self.assertRaisesRegex(LookupError,'gate passed'):
                    host.base_context(scope,{},'reconciliation',key,paused_interactive_recovery=True)
            with self.subTest(key='interactive-retry-4'),self.assertRaisesRegex(LookupError,'gate passed'):
                host.base_context(scope,{},'reconciliation','interactive-retry-4',paused_interactive_recovery=True)
            with self.assertRaisesRegex(ValueError,'No new preparation'):
                host.base_context(scope,{},'reconciliation','interactive-retry-5',paused_interactive_recovery=True)
            for control,work,key,flag,tasks in [('paused','reconciliation','interactive-retry-1',False,{}),('stopped','reconciliation','interactive-retry-1',True,{}),('paused','handoff','interactive-retry-1',True,{}),('paused','reconciliation','step-1',True,{}),('paused','reconciliation','interactive-retry-1',True,{'child':{}})]:
                state.update(control=control,tasks=tasks)
                with self.assertRaisesRegex(ValueError,'No new preparation'):
                    host.base_context(scope,{},work,key,paused_interactive_recovery=flag)


if __name__=='__main__':unittest.main()
