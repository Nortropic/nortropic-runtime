"""The WHOLE operator path to a second whole-goal assessment, not the internal function alone.

Terminal parser -> chosen action -> bound decision and predecessor -> check of the preserved integrations ->
whole-goal assessment. Driven in isolation with a fake engine: no service, no model, no scope of the real
application, and nothing here is the later live assessment.
"""
import asyncio
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from temporalio.service import RPCError

from runtime import development_assessment as assessment
from runtime import development_control as control
from runtime.development_workflow import FiniteAssessment, FiniteDevelopment


ID = 'office-ap11-assessment-2'


class FakeHandle:
    def __init__(self, status='COMPLETED'):
        self.status = SimpleNamespace(name=status)

    async def describe(self):
        return self


class FakeClient:
    """Records what the operator path actually asked the engine to do."""

    def __init__(self, predecessor='COMPLETED'):
        self.started = []
        self.signals = []
        self.cancelled = []
        self.predecessor = predecessor

    def get_workflow_handle(self, name, **kwargs):
        from temporalio.client import WorkflowExecutionStatus
        from temporalio.service import RPCStatusCode
        status = WorkflowExecutionStatus.RUNNING if self.predecessor == 'RUNNING' else \
            WorkflowExecutionStatus.COMPLETED

        async def describe():
            # What the real engine answers for an execution its retention has removed, or on any other failure.
            if self.predecessor in ('NOT_FOUND', 'UNAVAILABLE'):
                raise RPCError('probe', getattr(RPCStatusCode, self.predecessor), b'')
            return SimpleNamespace(status=status)

        async def query(*args, **inner):
            # The readback operate() makes after every action. An assessment that has only just been
            # started has no phase yet, which is what a real engine would also report.
            return {'phase': None, 'children': [], 'final': None}

        async def signal(*args, **inner):
            self.signals.append(name)

        async def cancel(*args, **inner):
            self.cancelled.append(name)

        return SimpleNamespace(describe=describe, query=query, signal=signal, cancel=cancel, name=name)

    async def start_workflow(self, run, *args, **kwargs):
        self.started.append({'run': run, 'args': args, 'id': kwargs.get('id'),
                             'policy': kwargs.get('id_reuse_policy')})
        return SimpleNamespace()


