"""Synthetic native-decision tests; real queue and session proof is separate."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from temporalio import workflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
from runtime.development_workflow import FiniteDevelopment
from runtime.development_trial import CapacityTrial


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
        SandboxedWorkflowRunner().prepare_workflow(workflow._Definition.must_from_class(CapacityTrial))

    async def test_interactive_wait_is_native_and_does_not_start_model_work(self):
        instance=FiniteDevelopment();instance.expected='a'*64
        with patch('runtime.development_workflow.workflow.execute_activity',AsyncMock(side_effect=[
                {'interactive_wait':True},{'draft':'actual-interactive-draft'}])) as execute, \
             patch('runtime.development_workflow.workflow.sleep',AsyncMock()) as sleep:
            result=await instance.step('interactive')
        sleep.assert_awaited_once_with(30)
        self.assertEqual(execute.await_args_list[0],execute.await_args_list[1])
        self.assertEqual(result['draft'],'actual-interactive-draft')

    async def test_a_pause_and_an_evidence_wait_are_event_driven_and_the_session_wait_polls_slowly(self):
        """A pause can last days: it waits for the host's wake signal with a rare fallback timer, never a poll cycle."""
        import asyncio
        from runtime import development_workflow
        for answer in ({'control_wait': True, 'control': 'paused'}, {'proof_wait': True, 'reason': 'evidence not yet preserved'}):
            for outcome in (None, asyncio.TimeoutError()):            # woken by the host signal, or the fallback timer fired
                instance=FiniteDevelopment();instance.expected='a'*64;instance.wake=True
                with patch('runtime.development_workflow.workflow.execute_activity',AsyncMock(side_effect=[answer,{'done':True}])), \
                     patch('runtime.development_workflow.workflow.wait_condition',AsyncMock(side_effect=[outcome])) as wait, \
                     patch('runtime.development_workflow.workflow.sleep',AsyncMock()) as sleep:
                    result=await instance.step('interactive')
                with self.subTest(answer=answer,outcome=outcome):
                    self.assertEqual(result,{'done':True});sleep.assert_not_awaited();wait.assert_awaited_once()
                    self.assertEqual(wait.await_args.kwargs,{'timeout':development_workflow.HOST_WAIT_SECONDS})
                    self.assertFalse(instance.wake)               # cleared before the host step: an OLD wake never skips a wait
                    self.assertFalse(wait.await_args.args[0]());instance.host_state_changed();self.assertTrue(wait.await_args.args[0]())
        instance=FiniteDevelopment();instance.expected='a'*64
        with patch('runtime.development_workflow.workflow.execute_activity',AsyncMock(side_effect=[{'interactive_wait':True},{'done':True}])), \
             patch('runtime.development_workflow.workflow.wait_condition',AsyncMock()) as wait, \
             patch('runtime.development_workflow.workflow.sleep',AsyncMock()) as sleep:
            await instance.step('interactive')
        sleep.assert_awaited_once_with(30);wait.assert_not_awaited()     # the session wait stays host-polled: no signal after a session exit

    async def test_a_wake_that_arrives_while_the_host_step_is_in_flight_is_not_lost(self):
        """Measured in review: clearing the flag at wait entry dropped such a wake and a resume was missed until the fallback."""
        instance=FiniteDevelopment();instance.expected='a'*64;instance.wake=True;seen=[];steps=[]
        async def host_step(*args,**kwargs):
            steps.append(instance.wake)                         # the flag as the host step starts
            if len(steps)==1:
                instance.host_state_changed()                   # the operator's resume lands after this step already read 'paused'
                return {'control_wait':True,'control':'paused'}
            return {'done':True}
        async def wait(condition,timeout=None):
            seen.append(condition())                            # what the wait sees on entry
        with patch('runtime.development_workflow.workflow.execute_activity',host_step), \
             patch('runtime.development_workflow.workflow.wait_condition',wait):
            result=await instance.step('interactive')
        self.assertEqual(result,{'done':True})
        self.assertEqual(steps,[False,False])                   # a stale wake is cleared BEFORE each host step reads the state
        self.assertEqual(seen,[True])                           # the wake from during the step ends the wait at once: control is read again

    async def test_the_wake_signal_carries_no_data_and_changes_no_state_by_itself(self):
        instance=FiniteDevelopment();before=instance.state()
        instance.host_state_changed()
        self.assertEqual(instance.state(),before);self.assertTrue(instance.wake)

    async def test_following_a_child_polls_at_the_same_bounded_rate(self):
        instance = FiniteDevelopment(); observed = iter([{'child': {'phase': 'running'}}, {'child': {'phase': 'completed'}}, {'child': {'phase': 'completed'}}])
        async def step(operation, **fields):
            if operation == 'interactive': return {'draft': 'reconciliation', 'sha256': 'fixture'}
            if operation == 'propose': return {'draft': fields['work'], 'sha256': 'fixture'}
            if operation == 'review': return {'review': 'review', 'approved': True}
            if operation == 'freeze': return {'task': {'id': fields['draft']['draft']}}
            if operation == 'control': return {'control': 'active'}
            if operation == 'observe': return next(observed)
            if operation == 'final-review': return {'approved': False, 'whole_goal_complete': False}
        async def child_start(_, task, **options): return Child(task['id'], [])
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', side_effect=child_start), \
             patch('runtime.development_workflow.workflow.sleep', AsyncMock()) as sleep:
            await instance.run('a'*64)
        self.assertEqual([call.args for call in sleep.await_args_list], [(30,)])

    async def test_dependent_preparation_follows_actual_first_result(self):
        instance = FiniteDevelopment(); events = []; children = []
        async def step(operation, **fields):
            events.append((operation, fields))
            if operation == 'interactive': return {'draft':'reconciliation','sha256':'fixture'}
            if operation == 'propose': return {'draft': fields['work'], 'sha256': 'fixture'}
            if operation == 'review': return {'review': 'review', 'approved': True}
            if operation == 'freeze': return {'task': {'id': fields['draft']['draft']}}
            if operation == 'control': return {'control': 'active'}
            if operation == 'observe': return {'child': {'phase': 'completed'}}
            if operation == 'final-review': return {'approved':False,'whole_goal_complete':False}
            self.fail('Unexpected operation')
        async def child_start(_, task, **options):
            child = Child(task['id'], events); children.append(child); return child
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', side_effect=child_start):
            result = await instance.run('a'*64)
        first = events.index(('actual-child-return', 'reconciliation'))
        second = next(i for i,e in enumerate(events) if e[0]=='propose' and e[1]['work']=='handoff')
        self.assertLess(first, second)
        self.assertEqual(result['phase'], 'whole_goal_not_approved')
        self.assertFalse(result['whole_goal_complete'])  # two task PASS cannot close G1–G10
        self.assertEqual(result['children'], ['reconciliation', 'handoff'])

    async def test_stop_cancels_only_own_child(self):
        instance = FiniteDevelopment(); child = Child('own', [])
        async def step(operation, **fields):
            return {'interactive': {'draft':'own'}, 'propose': {'draft': 'own'}, 'review': {'approved': True, 'review': 'r'},
                    'freeze': {'task': {'id': 'own'}}, 'control': {'control': 'stopped'}}[operation]
        instance.step = step
        with patch('runtime.development_workflow.workflow.start_child_workflow', AsyncMock(return_value=child)) as start:
            result = await instance.run('a'*64)
        self.assertTrue(child.cancelled); self.assertEqual(start.await_count, 1)
        self.assertEqual(result['phase'], 'stopped')

    async def test_no_child_for_inconclusive_preparation_review(self):
        instance = FiniteDevelopment()
        async def step(operation, **fields):
            if operation in ('interactive','propose'): return {'draft': 'fixture'}
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
