"""Synthetic native-decision tests; real queue and session proof is separate."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from temporalio import workflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
from runtime.development_workflow import FiniteDevelopment


class Child:
    def __init__(self, name, events):
        self.name = name; self.events = events; self.signal = AsyncMock(); self.cancelled = False
    def __await__(self):
        async def done():
            self.events.append(('actual-child-return', self.name))
            return {'phase': 'completed', 'integration': {'fixture': self.name}}
        return done().__await__()
    def cancel(self): self.cancelled = True


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_definition_loads_in_existing_native_sandbox(self):
        SandboxedWorkflowRunner().prepare_workflow(workflow._Definition.must_from_class(FiniteDevelopment))

    async def test_dependent_preparation_follows_actual_first_result(self):
        instance = FiniteDevelopment(); events = []; children = []
        async def step(operation, **fields):
            events.append((operation, fields))
            if operation == 'propose': return {'draft': fields['work'], 'sha256': 'fixture'}
            if operation == 'review': return {'review': 'review', 'approved': True}
            if operation == 'freeze': return {'task': {'id': fields['draft']['draft']}}
            if operation == 'control': return {'control': 'active'}
            if operation == 'observe': return {'child': {'phase': 'completed'}}
            self.fail('Unexpected operation')
        async def child_start(_, task, **options):
            child = Child(task['id'], events); children.append(child); return child
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', side_effect=child_start):
            result = await instance.run('a'*64)
        first = events.index(('actual-child-return', 'reconciliation'))
        second = next(i for i,e in enumerate(events) if e[0]=='propose' and e[1]['work']=='handoff')
        self.assertLess(first, second)
        self.assertEqual(result['phase'], 'awaiting_whole_goal_review')
        self.assertFalse(result['whole_goal_complete'])  # two task PASS cannot close G1–G10
        self.assertEqual(result['children'], ['reconciliation', 'handoff'])

    async def test_stop_cancels_only_own_child(self):
        instance = FiniteDevelopment(); child = Child('own', [])
        async def step(operation, **fields):
            return {'propose': {'draft': 'own'}, 'review': {'approved': True, 'review': 'r'},
                    'freeze': {'task': {'id': 'own'}}, 'control': {'control': 'stopped'}}[operation]
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', AsyncMock(return_value=child)) as start:
            result = await instance.run('a'*64)
        self.assertTrue(child.cancelled); self.assertEqual(start.await_count, 1)
        self.assertEqual(result['phase'], 'stopped')

    async def test_no_child_for_inconclusive_preparation_review(self):
        instance = FiniteDevelopment()
        async def step(operation, **fields):
            if operation == 'propose': return {'draft': 'fixture'}
            return {'approved': False, 'decision': {'verdict': 'inconclusive', 'blocking_findings': []}}
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', AsyncMock()) as start:
            result = await instance.run('a'*64)
        start.assert_not_awaited(); self.assertEqual(result['phase'], 'preparation_not_approved')

    async def test_native_capacity_timer_without_a_new_operation_identity(self):
        instance = FiniteDevelopment(); instance.expected = 'a'*64
        with patch('runtime.development_workflow.workflow.execute_activity', AsyncMock(side_effect=[
                {'capacity_wait': True, 'reason': 'watch due'}, {'control': 'active'}])) as execute, \
             patch('runtime.development_workflow.workflow.sleep', AsyncMock()) as sleep:
            result = await instance.step('control')
        sleep.assert_awaited_once_with(30)
        self.assertEqual(execute.await_args_list[0], execute.await_args_list[1])
        self.assertEqual(execute.await_args.kwargs['start_to_close_timeout'].total_seconds(), 1520)
        self.assertEqual(instance.sequence, 1); self.assertEqual(result['control'], 'active')


if __name__ == '__main__': unittest.main()