class OperatorPathTests(unittest.TestCase):
    def context(self, directory, bound=True, control_value='active', approved=False,
                predecessor='COMPLETED', calls=(('step-36', 'final-review'),), result=True):
        """A whole isolated world: a scope directory, a configuration, and a fake engine."""
        root = Path(directory)
        context_dir = root / 'development-context'
        context_dir.mkdir(parents=True, exist_ok=True)
        decision = b'Owner decision: assess the same commitment once more.\n'
        review = json.dumps({'verdict': 'approved', 'blocking_findings': [], 'assesses': ID,
                             'after': assessment.APPLICATION,
                             'previous_outcome': 'whole_goal_not_approved',
                             'decision_sha256': __import__('hashlib').sha256(decision).hexdigest()}).encode()
        (context_dir / 'assessment-2.md').write_bytes(decision)
        (context_dir / 'assessment-2-review.json').write_bytes(review)
        development = {'contract_sha256': 'c' * 64}
        if bound:
            development['assessments'] = [{
                'id': ID, 'after': assessment.APPLICATION, 'previous_outcome': 'whole_goal_not_approved',
                'decision': 'assessment-2.md',
                'decision_sha256': __import__('hashlib').sha256(decision).hexdigest(),
                'review': 'assessment-2-review.json',
                'review_sha256': __import__('hashlib').sha256(review).hexdigest()}]
        config = {'directory': str(root), 'development': development,
                  'config_sha256': 'f' * 64, 'runtime_revision': 'a' * 40,
                  'office_revision': 'b' * 40}
        scope_dir = root / 'scope'
        (scope_dir / 'calls').mkdir(parents=True, exist_ok=True)
        for nonce, _role in calls:
            stage = scope_dir / 'calls' / nonce
            stage.mkdir(parents=True, exist_ok=True)
            if result:
                stage.joinpath('result.json').write_text(json.dumps({'answer': {'verdict': 'inconclusive'}}))
        recorded = []
        scope = SimpleNamespace(directory=scope_dir, expected='c' * 64,
                                controls=recorded,
                                control=lambda value, reason: recorded.append((value, reason)),
                                inspect=lambda: {'control': control_value,
                                                 'calls': [{'nonce': n, 'role': r} for n, r in calls],
                                                 'tasks': []})
        client = FakeClient(predecessor=predecessor)
        policy = SimpleNamespace(review=lambda answer: approved)
        return config, scope, client, policy

    def run_action(self, action, directory, **kwargs):
        """Through the TERMINAL PARSER, not by calling operate() directly."""
        config, scope, client, policy = self.context(directory, **kwargs)

        class FakeService:
            async def __aenter__(self_inner):
                return client

            async def __aexit__(self_inner, *exc):
                return False

        with patch.object(control, 'require_active_code', return_value=config), \
             patch.object(control, 'active_scope', return_value=(scope, config)), \
             patch.object(control, 'SharedService', FakeService), \
             patch.object(control, 'delegate', return_value=None), \
             patch.object(assessment.host, 'policy', return_value=policy), \
             patch.object(sys, 'argv', ['development_control', action, '--reason', 'probe']):
            # main() prints its readback. A test must not write on the suite's own stdout: a stdout that is
            # block buffered when piped flushes at exit, AFTER unittest's OK on stderr, which makes the
            # last line of a green run something other than OK.
            with contextlib.redirect_stdout(io.StringIO()):
                code = control.main()
        return code, client

    def test_the_terminal_parser_actually_offers_the_action(self):
        """Without this the entry is unreachable: the earlier build had operate() handling 'start' while the
        parser's choices did not include it, so the only reachable start was the interactive one."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                self.run_action('assess-typo', directory)
            code, client = self.run_action('assess', directory)
            self.assertEqual(code, 0)
            self.assertTrue(client.started, 'the parser reached the engine')

    def test_the_whole_path_starts_the_assessment_under_the_bound_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            _code, client = self.run_action('assess', directory)
            self.assertEqual(len(client.started), 1)
            started = client.started[0]
            self.assertIs(started['run'], FiniteAssessment.run, 'the direct assessment, not the build sequence')
            self.assertEqual(started['id'], ID, 'under the separately reviewed identity')
            self.assertEqual(started['policy'].name, 'REJECT_DUPLICATE',
                             'the duplicate-start refusal is not lifted for the new identity either')

    def test_the_build_sequence_can_never_run_under_an_assessment_identity(self):
        """The failure this pins: binding an assessment must not hand the interactive session, the A/B
        preparation, the implementations and the publication a second identity to run under.

        Driven through operate() rather than the parser, because there is deliberately no plain start action
        on the terminal: the build start is only reached by interactive-start, whose own branch launches a
        real session. The assess path above is the one the parser has to carry, and it is driven that way.
        """
        with tempfile.TemporaryDirectory() as directory:
            config, scope, client, policy = self.context(directory)

            class FakeService:
                async def __aenter__(self_inner):
                    return client

                async def __aexit__(self_inner, *exc):
                    return False

            with patch.object(control, 'require_active_code', return_value=config), \
                 patch.object(control, 'active_scope', return_value=(scope, config)), \
                 patch.object(control, 'SharedService', FakeService), \
                 patch.object(assessment.host, 'policy', return_value=policy):
                asyncio.run(control.operate('start'))                    # operate() itself prints nothing
            started = [s for s in client.started if s['run'] is FiniteDevelopment.run]
            self.assertTrue(started, 'the build start still exists')
            for entry in started:
                self.assertEqual(entry['id'], 'office-ap11',
                                 'pinned to the original application identity even with an assessment bound')

    def test_without_a_bound_reviewed_decision_the_action_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                self.run_action('assess', directory, bound=False)
            self.assertIn('No separately reviewed further assessment', str(caught.exception))

    def test_a_predecessor_that_is_still_running_refuses(self):
        """No concurrent writers on one scope."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                self.run_action('assess', directory, predecessor='RUNNING')
            self.assertIn('still running', str(caught.exception))

    def test_a_predecessor_the_engine_removed_by_retention_does_not_block_the_start(self):
        """The engine removes a closed execution one day after it closed, and then answers NOT_FOUND. The
        application this assessment follows completed on 2026-09-23, so without this the assessment could no
        longer be started at all a day later - although a removed execution is certainly not running."""
        with tempfile.TemporaryDirectory() as directory:
            code, client = self.run_action('assess', directory, predecessor='NOT_FOUND')
            self.assertEqual(code, 0)
            self.assertEqual([s['id'] for s in client.started], [ID])
            self.assertIs(client.started[0]['run'], FiniteAssessment.run)

    def test_any_other_engine_failure_on_the_predecessor_still_refuses(self):
        """Only NOT_FOUND means removed. An engine that cannot answer says nothing about whether it runs."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RPCError):
                self.run_action('assess', directory, predecessor='UNAVAILABLE')

    def test_an_approved_previous_review_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                self.run_action('assess', directory, approved=True)
            self.assertIn('nothing to re-assess', str(caught.exception))

    def test_a_scope_that_is_not_active_refuses_before_anything_is_started(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.run_action('assess', directory, control_value='paused')


class AssessmentWorkflowTests(unittest.TestCase):
    """What the started workflow actually does, without an engine."""

    def drive(self, results):
        workflow = FiniteAssessment()
        seen = []

        async def step(operation, **fields):
            seen.append(operation)
            return results[operation]

        workflow.step = step
        state = asyncio.run(workflow.run('c' * 64))
        return seen, state

    def test_it_verifies_the_preserved_delivery_before_the_counted_review(self):
        seen, state = self.drive({
            'preserved-delivery': {'control': 'active', 'integrated': ['handoff', 'reconciliation'],
                                   'complete': True},
            'final-review': {'approved': False, 'whole_goal_complete': False}})
        self.assertEqual(seen, ['preserved-delivery', 'final-review'],
                         'exactly two steps, in this order, and nothing else')
        self.assertEqual(state['phase'], 'whole_goal_not_approved')

    def test_it_never_runs_any_part_of_the_build_sequence(self):
        seen, _state = self.drive({
            'preserved-delivery': {'control': 'active', 'integrated': ['handoff', 'reconciliation'],
                                   'complete': True},
            'final-review': {'approved': True, 'whole_goal_complete': True}})
        for forbidden in ('interactive', 'propose', 'review', 'freeze', 'observe', 'diagnose'):
            self.assertNotIn(forbidden, seen)

    def test_an_incomplete_preserved_delivery_refuses_without_spending_a_review(self):
        seen, state = self.drive({
            'preserved-delivery': {'control': 'active', 'integrated': ['reconciliation'], 'complete': False}})
        self.assertEqual(seen, ['preserved-delivery'], 'the counted review was never reached')
        self.assertEqual(state['phase'], 'preserved_delivery_incomplete')

    def test_a_closed_scope_stops_it_before_the_review(self):
        seen, state = self.drive({'preserved-delivery': {'control_wait': True, 'control': 'stopped'}})
        self.assertEqual(seen, ['preserved-delivery'])
        self.assertEqual(state['phase'], 'stopped')

    def test_it_starts_no_children(self):
        _seen, state = self.drive({
            'preserved-delivery': {'control': 'active', 'integrated': ['handoff', 'reconciliation'],
                                   'complete': True},
            'final-review': {'approved': True, 'whole_goal_complete': True}})
        self.assertEqual(state['children'], [], 'a direct assessment publishes and implements nothing')


class PreservedDeliveryStepTests(unittest.TestCase):
    def test_the_step_makes_no_model_call_and_reserves_no_capacity(self):
        """It is answered before the capacity reservation, so asking what is already integrated cannot
        occupy AP10's budget and cannot spend a model process."""
        import ast
        import inspect as inspect_module
        from runtime import development_activity
        tree = ast.parse(inspect_module.getsource(development_activity.development_step).lstrip())
        body = tree.body[0].body
        def position(predicate):
            for index, node in enumerate(body):
                if predicate(ast.unparse(node)):
                    return index
            return None
        preserved = position(lambda text: "'preserved-delivery'" in text)
        capacity = position(lambda text: 'occupied =' in text)
        self.assertIsNotNone(preserved)
        self.assertIsNotNone(capacity)
        self.assertLess(preserved, capacity, 'answered before any capacity is reserved')
        branch = [node for node in body if isinstance(node, ast.If)
                  and "'preserved-delivery'" in ast.unparse(node.test)]
        self.assertEqual(len(branch), 1)
        called = {getattr(n.func, 'id', getattr(n.func, 'attr', None))
                  for n in ast.walk(branch[0]) if isinstance(n, ast.Call)}
        self.assertEqual(called & {'run_model', 'prepare', 'close', 'execute_activity'}, set(),
                         'the branch calls nothing that spends a model process or prepares one')

