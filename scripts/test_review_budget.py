"""The explicit review budget, its derived frames and the bounded continuation across a Runtime revision.

Office decision RUNTIME-GRANSKNINGSBUDGET-ACCEPT-20260925. Measured 2026-09-25 from preserved traces: three office reviews
were still reading the candidate when the fixed 180 s model bound ended them (exit 124, process group removed), and
complete reviews of the same candidates took 391-488 s. These checks drive the real call sites - the task validation, the
review activity, the host's attempt bound, the workflow's review step and the operator's continuation - with fakes only
where an engine, a model or the network would be. Offline: nothing connects to a service.
"""
import asyncio
import contextlib
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import activities, attempt, development_binding as binding, run, task as task_module, targets
from runtime import workflow as workflow_module
from runtime.development_scope import ScopeClosed
from runtime.integration import digest
from runtime.workflow import DevelopmentTask

ACCEPTED, ACTIVE = 'c' * 40, 'e' * 40


def office_task(**extra):
    return {'id': 'office-budget-1', 'target': targets.OFFICE, 'base': 'a' * 40, 'allowed_paths': ['tools/x.py'],
            'attempt_seconds': 3000, 'automatic_retries': 0, 'steps': [{'provider': 'claude', 'prompt': 'p'}],
            'acceptance_sha256': 'b' * 64, 'runtime_revision': ACCEPTED, 'review_provider': 'claude', **extra}


class BudgetTests(unittest.TestCase):
    def test_an_accepted_task_may_carry_a_budget_inside_the_frame_and_nothing_else(self):
        for seconds in (180, 720, 900):
            self.assertEqual(task_module.validate(office_task(review_seconds=seconds))['review_seconds'], seconds)
        for seconds in (179, 901, 0, True, 720.0, '720', None):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                task_module.validate(office_task(review_seconds=seconds))
        development = office_task(review_seconds=720, allowed_paths=['tools/a.py', 'tools/b.py'], attempt_seconds=480,
                                  development={'contract_sha256': 'f' * 64, 'work': 'w'})
        with self.assertRaisesRegex(ValueError, 'own review bound'):
            task_module.validate(development)

    def test_an_earlier_task_keeps_its_digest_and_its_former_bound(self):
        legacy = office_task()
        self.assertNotIn('review_seconds', task_module.validate(dict(legacy)))
        self.assertEqual(digest(task_module.validate(dict(legacy))), digest(legacy))
        self.assertEqual(binding.model_seconds(legacy, 'review'), 180)
        self.assertEqual(binding.model_seconds({'attempt_seconds': 120}, 'review'), 120)

    def test_one_derivation_gives_every_frame(self):
        self.assertEqual(binding.review_frames(180), {'model': 180, 'host': 195, 'activity': 210}, 'exactly the former frames')
        self.assertEqual(binding.review_frames(720), {'model': 720, 'host': 735, 'activity': 750})
        observed = binding.review_observation(720)
        # The observation covers the longest admission wait (activity plus 60 s before the watch run, then the whole
        # watch run and two timer periods) and then the review activity itself.
        self.assertGreaterEqual(observed, (750 + 60 + 1200 + 60) + 750)
        self.assertEqual(binding.WATCH_RUN_SECONDS, 1200)

    def test_the_watch_run_bound_is_the_schedule_timeout(self):
        from runtime import obligation
        definition = obligation.definition({'config_sha256': 'x' * 64})
        self.assertEqual(definition.action.execution_timeout, timedelta(seconds=binding.WATCH_RUN_SECONDS))

    def test_a_continuation_budget_wins_over_the_task_and_the_development_profile_keeps_its_own(self):
        self.assertEqual(binding.model_seconds(office_task(review_seconds=720), 'review'), 720)
        self.assertEqual(binding.model_seconds(office_task(review_seconds=720), 'review', 600), 600)
        self.assertEqual(binding.model_seconds(office_task(), 'review', 900), 900)
        with self.assertRaises(ValueError):
            binding.model_seconds(office_task(), 'review', 901)
        with self.assertRaises(ScopeClosed):
            binding.model_seconds(office_task(development={'contract_sha256': 'f' * 64, 'work': 'w'}), 'review', 720)


