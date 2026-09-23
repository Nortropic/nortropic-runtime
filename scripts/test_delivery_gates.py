"""The scope gates are read when an activity is DELIVERED, not when it was scheduled.

G6: all gates survive restart and queued activity delivery. An activity request is fixed when the parent schedules
it; the engine may hand it to a worker much later, after a pause or a stop, or to a worker that replaced the one it
was scheduled for. These drive the REAL development_step against a synthetic scope of the frozen contract shape.
Only the active-scope lookup and the AP10 capacity observation are substituted; nothing here reaches a model, an
engine, the live scope or the network, and every result is a synthetic isolated proof, not a live observation.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import development_activity as activity
from runtime.development_scope import Scope, ScopeClosed, initialize


def contract():
    return {'schema': 1, 'id': 'office-ap11', 'target': 'Nortropic/nortropic-projektkontor',
            'authority_sha256': 'a' * 64, 'acceptance_sha256': 'b' * 64,
            'runtime_revision': 'c' * 40, 'office_revision': 'd' * 40,
            'work': {'reconciliation': ['tools/reconciliation.py'], 'handoff': ['tools/handoff.py']},
            'model_calls': 48, 'implementation_attempts': 6}


GATED = ('interactive', 'propose', 'review', 'freeze', 'diagnose', 'final-review')


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve() / 'scope'
        self.expected = initialize(self.path, contract())

    def tearDown(self):
        self.tmp.cleanup()

    def deliver(self, request, scope=None):
        """Execute the real activity function as a worker would on delivery, reading the scope at that moment."""
        scope = scope or Scope(self.path, self.expected)
        reached = []

        def must_not_run(*args, **kwargs):
            reached.append(args)
            raise AssertionError('model work was reached under a closed gate')
        with patch.object(activity, 'active_scope', return_value=(scope, {'development': {}})), \
             patch.object(activity, 'inspect_capacity', side_effect=self.available), \
             patch.object(activity, 'run_model', side_effect=must_not_run), \
             patch.object(activity.host, 'prepare_call', side_effect=must_not_run), \
             patch.object(activity.host, 'base_context', side_effect=must_not_run):
            result = activity.development_step(request)
        self.assertEqual(reached, [])
        return result

    @staticmethod
    async def available(_seconds):
        return {'available': True, 'wait_seconds': 0, 'reason': 'synthetic'}

    def request(self, operation, sequence=1):
        return {'contract_sha256': self.expected, 'operation': operation, 'key': 'step-%d' % sequence,
                'work': 'handoff', 'task_id': 'bound-task', 'draft': {'draft': 'x'}, 'review': 'r'}

    def test_a_request_scheduled_while_active_and_delivered_after_a_pause_starts_nothing(self):
        scheduled = {operation: self.request(operation, n) for n, operation in enumerate(GATED, 1)}
        Scope(self.path, self.expected).control('paused', 'operator pause after the parent scheduled its steps')
        before = Scope(self.path, self.expected).inspect()
        for operation, request in scheduled.items():
            with self.subTest(operation=operation):
                self.assertEqual(self.deliver(request), {'control_wait': True, 'control': 'paused'})
        after = Scope(self.path, self.expected).inspect()
        self.assertEqual(before, after, 'no reservation, launch or control was recorded by any delivery')
        self.assertFalse((self.path / 'calls').exists(), 'no call stage was prepared')

    def test_every_non_active_gate_is_honoured_at_delivery_and_terminal_ones_stay_closed(self):
        for value in ('quota', 'stopped', 'revoked'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as other:
                path = Path(other).resolve() / 'scope'
                expected = initialize(path, contract())
                Scope(path, expected).control(value, 'synthetic gate')
                scope = Scope(path, expected)
                for operation in GATED:
                    request = {**self.request(operation), 'contract_sha256': expected}
                    self.assertEqual(self.deliver(request, scope), {'control_wait': True, 'control': value})
                if value in ('stopped', 'revoked'):
                    with self.assertRaises(ScopeClosed):
                        Scope(path, expected).control('active', 'a restart or a model cannot reopen it')

    def test_a_worker_that_replaced_the_old_one_reads_the_same_preserved_gate(self):
        """A restart is a new process with fresh module state and a fresh Scope object over the same files."""
        Scope(self.path, self.expected).control('paused', 'pause before the worker was replaced')
        request = self.request('final-review')
        import importlib
        importlib.reload(activity)
        try:
            self.assertEqual(self.deliver(request, Scope(self.path, self.expected)),
                             {'control_wait': True, 'control': 'paused'})
        finally:
            importlib.reload(activity)

    def test_status_and_the_preserved_delivery_read_the_gate_without_passing_it(self):
        Scope(self.path, self.expected).control('stopped', 'synthetic stop')
        self.assertEqual(self.deliver(self.request('control')), {'control': 'stopped'})
        delivered = self.deliver(self.request('preserved-delivery'))
        self.assertEqual(delivered['control'], 'stopped')
        self.assertFalse(delivered['complete'], 'nothing is integrated in this synthetic scope')

    def test_an_unrelated_child_is_refused_before_the_engine_is_asked(self):
        """G8: an irrelevant child is refused. The refusal comes before any native query, so no engine is needed
        and none is reached."""
        with patch.object(activity, 'native_observation', side_effect=AssertionError('engine reached')):
            with self.assertRaises(ValueError) as caught:
                self.deliver(self.request('observe'))
        self.assertIn('unrelated child', str(caught.exception))


class OwnershipGateTests(unittest.TestCase):
    """G6: without concurrent writers. The next counted call is refused while any earlier call's guardian has not
    recorded its process group as removed. Drives the REAL run_model against a synthetic scope; the refusal comes
    before the call's own dispatch record is written, so nothing is launched and nothing is left behind."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve() / 'scope'
        self.expected = initialize(self.path, contract())
        self.scope = Scope(self.path, self.expected)

    def tearDown(self):
        self.tmp.cleanup()

    def earlier(self, name, result):
        stage = self.path / 'calls' / name
        stage.mkdir(parents=True)
        (stage / 'launch.json').write_text('{"provider_pid": 1, "provider_identity": "gone"}')
        if result is not None:
            (stage / 'result.json').write_text(__import__('json').dumps(result))

    def attempt(self):
        nxt = self.path / 'calls' / 'next-call'
        nxt.mkdir(parents=True)
        with patch.object(activity, 'active_scope', return_value=(self.scope, {'development': {}})), \
             patch.object(activity.subprocess, 'Popen', side_effect=AssertionError('a guardian was launched')):
            with self.assertRaises(ValueError) as caught:
                activity.run_model({'contract_sha256': self.expected, 'nonce': 'next-call'})
        self.assertIn('Unresolved earlier AP11 model ownership', str(caught.exception))
        self.assertFalse((nxt / 'dispatch.json').exists(), 'nothing of the next call was written')

    def test_an_earlier_call_without_any_result_blocks_the_next_one(self):
        self.earlier('interrupted', None)
        self.attempt()

    def test_an_earlier_call_whose_group_was_not_verified_removed_blocks_the_next_one(self):
        self.earlier('interrupted', {'completed': False, 'process_group_removed': False})
        self.attempt()

    def test_a_verified_removed_group_is_what_releases_the_next_call(self):
        """The released case, driven up to the point where the guardian would start - and stopped there."""
        self.earlier('interrupted', {'completed': False, 'process_group_removed': True})
        nxt = self.path / 'calls' / 'next-call'
        nxt.mkdir(parents=True)
        with patch.object(activity, 'active_scope', return_value=(self.scope, {'development': {}})), \
             patch.object(activity.subprocess, 'Popen', side_effect=RuntimeError('guardian start reached')):
            with self.assertRaises(RuntimeError) as caught:
                activity.run_model({'contract_sha256': self.expected, 'nonce': 'next-call'})
        self.assertIn('guardian start reached', str(caught.exception))