class InteractiveRoutesAreBuildOnlyTests(unittest.TestCase):
    """Found by the independent review of the decision, not by the host.

    With an assessment bound, the interactive-retry gate matched a paused assessment exactly - phase
    waiting_control or waiting_host_diagnosis with no children - so the interactive routes could have run
    against the very run whose preserved evidence the second assessment exists to examine unchanged.
    """

    def config(self, bound):
        development = {'contract_sha256': 'c' * 64}
        if bound:
            development['assessments'] = [{'id': ID}]          # identity() is patched; shape is irrelevant here
        return {'directory': '/nowhere', 'development': development}

    def test_an_interactive_route_is_refused_while_an_assessment_identity_is_bound(self):
        with patch.object(assessment, 'identity', return_value=ID):
            with self.assertRaises(ValueError) as caught:
                control.build_only(self.config(bound=True))
        self.assertIn('belongs to the application build', str(caught.exception))
        self.assertIn(ID, str(caught.exception), 'the refusal names the identity it found')

    def test_the_interactive_routes_are_unaffected_without_a_bound_assessment(self):
        with patch.object(assessment, 'identity', return_value='office-ap11'):
            control.build_only(self.config(bound=False))

    def test_both_interactive_entries_apply_the_guard_before_anything_else(self):
        """Before preflight, before a retry slot is bound, before the scope is resumed and before any
        signal - otherwise the refusal would arrive after the side effects it exists to prevent."""
        import ast
        import inspect as inspect_module
        source = inspect_module.getsource(control.main)
        tree = ast.parse(source.lstrip())
        for action in ('interactive-start', 'interactive-retry'):
            branch = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                      and repr(action) in ast.unparse(n.test)]
            self.assertEqual(len(branch), 1, action)
            body = [ast.unparse(n) for n in branch[0].body]
            guarded = next((i for i, text in enumerate(body) if 'build_only(config)' in text), None)
            self.assertIsNotNone(guarded, action + ' applies the guard')
            for marker in ('preflight(', 'prepare_retry(', "operate('resume'", 'signal(', 'execute(request)'):
                later = next((i for i, text in enumerate(body) if marker in text), None)
                if later is not None:
                    self.assertLess(guarded, later, action + ' guards before ' + marker)

    def test_the_diagnosis_signal_targets_the_build_parent(self):
        import ast
        import inspect as inspect_module
        tree = ast.parse(inspect_module.getsource(control.main).lstrip())
        handles = [ast.unparse(n.args[0]) for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and getattr(n.func, 'attr', None) == 'get_workflow_handle']
        self.assertTrue(handles)
        for handle in handles:
            self.assertEqual(handle, 'NAME', 'the interactive continuation signals the build parent only')