class AttemptBoundTests(unittest.TestCase):
    """The host's own check on the call: a review is bounded by its budget, an implementation by its attempt time."""
    def check(self, task, seconds, role='review', bound=None):
        with patch.object(attempt, 'load', return_value=task):
            try:
                attempt.execute(task['id'], 1, 'p', seconds, task_digest=digest(task), role=role,
                                workspace_name='not-a-commit', provider='claude', binding=bound)
            except ValueError as error:
                return str(error)

    def test_a_bound_review_may_exceed_the_implementation_time_but_not_the_frame(self):
        short = office_task(attempt_seconds=600)
        self.assertIn('host-prepared immutable candidate', self.check(short, 720, bound={'review_seconds': 720}),
                      'past the bound check')
        self.assertIn('invocation limit', self.check(short, 901, bound={'review_seconds': 901}))
        self.assertIn('invocation limit', self.check(short, 601, role='implementation'))

    def test_an_unbound_review_keeps_its_former_ceiling(self):
        short = office_task(attempt_seconds=600)
        self.assertIn('invocation limit', self.check(short, 720), 'without a binding the accepted attempt time bounds it')
        self.assertIn('host-prepared immutable candidate', self.check(short, 180))

    def test_a_binding_must_carry_exactly_the_budget_of_its_review(self):
        task = office_task()
        self.assertIn('exactly its budget', self.check(task, 720, bound={'review_seconds': 600}))
        self.assertIn('exactly its budget', self.check(task, 720, role='implementation', bound={'review_seconds': 720}))
        self.assertIn('host-prepared immutable candidate', self.check(task, 720, bound={'review_seconds': 720}))

    def records(self, bound, seconds):
        """The launch and result records of one review whose provider launch is refused, as test_claude_roles measures."""
        task = office_task()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = root / 'state'; workspace = state / 'commit-1'; workspace.mkdir(parents=True)
            (workspace / 'REVIEW_SCHEMA.json').write_text('{}')
            evidence = root / 'evidence'; evidence.mkdir()
            with patch.object(attempt, 'ROOT', root), patch.object(attempt, 'load', return_value=task), \
                 patch.object(attempt, 'task_directory', return_value=state), \
                 patch.object(attempt, 'evidence_directory', return_value=evidence), \
                 patch.object(attempt, 'claude_command', return_value=['pinned-claude', '--tools', 'Read']), \
                 patch.object(attempt, 'require_subscription', return_value={'subscriptionType': 'max'}), \
                 patch.object(attempt, 'environment', return_value={}), \
                 patch.object(attempt, 'reserve_task_call', return_value=None), \
                 patch.object(attempt.subprocess, 'Popen', side_effect=OSError('provider launch refused in this test')), \
                 patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                code = attempt.execute(task['id'], 1, 'p', seconds, task_digest=digest(task), role='review',
                                       workspace_name='commit-1', provider='claude', binding=bound)
            return (code, json.loads((evidence / 'review-1/launch.json').read_text()),
                    json.loads((evidence / 'review-1/result.json').read_text()))

    def test_the_round_records_carry_its_binding_and_an_unbound_round_records_none(self):
        bound = {'accepted_runtime_revision': ACCEPTED, 'runtime_revision': ACTIVE, 'config_sha256': None, 'review_seconds': 720}
        code, launch, result = self.records(bound, 720)
        self.assertEqual((launch['binding'], result['binding'], launch['seconds_limit']), (bound, bound, 720))
        self.assertEqual(code, 1); self.assertFalse(result['provider_completed'], 'a refused launch is never a review')
        _, launch, result = self.records(None, 180)
        self.assertNotIn('binding', launch); self.assertNotIn('binding', result)