class StopBoundaryTests(unittest.TestCase):
    """G6: stop cancels only own processes; AP10 and unrelated work stays. The REAL operate('stop') against a
    recording engine double in which EVERY execution, the unrelated ones included, answers RUNNING: whatever it
    touches, it touches by its own names only. Revocation: nothing reopens a terminal scope, and a new commitment
    cannot be initialised over the old one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve() / 'scope'
        self.expected = initialize(self.path, contract())
        self.scope = Scope(self.path, self.expected)
        self.scope.bind_task('reconciliation', 'own-task', 'e' * 64, ['tools/reconciliation.py'], 'f' * 64)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stop_asks_about_and_cancels_only_the_commitments_own_names(self):
        import asyncio
        from types import SimpleNamespace
        from temporalio.client import WorkflowExecutionStatus
        from runtime import development_control as control
        asked, cancelled = [], []

        def handle(name, **kwargs):
            async def describe():
                asked.append(name)
                return SimpleNamespace(status=WorkflowExecutionStatus.RUNNING)

            async def cancel():
                cancelled.append(name)

            async def query(*args, **kwargs):
                return {'phase': 'stopped'}

            async def signal(*args, **kwargs):
                return None
            return SimpleNamespace(describe=describe, cancel=cancel, query=query, signal=signal)

        class Service:
            async def __aenter__(self_inner):
                return SimpleNamespace(get_workflow_handle=handle)

            async def __aexit__(self_inner, *exc):
                return False
        config = {'directory': self.tmp.name, 'development': {'contract_sha256': self.expected},
                  'config_sha256': 'f' * 64}
        with patch.object(control, 'require_active_code', return_value=config), \
             patch.object(control, 'active_scope', return_value=(self.scope, config)), \
             patch.object(control, 'SharedService', Service):
            asyncio.run(control.operate('stop', 'synthetic stop of the commitment'))
        own = {'own-task', 'office-ap11'}
        self.assertEqual(set(asked), own, 'nothing outside the commitment was even asked about')
        self.assertEqual(set(cancelled), own, 'every own RUNNING execution, and only those, was cancelled')
        for unrelated in ('office-python-temporal', 'ap10-office-python-temporal-2026-09-24T07:00:00Z'):
            self.assertNotIn(unrelated, asked + cancelled)
        self.assertEqual(Scope(self.path, self.expected).inspect()['control'], 'stopped')
        with self.assertRaises(ScopeClosed):
            Scope(self.path, self.expected).control('active', 'no path reopens a stopped scope')

    def test_a_revoked_commitment_is_not_reopened_by_resume_or_replaced_by_a_new_one(self):
        import asyncio
        from types import SimpleNamespace
        from runtime import development_control as control
        self.scope.control('revoked', 'owner revoked authority')
        config = {'directory': self.tmp.name, 'development': {'contract_sha256': self.expected},
                  'config_sha256': 'f' * 64}
        with patch.object(control, 'require_active_code', return_value=config), \
             patch.object(control, 'active_scope', return_value=(self.scope, config)), \
             patch.object(control, 'SharedService', side_effect=AssertionError('the engine was reached')):
            with self.assertRaises(ScopeClosed):
                asyncio.run(control.operate('resume', 'an operator resume is not new owner authority'))
        with self.assertRaises(FileExistsError):
            initialize(self.path, contract())
        self.assertEqual(Scope(self.path, self.expected).inspect()['control'], 'revoked')


if __name__ == '__main__':
    unittest.main()