class CountedKeyNamespaceTests(unittest.TestCase):
    """Found by independent review, and invisible to every other test here.

    The counted call stages live in ONE scope. FiniteAssessment inherits the build workflow's sequence, so
    without its own prefix its first counted call would land on a key the original run already consumed, and
    prepare_call creates its stage with exist_ok=False - which is not a clean refusal but a repeating
    host-diagnosis loop that rebuilds the whole evidence package and writes spurious operator answers into
    the evidence being delivered.

    These drive the REAL step() key construction. The other tests replace step() wholesale or stub the
    engine, so none of them can see a key at all.
    """

    def keys(self, workflow_class, count=3):
        from runtime import development_workflow
        seen = []

        async def execute_activity(_activity, request, **kwargs):
            seen.append(request['key'])
            return {'control': 'active', 'integrated': ['handoff', 'reconciliation'], 'complete': True,
                    'approved': False, 'whole_goal_complete': False}

        instance = workflow_class()
        instance.expected = 'c' * 64
        with patch.object(development_workflow.workflow, 'execute_activity', execute_activity):
            async def drive():
                for _ in range(count):
                    await instance.step('control')
            asyncio.run(drive())
        return seen

    def test_the_assessment_uses_a_key_namespace_of_its_own(self):
        build = self.keys(FiniteDevelopment)
        assessment_keys = self.keys(FiniteAssessment)
        self.assertEqual(build, ['step-1', 'step-2', 'step-3'])
        self.assertEqual(set(build) & set(assessment_keys), set(),
                         'no counted key of the assessment can collide with one the build already consumed')
        for key in assessment_keys:
            self.assertTrue(key.startswith(ID + '-step-'), key)

    def test_the_prefix_names_the_identity_it_belongs_to(self):
        """So a stage on disk says which run consumed it, rather than only which sequence number."""
        self.assertEqual(FiniteAssessment.KEY_PREFIX, ID + '-step-')
        self.assertEqual(FiniteDevelopment.KEY_PREFIX, 'step-')

    def test_a_retried_key_after_an_activity_error_stays_in_the_namespace(self):
        """The error path advances the key by one and must not fall back to the build's prefix."""
        import ast
        import inspect as inspect_module
        from runtime import development_workflow
        source = inspect_module.getsource(development_workflow.FiniteDevelopment.step)
        assignments = [ast.unparse(n) for n in ast.walk(ast.parse(source.lstrip()))
                       if isinstance(n, ast.Assign) and "'key'" in ast.unparse(n)]
        self.assertTrue(assignments, 'the retry path assigns a fresh key')
        for text in assignments:
            self.assertIn('KEY_PREFIX', text, 'every key the step builds uses the run\'s own prefix')