class ReviewActivityTests(unittest.TestCase):
    """The real review activity, with the model call, the Git read and the watch observation replaced."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        (Path(self.temp.name) / 'commit-1').mkdir()

    def review(self, task, request=None, available=True, completed=False):
        seen = {'before': [], 'inspect': []}

        def invoke(call):
            seen['call'] = call
            if completed:
                return {'provider_completed': True, 'thread_id': 'review-run-1', 'exit_code': 0}
            return {'provider_completed': False, 'exit_code': 124, 'interrupted': 'deadline'}

        async def inspect(seconds):
            seen['inspect'].append(seconds)
            if available == 'error':
                raise OSError('no engine here')
            return {'available': available, 'wait_seconds': 30, 'reason': 'fixture'}
        with patch.object(activities, 'load', return_value=task), \
             patch.object(activities, 'before_activity', side_effect=lambda t, s: seen['before'].append(s)), \
             patch.object(activities, 'inspect_capacity', side_effect=inspect), \
             patch.object(activities, 'revision', return_value=ACTIVE), \
             patch.object(activities, 'task_directory', return_value=Path(self.temp.name)), \
             patch.object(activities, 'evidence_directory', return_value=Path(self.temp.name) / 'evidence'), \
             patch.object(activities, 'git', return_value='d' * 40), \
             patch.object(activities, 'read_regular', return_value=b'accepted brief'), \
             patch.object(activities, 'invoke', side_effect=invoke), \
             patch.dict(os.environ, {'NR_CONFIG_SHA256': 'f' * 64}):
            subject = {'candidate': 'd' * 40, 'task_id': task['id'], 'task_sha256': digest(task),
                       'acceptance_sha256': task['acceptance_sha256']}
            outcome = activities.review_candidate({'task_id': task['id'], 'task_digest': digest(task),
                                                   'workspace_name': 'commit-1', 'subject': subject,
                                                   **(request or {})})
        return seen, outcome

    def test_an_unbudgeted_review_keeps_exactly_its_former_path(self):
        seen, outcome = self.review(office_task())
        self.assertEqual(seen['call']['seconds'], 180)
        self.assertEqual(seen['before'], [210], 'the former admission path with the former envelope')
        self.assertEqual(seen['inspect'], [], 'no watch observation for a review that did not grow')
        self.assertNotIn('binding', seen['call'])
        self.assertEqual(set(outcome), {'terminal_status', 'provider_result'}, 'the former incomplete record, nothing added')

    def test_a_budgeted_review_passes_admission_with_its_whole_activity_and_is_bound(self):
        seen, outcome = self.review(office_task(review_seconds=720))
        self.assertEqual(seen['inspect'], [750], 'the whole activity is what must fit before the watch')
        self.assertEqual(seen['before'], [])
        self.assertEqual(seen['call']['seconds'], 720, 'the budget is what the model process is given')
        expected = {'accepted_runtime_revision': ACCEPTED, 'runtime_revision': ACTIVE, 'config_sha256': 'f' * 64,
                    'review_seconds': 720}
        self.assertEqual(seen['call']['binding'], expected)
        self.assertEqual(outcome['binding'], expected, 'an incomplete round still says what it was bound to')

    def test_a_crossing_without_a_budget_keeps_the_former_admission_and_is_bound(self):
        seen, outcome = self.review(office_task(), {'review_number': 2, 'change_reason': 'new release',
                                                    'runtime': {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': 'f' * 64}})
        self.assertEqual((seen['before'], seen['inspect'], seen['call']['seconds']), ([210], [], 180))
        self.assertEqual(seen['call']['binding'], {'accepted_runtime_revision': ACCEPTED, 'runtime_revision': ACTIVE,
                                                   'config_sha256': 'f' * 64, 'review_seconds': 180})
        self.assertEqual(outcome['binding']['review_seconds'], 180)

    def test_a_completed_bound_round_writes_its_binding_into_the_decision(self):
        for task, request, expected in ((office_task(review_seconds=720), {}, 720), (office_task(), {}, None)):
            with self.subTest(expected=expected):
                evidence = Path(self.temp.name) / 'evidence' / ('review-1')
                if evidence.exists():
                    for child in evidence.iterdir():
                        child.unlink()
                evidence.mkdir(parents=True, exist_ok=True)
                with patch.object(activities, 'verdict', return_value={'verdict': 'approved', 'blocking_findings': [], 'summary': 's'}):
                    seen, outcome = self.review(task, request, completed=True)
                decision = json.loads((evidence / 'decision.json').read_text())
                self.assertEqual(decision.get('binding', {}).get('review_seconds'), expected)
                self.assertEqual(outcome.get('binding', {}).get('review_seconds'), expected)

    def test_a_continuation_budget_reaches_the_call(self):
        seen, _ = self.review(office_task(), {'review_seconds': 600, 'review_number': 2, 'change_reason': 'budget',
                                              'runtime': {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': 'f' * 64}})
        self.assertEqual((seen['call']['seconds'], seen['inspect']), (600, [630]))
        self.assertEqual(seen['call']['binding']['runtime_revision'], ACTIVE)

    def test_no_capacity_or_an_unreadable_watch_starts_nothing(self):
        for available in (False, 'error'):
            with self.subTest(available=available):
                seen, outcome = self.review(office_task(review_seconds=720), available=available)
                self.assertTrue(outcome['capacity_wait'])
                self.assertNotIn('call', seen, 'the model process was never started')

    def test_a_round_sent_under_another_revision_refuses_before_any_call(self):
        for runtime in ({'accepted': ACCEPTED, 'used': 'f' * 40, 'config_sha256': 'f' * 64},
                        {'accepted': 'f' * 40, 'used': ACTIVE, 'config_sha256': 'f' * 64},
                        {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': '0' * 64}, 'not a binding'):
            with self.subTest(runtime=runtime), self.assertRaisesRegex(ValueError, 'another Runtime revision'):
                self.review(office_task(review_seconds=720), {'runtime': runtime})


class CallSiteTests(unittest.TestCase):
    """Where the derived frames are spent: the host's wait on the model process and the operator's outer bound."""
    def test_the_host_waits_exactly_the_derived_host_frame(self):
        seen = {}

        class Process:
            returncode = 0
            def communicate(self, data, timeout):
                seen['timeout'] = timeout
                return b'{"provider_completed": false}', b''
        with patch.object(activities.subprocess, 'Popen', return_value=Process()), \
             patch.object(activities, 'stop_group', return_value=True):
            activities.invoke({'seconds': 720, 'number': 1})
        self.assertEqual(seen['timeout'], binding.review_frames(720)['host'])

    def test_the_operator_waits_on_the_derived_outer_bound(self):
        seen = {}

        async def fake_main(task_file, **options):
            return 0

        async def fake_wait_for(awaitable, timeout):
            seen['timeout'] = timeout
            return await awaitable
        with patch.object(run, 'main', fake_main), patch.object(run, 'operator_bound', return_value=4321), \
             patch.object(run.asyncio, 'wait_for', fake_wait_for):
            self.assertEqual(asyncio.run(run.bounded('task.json', resume=True)), 0)
        self.assertEqual(seen['timeout'], 4321)


class Stop(Exception):
    pass


class FakeWorkflow:
    """Stands in for temporalio.workflow inside the real DevelopmentTask code: records every activity and timer."""
    def __init__(self, results, on_wait=None):
        self.results, self.on_wait, self.calls, self.sleeps = list(results), on_wait, [], []

    async def execute_activity(self, function, request, **options):
        self.calls.append((function.__name__, json.loads(json.dumps(request)), options))
        if not self.results:
            raise Stop()
        return self.results.pop(0)

    async def wait_condition(self, predicate):
        if self.on_wait is not None:
            self.on_wait()
        if not predicate():
            raise Stop()

    async def sleep(self, seconds):
        self.sleeps.append(seconds)


def implementation():
    return {'provider_completed': True, 'phase_acceptance_passed': True, 'candidate': 'd' * 40, 'thread_id': 'impl-1',
            'evidence': 'evidence/runs/office-budget-1/attempt-1', 'workspace_name': 'commit-1',
            'candidate_files_sha256': {'tools/x.py': '0' * 64}}


def approved(task, candidate='d' * 40, run_id='review-1', verdict='approved', findings=()):
    return {'task_id': task['id'], 'task_sha256': digest(task), 'candidate': candidate, 'acceptance_sha256': task['acceptance_sha256'],
            'scope': 'whole_task', 'terminal_status': 'completed', 'verdict': verdict, 'blocking_findings': list(findings),
            'summary': 's', 'reviewer_run': run_id}


class WorkflowTests(unittest.TestCase):
    """The real workflow code, driven without an engine: the review request and its activity envelope."""
    def drive(self, task, results, on_wait=None):
        fake = FakeWorkflow(results, on_wait)
        instance = DevelopmentTask()
        with patch.object(workflow_module, 'workflow', fake):
            try:
                asyncio.run(instance.run(task))
            except Stop:
                pass
        return fake, instance

    def reviews(self, fake):
        return [(request, options) for name, request, options in fake.calls if name == 'review_candidate']

    def test_an_unbudgeted_task_sends_exactly_the_former_review_request(self):
        task = office_task()
        fake, instance = self.drive(task, [implementation(), approved(task), {'merged': True}])
        (request, options), = self.reviews(fake)
        self.assertEqual(set(request), {'task_id', 'task_digest', 'subject', 'workspace_name'})
        self.assertEqual(options['start_to_close_timeout'], timedelta(seconds=210))
        self.assertEqual(instance.phase, 'completed')

    def test_a_budgeted_task_waits_on_a_native_timer_then_reviews_inside_its_derived_envelope(self):
        task = office_task(review_seconds=720)
        wait = {'capacity_wait': True, 'capacity': {'available': False, 'wait_seconds': 30, 'reason': 'watch soon'}}
        fake, instance = self.drive(task, [implementation(), wait, approved(task), {'merged': True}])
        first, second = self.reviews(fake)
        self.assertEqual(fake.sleeps, [30], 'the wait is a native timer, not a sleeping activity slot')
        for request, options in (first, second):
            self.assertEqual(request['review_seconds'], 720)
            self.assertEqual(options['start_to_close_timeout'], timedelta(seconds=750))
        self.assertEqual(len(instance.reviews), 1, 'a capacity wait is not a review')
        self.assertEqual(instance.phase, 'completed')

    def test_a_stopped_review_continues_with_its_budget_and_binding_and_only_as_review_only(self):
        task = office_task()
        runtime = {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': 'f' * 64}
        holder = {}

        def operator():
            instance = holder['instance']
            base = {'task_sha256': digest(task), 'candidate': 'd' * 40, 'review_number': 1, 'expected_attempt': 1,
                    'action': 'review_only', 'reason': 'the fixed bound stopped a working review'}
            for refused in ({**base, 'review_seconds': 901}, {**base, 'review_seconds': 720, 'action': 'repair'},
                            {**base, 'runtime': {**runtime, 'accepted': 'f' * 40}}, {**base, 'runtime': 'free text'}):
                instance.continue_after_review(refused)
                self.assertIsNone(instance.review_request, refused)
            instance.continue_after_review({**base, 'review_seconds': 720, 'runtime': runtime})

        original = DevelopmentTask.__init__

        def remember(instance):
            original(instance); holder['instance'] = instance
        stopped = {'terminal_status': 'incomplete', 'provider_result': {'exit_code': 124, 'interrupted': 'deadline'}}
        with patch.object(DevelopmentTask, '__init__', remember):
            fake, instance = self.drive(task, [implementation(), stopped, approved(task), {'merged': True}], operator)
        first, second = self.reviews(fake)
        self.assertEqual(first[1]['start_to_close_timeout'], timedelta(seconds=210))
        self.assertEqual((second[0]['review_seconds'], second[0]['runtime']), (720, runtime))
        self.assertEqual(second[0]['subject'], first[0]['subject'], 'the same frozen candidate, no new implementation')
        self.assertEqual(second[1]['start_to_close_timeout'], timedelta(seconds=750))
        self.assertEqual([name for name, _, _ in fake.calls].count('execute_claude'), 1)
        self.assertEqual(len(instance.reviews), 2, 'the stopped round is kept')
        self.assertEqual(instance.phase, 'completed')


    def test_a_repair_keeps_its_former_bounds_even_when_the_workflow_waits_for_repair(self):
        task = office_task()
        holder = {}

        def operator():
            instance = holder['instance']
            self.assertEqual(instance.review_recovery, 'repair', 'a concrete rejection is waiting for repair')
            base = {'task_sha256': digest(task), 'candidate': 'd' * 40, 'review_number': 1, 'expected_attempt': 1,
                    'action': 'repair', 'reason': 'repair the named violation'}
            for refused in ({**base, 'review_seconds': 720},
                            {**base, 'runtime': {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': 'f' * 64}}):
                instance.continue_after_review(refused)
                self.assertIsNone(instance.review_request, refused)
            instance.continue_after_review(base)

        original = DevelopmentTask.__init__

        def remember(instance):
            original(instance); holder['instance'] = instance
        repaired = {**implementation(), 'candidate': 'e' * 40, 'thread_id': 'impl-2', 'workspace_name': 'commit-2',
                    'candidate_files_sha256': {'tools/x.py': '1' * 64}}
        rejected = approved(task, verdict='rejected', findings=['the named violation'])
        with patch.object(DevelopmentTask, '__init__', remember):
            fake, instance = self.drive(task, [implementation(), rejected, repaired,
                                               approved(task, candidate='e' * 40, run_id='review-2'), {'merged': True}], operator)
        first, second = self.reviews(fake)
        self.assertNotIn('review_seconds', second[0], 'the repair did not bring a budget')
        self.assertEqual(second[1]['start_to_close_timeout'], timedelta(seconds=210))
        self.assertEqual(instance.phase, 'completed')


class RevisionTests(unittest.TestCase):
    def binding(self, used, review_retry, config=True, environment=True, descends=True):
        active = {'config_sha256': 'f' * 64} if config else None
        env = {'NR_CONFIG_SHA256': 'f' * 64} if environment else {}
        with patch.object(run, 'installed', return_value=active), patch.object(run, 'revision', return_value=used), \
             patch.object(run, 'git', return_value=used), patch.object(run, 'descends', return_value=descends), \
             patch.dict(os.environ, env, clear=False):
            if not environment:
                os.environ.pop('NR_CONFIG_SHA256', None)
            return run.revision_binding(office_task(), review_retry)

    def test_the_accepted_revision_binds_as_before(self):
        self.assertEqual(self.binding(ACCEPTED, False), {'accepted': ACCEPTED, 'used': ACCEPTED, 'config_sha256': 'f' * 64})

    def test_only_a_review_only_continuation_under_the_active_descending_release_may_cross(self):
        self.assertEqual(self.binding(ACTIVE, True)['used'], ACTIVE)
        for label, kwargs in (('not review-only', {'review_retry': False}), ('no installed release', {'config': False}),
                              ('not run as the release', {'environment': False}), ('not a descendant', {'descends': False})):
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'unchanged accepted Runtime revision'):
                self.binding(ACTIVE, **{'review_retry': True, **kwargs})

    def test_descent_is_read_from_real_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def g(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
            g('init', '-q'); g('config', 'user.name', 'T'); g('config', 'user.email', 't@invalid.example')
            g('commit', '-q', '--allow-empty', '-m', 'one'); first = g('rev-parse', 'HEAD')
            g('commit', '-q', '--allow-empty', '-m', 'two'); second = g('rev-parse', 'HEAD')
            with patch.object(run, 'ROOT', root):
                self.assertTrue(run.descends(first, second))
                self.assertFalse(run.descends(second, first))
                self.assertFalse(run.descends('main', second))

    def test_the_observation_and_the_outer_bound_follow_the_budget(self):
        legacy, budgeted = office_task(), office_task(review_seconds=720)
        self.assertEqual(run.observation_seconds(legacy), 3000 + 420, 'exactly the former bound')
        self.assertEqual(run.observation_seconds(legacy, 'retry'), 3000 + 420)
        self.assertEqual(run.observation_seconds(legacy, 'retry', 720), binding.review_observation(720))
        self.assertEqual(run.observation_seconds(budgeted, 'retry'), binding.review_observation(720))
        self.assertEqual(run.observation_seconds(budgeted), 3000 + 420 - 210 + binding.review_observation(720))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'task.json'
            path.write_text(json.dumps(legacy))
            self.assertEqual(run.operator_bound(path, {}), 4200, 'the former outer bound without a budget')
            path.write_text(json.dumps(budgeted))
            self.assertGreater(run.operator_bound(path, {}), run.observation_seconds(budgeted))
            path.write_text(json.dumps(legacy))
            self.assertGreater(run.operator_bound(path, {'review_retry': 'r', 'review_seconds': 900}), binding.review_observation(900))

    def test_observation_goes_on_through_a_capacity_wait_and_stops_where_it_stopped_before(self):
        self.assertFalse(run.settled({'phase': 'waiting_capacity', 'attempts': 1}))
        self.assertFalse(run.settled({'phase': 'reviewing', 'attempts': 1}))
        self.assertTrue(run.settled({'phase': 'waiting_review', 'attempts': 1}))
        self.assertTrue(run.settled({'phase': 'completed', 'attempts': 1}))
        self.assertFalse(run.settled({'phase': 'waiting_review', 'attempts': 1, 'reviews': [{}]}, required_reviews=2))
        self.assertTrue(run.settled({'phase': 'waiting_diagnosis', 'attempts': 2}, required_attempt=2, required_reviews=5))
        self.assertFalse(run.settled({'phase': 'waiting_diagnosis', 'attempts': 1}, required_attempt=2))

    def test_a_budget_belongs_to_a_review_only_continuation(self):
        for options in ({'resume': True, 'review_seconds': 720}, {'resume': True, 'review_repair': 'x', 'review_seconds': 720},
                        {'resume': True, 'review_retry': 'x', 'review_seconds': 901}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                asyncio.run(run.main('unused.json', **options))


class ContinuationSignalTests(unittest.TestCase):
    """The operator's real continuation path up to the signal, with the service replaced by a recording fake."""
    def continue_(self, used, review_seconds):
        task = office_task()
        prior = {'phase': 'waiting_review', 'review_recovery': 'review_only', 'review_number': 1, 'attempts': 1,
                 'results': [{'candidate': 'd' * 40}], 'reviews': [{}]}
        after = {**prior, 'reviews': [{}, {}]}
        sent = []

        class Handle:
            def __init__(self):
                self.states = [prior, after]
            async def query(self, _):
                return self.states.pop(0) if len(self.states) > 1 else self.states[0]
            async def signal(self, method, payload):
                sent.append((method.__name__, payload))
            async def fetch_history(self):
                return type('History', (), {'events': []})()

        handle = Handle()

        class Client:
            def get_workflow_handle(self, _):
                return handle

        class Service:
            migrated = False
            async def __aenter__(self):
                return Client()
            async def __aexit__(self, *exc):
                return False
        # The operator reports its evidence relative to the host root, so the fixture lives under it.
        with tempfile.TemporaryDirectory(dir=run.ROOT / '.runtime') as directory:
            path = Path(directory) / 'task.json'; path.write_text(json.dumps(task))
            with patch.object(run, 'load', return_value=task), patch.object(run, 'check_unfinished_writers'), \
                 patch.object(run, 'evidence_directory', return_value=Path(directory) / 'evidence'), \
                 patch.object(run, 'installed', return_value={'config_sha256': 'f' * 64}), \
                 patch.object(run, 'revision', return_value=used), patch.object(run, 'descends', return_value=True), \
                 patch.object(run, 'SharedService', Service), patch.dict(os.environ, {'NR_CONFIG_SHA256': 'f' * 64}), \
                 patch.object(run, 'observation_seconds', wraps=run.observation_seconds) as observed:
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    code = asyncio.run(run.main(str(path), resume=True, review_retry='the fixed bound stopped a working review',
                                                review_seconds=review_seconds))
                resume = json.loads(next((Path(directory) / 'evidence/observations').iterdir()).joinpath('resume.json').read_text())
        observed.assert_called_once_with(task, 'the fixed bound stopped a working review', review_seconds)
        self.assertEqual(json.loads(printed.getvalue())['phase'], 'waiting_review')
        self.assertEqual(code, 1, 'observed until the new round is recorded; not completed here')
        (name, payload), = sent
        self.assertEqual(name, 'continue_after_review')
        self.assertEqual(payload['task_sha256'], digest(task), 'the frozen input is not rewritten')
        self.assertEqual((payload['action'], payload['review_number']), ('review_only', 1))
        return payload, resume

    def test_a_crossing_round_is_bound_to_both_revisions_the_release_and_the_budget(self):
        payload, resume = self.continue_(ACTIVE, 720)
        self.assertEqual(payload['runtime'], {'accepted': ACCEPTED, 'used': ACTIVE, 'config_sha256': 'f' * 64})
        self.assertEqual(payload['review_seconds'], 720)
        self.assertEqual((resume['review_seconds'], resume['runtime_binding']['used']), (720, ACTIVE), 'the receipt says it too')

    def test_a_crossing_without_a_budget_is_bound_and_keeps_the_former_bound(self):
        payload, _ = self.continue_(ACTIVE, None)
        self.assertEqual(payload['runtime']['used'], ACTIVE)
        self.assertNotIn('review_seconds', payload)

    def test_a_budget_under_the_accepted_revision_is_bound_too(self):
        payload, _ = self.continue_(ACCEPTED, 720)
        self.assertEqual((payload['runtime']['used'], payload['review_seconds']), (ACCEPTED, 720))

    def test_an_ordinary_continuation_is_sent_exactly_as_before(self):
        payload, _ = self.continue_(ACCEPTED, None)
        self.assertEqual(set(payload), {'task_sha256', 'candidate', 'review_number', 'expected_attempt', 'action', 'reason'})


if __name__ == '__main__':
    unittest.main()
