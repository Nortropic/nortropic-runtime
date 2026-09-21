"""Actual local processes and isolated journals; no model or remote mutation."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

from runtime import attempt, development_binding as binding
from runtime.development_scope import Scope, ScopeClosed, initialize
from runtime.development_capacity import before_activity
from runtime.integration import digest, Publisher
from runtime.workflow import DevelopmentTask
from scripts.test_development_scope import contract


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.scope = Scope(self.root / 'scope', initialize(self.root / 'scope', contract()))
        self.task = {'id': 'fixture', 'target': 'Nortropic/nortropic-projektkontor',
                     'attempt_seconds': 10, 'allowed_paths': ['tools/reconciliation.py'],
                     'development': {'work': 'reconciliation', 'contract_sha256': self.scope.expected}}
        self.scope.bind_task('reconciliation', self.task['id'], digest(self.task),
                             self.task['allowed_paths'], 'f'*64)

    def tearDown(self):
        self.temp.cleanup()

    def test_no_scope_for_ordinary_and_no_self_activation(self):
        self.assertIsNone(binding.for_task({'id': 'ordinary'}))
        with patch.object(binding, 'require_active_code', return_value={}):
            with self.assertRaises(ScopeClosed):
                binding.for_task(self.task)
        foreign = {**self.task, 'target': 'Nortropic/nortropic-runtime'}
        with self.assertRaises(ScopeClosed):
            binding.for_task(foreign)

    def test_long_task_identity_cannot_overflow_nonce(self):
        task = {**self.task, 'id': 'x'*80}
        self.scope.bind_task('reconciliation', task['id'], digest(task), task['allowed_paths'], 'f'*64)
        with patch.object(binding, 'for_task', return_value=self.scope):
            result = binding.reserve_task_call(task, 'implementation', 1)
        self.assertLessEqual(len(result[1]), 80)

    def run_process(self, source, after_start=None, fail_started_record=False):
        state, evidence = self.root / 'task', self.root / 'evidence'
        state.mkdir(); evidence.mkdir(); (state / 'candidate').mkdir()
        launch = self.scope.launch
        def wrapped(nonce, callback):
            def invoke():
                process = callback()
                if after_start:
                    after_start()
                return process
            return launch(nonce, invoke)
        append = self.scope.append
        def append_checked(rows, event):
            if fail_started_record and event['kind'] == 'started':
                raise OSError('synthetic disk failure AFTER actual Popen')
            return append(rows, event)
        with patch.object(attempt, 'ROOT', self.root), \
             patch.object(attempt, 'load', return_value=self.task), \
             patch.object(attempt, 'task_directory', return_value=state), \
             patch.object(attempt, 'evidence_directory', return_value=evidence), \
             patch.object(attempt, 'command', return_value=[sys.executable, '-u', '-c', source]), \
             patch.object(attempt, 'environment', return_value={}), \
             patch.object(binding, 'for_task', return_value=self.scope), \
             patch.object(self.scope, 'launch', side_effect=wrapped), \
             patch.object(self.scope, 'append', side_effect=append_checked), \
             patch.dict('os.environ', {}, clear=True), redirect_stdout(io.StringIO()):
            code = attempt.execute(self.task['id'], 1, 'fixture', 10, task_digest=digest(self.task))
        launch_data = json.loads((evidence/'attempt-1/launch.json').read_text())
        report = json.loads((evidence/'attempt-1/result.json').read_text())
        if 'provider_pid' in launch_data:
            self.assertNotEqual(subprocess.run(['ps', '-p', str(launch_data['provider_pid'])],
                                               capture_output=True).returncode, 0)
        return code, report

    def test_real_process_retained_and_removed_if_started_append_fails(self):
        code, report = self.run_process('import time; time.sleep(60)', fail_started_record=True)
        self.assertEqual(code, 1)
        self.assertTrue(report['model_started'])
        self.assertTrue(report['process_group_removed'])
        self.assertEqual(len(self.scope.inspect()['calls']), 1)
        self.assertEqual(self.scope.inspect()['started'], [])

    def test_scoped_cleanup_reuses_verified_group_readback_on_eperm(self):
        with patch('runtime.private_stage.stop_group', side_effect=PermissionError('synthetic macOS exit transition')):
            code,report=self.run_process('pass',fail_started_record=True)
        self.assertEqual(code,1)
        self.assertTrue(report['process_group_removed'])
        self.assertEqual(len(self.scope.inspect()['calls']),1)

    def test_real_running_process_stops_on_own_persistent_stop(self):
        def stop():
            # Launch journal lock is held now; controller obtains it afterwards.
            self.controller = threading.Thread(target=lambda: self.scope.control('stopped', 'fixture'))
            self.controller.start()
        started = time.monotonic()
        code, report = self.run_process('import time; time.sleep(60)', after_start=stop)
        self.controller.join(2)
        self.assertEqual(code, 1)
        self.assertLess(time.monotonic()-started, 8)
        self.assertIn('stopped', report['interrupted'])
        self.assertTrue(report['process_group_removed'])

    def test_stop_before_popen_consumes_no_new_start(self):
        self.scope.control('stopped', 'fixture')
        code, report = self.run_process('raise AssertionError("must not launch")')
        self.assertEqual(code, 1)
        self.assertFalse(report['model_started'])
        self.assertEqual(self.scope.inspect()['calls'], [])

    def test_publication_callback_stop_atomic_and_uncertain_not_repeated(self):
        calls = []
        def uncertain():
            calls.append('remote')
            raise TimeoutError('lost actual response')
        args = ('reconciliation', self.task['id'], digest(self.task), {'api': 'fixture'})
        with self.assertRaises(TimeoutError):
            self.scope.publication_effect(*args, uncertain)
        with self.assertRaises(ScopeClosed):
            self.scope.publication_effect(*args, uncertain)
        self.assertEqual(calls, ['remote'])
        self.scope.control('stopped', 'fixture')
        with self.assertRaises(ScopeClosed):
            self.scope.publication_effect(*args[:3], {'api': 'different'}, uncertain)
        self.assertEqual(calls, ['remote'])

    def test_completed_publication_is_reused_without_repeat(self):
        calls = []
        args = ('reconciliation', self.task['id'], digest(self.task), {'api': 'fixture'})
        def remote():
            calls.append('once'); return {'merged': True}
        self.assertEqual(self.scope.publication_effect(*args, remote), {'merged': True})
        self.scope.control('stopped', 'fixture')
        self.assertEqual(self.scope.publication_effect(*args, remote), {'merged': True})
        self.assertEqual(calls, ['once'])

    def test_capacity_is_rechecked_at_actual_slot_entry_without_side_effect(self):
        denied = {'available': False, 'reason': 'watch due', 'wait_seconds': 30}
        with patch.object(binding, 'for_task', return_value=self.scope), \
             patch('runtime.development_capacity.inspect_capacity', AsyncMock(return_value=denied)) as probe:
            self.assertTrue(before_activity(self.task, 160)['capacity_wait'])
            probe.assert_awaited_once_with(160)
        self.assertEqual(self.scope.inspect()['calls'], [])
        self.assertIsNone(before_activity({}, 160))

    def test_native_wait_releases_slot_and_does_not_rewrite_attempt(self):
        instance = DevelopmentTask(); instance.accepted_task = {**self.task, 'allowed_paths': ['tools/a.py', 'tools/test_a.py']}; instance.phase = 'running_codex'
        results = [{'capacity_wait': True, 'capacity': {'reason': 'watch due'}}, {'done': True}]
        with patch('runtime.workflow.workflow.execute_activity', AsyncMock(side_effect=results)) as run, \
             patch('runtime.workflow.workflow.sleep', AsyncMock()) as wait:
            value = asyncio.run(instance.execute_activity('fixture', {'number': 1}))
        self.assertEqual(value, {'done': True})
        self.assertEqual(run.await_args_list[0], run.await_args_list[1])
        wait.assert_awaited_once_with(30)
        self.assertEqual(instance.phase, 'running_codex')

    def test_full_occupancy_includes_host_checks_and_keeps_ordinary_history(self):
        task = {**self.task, 'allowed_paths': ['tools/a.py', 'tools/test_a.py'], 'attempt_seconds': 480}
        self.assertEqual(binding.activity_seconds(task, 'implementation'), 1500)
        self.assertEqual(binding.activity_seconds(task, 'publication'), 1500)
        self.assertEqual(binding.activity_seconds(task, 'review'), 360)
        self.assertIsNone(binding.activity_seconds({}, 'implementation'))
        for invalid in ({**task, 'attempt_seconds': 481}, {**task, 'allowed_paths': ['tools/a.py']}):
            with self.assertRaises(ScopeClosed):
                binding.activity_seconds(invalid, 'implementation')

    def test_publisher_routes_actual_remote_mutations_through_guard(self):
        publisher = Publisher(self.root)
        calls = []
        publisher.effect_guard = lambda operation, callback: calls.append(operation) or 'guarded'
        self.assertEqual(publisher.git('push', 'origin', 'candidate'), 'guarded')
        self.assertEqual(publisher.api('pulls', 'POST', {'head': 'candidate'}), 'guarded')
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