class StopCoversTheRunningAssessmentTests(OperatorPathTests):
    """Owner precision: check the actually-possible state.

    A completed build parent does not need cancelling again - cancelling a closed execution is not a stop,
    it is an error the branch would then have to report. What must be covered is the assessment that is
    actually running, and nothing outside this scope.
    """

    def stopped(self, running):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            config, scope, client, policy = self.context(directory, predecessor='COMPLETED')
            client.running = set(running)

            original = client.get_workflow_handle

            def handle(name, **kwargs):
                from temporalio.client import WorkflowExecutionStatus
                inner = original(name, **kwargs)

                async def describe():
                    return SimpleNamespace(
                        status=WorkflowExecutionStatus.RUNNING if name in client.running
                        else WorkflowExecutionStatus.COMPLETED)

                inner.describe = describe
                return inner

            client.get_workflow_handle = handle

            class FakeService:
                async def __aenter__(self_inner):
                    return client

                async def __aexit__(self_inner, *exc):
                    return False

            with patch.object(control, 'require_active_code', return_value=config), \
                 patch.object(control, 'active_scope', return_value=(scope, config)), \
                 patch.object(control, 'SharedService', FakeService), \
                 patch.object(assessment.host, 'policy', return_value=policy):
                asyncio.run(control.operate('stop', 'probe'))
            return client.cancelled

    def test_a_running_assessment_is_cancelled(self):
        self.assertEqual(self.stopped({ID}), [ID])

    def test_a_closed_build_parent_is_not_cancelled_again(self):
        self.assertEqual(self.stopped(set()), [], 'nothing running, nothing cancelled')

    def test_a_still_running_build_parent_is_reached_even_with_an_assessment_bound(self):
        """The identity that happens to be current must not decide what a stop can reach."""
        self.assertEqual(self.stopped({'office-ap11'}), ['office-ap11'])

    def test_every_identity_of_this_commitment_is_considered(self):
        self.assertEqual(sorted(self.stopped({'office-ap11', ID})), sorted(['office-ap11', ID]))


if __name__ == '__main__':
    unittest.main()
