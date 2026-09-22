"""Recovery from a host failure inside a running child: the reviewer's bound, the honest gate message, the host's own
answer and what the next diagnosis is shown.

Measured 2026-09-22 on the real application: the candidate passed the frozen host recipe, then the separate review was cut
off by the host guardian at 182.2 s against a 180 s model bound (exit 124, interrupted deadline) and produced no verdict.
The gate refused it as "Stale or mismatched evidence: task_id", which describes an identity mismatch and not the host
failure that happened; the diagnosis then held, honestly, because nothing it could see had changed; and the only way to
answer a host diagnosis was interactive-retry, which spends one of the counted interactive starts.
"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import development_host as host
from runtime.development_binding import activity_seconds, model_seconds, REVIEW_MODEL_SECONDS, DEVELOPMENT_REVIEW_MODEL_SECONDS
from runtime.integration import GateClosed, require_gate, digest
from runtime.snapshot import read_regular


def readable(directory, name, **kw):
    """The real read where the fixture wrote a file (the host's own answers and the contract are parsed as JSON);
    a named placeholder for the release material this test does not stage."""
    return read_regular(directory, name, **kw) if (Path(directory) / name).is_file() else b'delivered ' + name.encode()


def bound_task(**extra):
    return {'id': 'ap11-step-5', 'target': 'Nortropic/nortropic-projektkontor', 'base': 'a' * 40, 'attempt_seconds': 480,
            'allowed_paths': ['tools/development_result.py', 'tools/test_development_result.py'], 'automatic_retries': 0,
            'acceptance_sha256': 'b' * 64, 'steps': [{'provider': 'claude', 'prompt': 'p'}],
            'development': {'contract_sha256': 'c' * 64, 'work': 'reconciliation'}, **extra}


class ReviewBoundTests(unittest.TestCase):
    def test_the_review_model_bound_fits_inside_the_activity_envelope_that_already_applied(self):
        task = bound_task()
        envelope = activity_seconds(task, 'review'); bound = model_seconds(task, 'review')
        self.assertEqual(envelope, 360, 'the activity envelope is unchanged')
        self.assertEqual(bound, DEVELOPMENT_REVIEW_MODEL_SECONDS)
        self.assertGreater(bound, 182.2, 'the measured review needed more than the old bound')
        self.assertLessEqual(bound + 60, envelope, 'the host keeps time for its own work inside the envelope')

    def test_a_task_without_the_finite_binding_keeps_its_former_bound_exactly(self):
        legacy = {'id': 'runtime-evidence-index-1', 'attempt_seconds': 300}
        self.assertEqual(model_seconds(legacy, 'review'), REVIEW_MODEL_SECONDS)
        self.assertIsNone(activity_seconds(legacy, 'review'), 'and its envelope is still the caller default')
        self.assertEqual(model_seconds({'attempt_seconds': 120}, 'review'), 120, 'a shorter task still bounds its own review')

    def test_only_the_review_bound_is_derived_here(self):
        with self.assertRaises(ValueError):
            model_seconds(bound_task(), 'implementation')


class ReviewActivityTests(unittest.TestCase):
    """The bound only matters where it is actually spent. Measured 2026-09-22: the review process was killed at
    182.2 s against a 180 s bound, so this exercises the real activity and reads the seconds it hands the call."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / 'candidate'; self.workspace.mkdir(parents=True)

    def review(self, task):
        from runtime import activities
        seen = {}
        def invoke(request):
            seen.update(request); return {'provider_completed': False, 'exit_code': 124, 'interrupted': 'deadline', 'elapsed_seconds': 182.201}
        with patch.object(activities, 'load', return_value=task), \
             patch.object(activities, 'before_activity', side_effect=lambda t, seconds: seen.update(envelope=seconds) or None), \
             patch.object(activities, 'task_directory', return_value=Path(self.temp.name)), \
             patch.object(activities, 'git', return_value='c' * 40), \
             patch.object(activities, 'read_regular', return_value=b'accepted brief'), \
             patch.object(activities, 'invoke', side_effect=invoke):
            outcome = activities.review_candidate({'task_id': task['id'], 'task_digest': digest(task), 'workspace_name': 'candidate',
                                                   'subject': {'candidate': 'c' * 40}})
        return seen, outcome

    def test_the_raised_bound_reaches_the_real_review_call_and_a_cut_off_is_still_reported_as_incomplete(self):
        seen, outcome = self.review(bound_task())
        self.assertEqual(seen['seconds'], DEVELOPMENT_REVIEW_MODEL_SECONDS, 'the derived bound is what the call is given')
        self.assertGreater(seen['seconds'], 182.201, 'the measured review fits inside it')
        self.assertEqual(seen['envelope'], 360, 'the activity envelope is unchanged')
        self.assertEqual(seen['role'], 'review')
        self.assertEqual(outcome['terminal_status'], 'incomplete', 'a cut-off review still produces no verdict')
        self.assertEqual(outcome['provider_result']['exit_code'], 124)

    def test_a_task_without_the_finite_binding_still_reaches_the_call_with_its_former_bound(self):
        legacy = {k: v for k, v in bound_task().items() if k != 'development'}
        seen, _ = self.review(legacy)
        self.assertEqual(seen['seconds'], REVIEW_MODEL_SECONDS)


class GateMessageTests(unittest.TestCase):
    """An unfinished review must be reported as unfinished. It carries no identity fields at all, so the old order
    reported the first missing field and called a host failure a stale or mismatched identity."""
    def setUp(self):
        self.task = bound_task()
        self.subject = {'task_id': self.task['id'], 'task_sha256': digest(self.task), 'base': self.task['base'],
                        'candidate': 'c' * 40, 'acceptance_sha256': self.task['acceptance_sha256'],
                        'completed_steps': [0], 'implementation_runs': ['impl-run']}
        self.tests = {**{k: self.subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')},
                      'scope': 'whole_task', 'terminal_status': 'completed', 'passed': True}
        self.review = {**self.tests, 'verdict': 'approved', 'blocking_findings': [], 'reviewer_run': 'review-run'}

    def test_the_measured_incomplete_review_is_reported_as_incomplete(self):
        incomplete = {'terminal_status': 'incomplete', 'provider_result': {'exit_code': 124, 'interrupted': 'deadline', 'elapsed_seconds': 182.201, 'provider_completed': False}}
        with self.assertRaises(GateClosed) as caught:
            require_gate(self.task, self.subject, self.tests, incomplete)
        message = str(caught.exception)
        self.assertIn('review evidence unfinished', message); self.assertIn('incomplete', message)
        self.assertNotIn('Stale or mismatched', message, 'a host failure is not an identity mismatch')

    def test_a_genuinely_mismatched_identity_is_still_refused_and_named(self):
        with self.assertRaisesRegex(GateClosed, 'Stale or mismatched review evidence: candidate'):
            require_gate(self.task, self.subject, self.tests, {**self.review, 'candidate': 'd' * 40})
        with self.assertRaisesRegex(GateClosed, 'Stale or mismatched tests evidence: task_id'):
            require_gate(self.task, self.subject, {**self.tests, 'task_id': 'other'}, self.review)

    def test_the_gate_still_passes_and_still_refuses_everything_it_refused_before(self):
        self.assertTrue(require_gate(self.task, self.subject, self.tests, self.review))
        for label, tests, review in (('rejected', self.tests, {**self.review, 'verdict': 'rejected'}),
                                     ('findings', self.tests, {**self.review, 'blocking_findings': ['x']}),
                                     ('tests failed', {**self.tests, 'passed': False}, self.review),
                                     ('wrong scope', self.tests, {**self.review, 'scope': 'file'}),
                                     ('absent review', self.tests, None),
                                     ('not independent', self.tests, {**self.review, 'reviewer_run': 'impl-run'})):
            with self.subTest(label=label), self.assertRaises(GateClosed):
                require_gate(self.task, self.subject, tests, review)


class HostAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.scope = SimpleNamespace(directory=self.directory)

    def test_an_answer_is_append_only_and_states_where_it_came_from(self):
        self.assertEqual(host.host_answers(self.scope), [], 'no answers before the host gives one')
        first = host.record_host_answer(self.scope, 'The reviewer bound was raised from 180 to 300 model seconds.', 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 12})
        self.assertEqual((first['task'], first['parent_phase'], first['parent_sequence']), ('ap11-step-5', 'waiting_host_diagnosis', 12))
        self.assertIn('no model ran and no call was counted', first['source'])
        second = host.record_host_answer(self.scope, 'A second, later host fact.', 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 14})
        answers = host.host_answers(self.scope)
        self.assertEqual([a['reason'] for a in answers], [first['reason'], second['reason']], 'oldest first, nothing rewritten')
        self.assertEqual(host.host_answers(self.scope, 'other-task'), [], 'another child sees only its own answers')
        self.assertEqual(len(host.host_answers(self.scope, 'ap11-step-5')), 2)
        for empty in ('', '   ', None):
            with self.subTest(empty=empty), self.assertRaisesRegex(ValueError, 'Explicit host diagnosis answer'):
                host.record_host_answer(self.scope, empty, 'ap11-step-5', {})
        self.assertEqual(len(host.host_answers(self.scope)), 2, 'a refused answer records nothing')


class DiagnosisDeliveryTests(unittest.TestCase):
    """What the diagnosis is shown: the wait, the bounds that apply now, and what the host itself already answered."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.task = bound_task()
        self.scope = SimpleNamespace(directory=self.directory, inspect=lambda: {'tasks': {'ap11-step-5': {'task_sha256': digest(self.task), 'work': 'reconciliation'}}})

    def deliver(self, state, nonce='step-14'):
        config = {'directory': str(self.directory / 'release')}
        (self.directory / 'release/development-context').mkdir(parents=True, exist_ok=True)
        for name, content in (('goal.md', b'G'), ('authority.md', b'A')):
            (self.directory / 'release/development-context' / name).write_bytes(content)
        (self.directory / 'release/office').mkdir(parents=True, exist_ok=True); (self.directory / 'release/office/AGENTS.md').write_bytes(b'rules')
        (self.directory / 'contract.json').write_bytes(b'{}')
        captured = {}
        def prepare_call(expected, key, role, work, context, files, extra=None):
            captured.update(role=role, work=work, context=context, files=files); return {'nonce': key}
        with patch.object(host, 'active_scope', return_value=(self.scope, config)), \
             patch.object(host, 'load', return_value=self.task), patch.object(host, 'goal_amendments', return_value={}), \
             patch.object(host, 'task_directory', return_value=self.directory / 'task'), \
             patch.object(host, 'read_regular', side_effect=readable), \
             patch.object(host, 'prepare_call', side_effect=prepare_call):
            host.diagnosis_call('expected', 'ap11-step-5', state, nonce)
        return captured

    def test_the_bounds_that_apply_now_are_delivered_with_the_wait(self):
        wait = {'phase': 'waiting_review', 'results': [], 'review': {'terminal_status': 'incomplete', 'provider_result': {'exit_code': 124, 'interrupted': 'deadline', 'elapsed_seconds': 182.201}}}
        got = self.deliver(wait)
        bounds = got['context']['host_bounds']
        self.assertEqual(bounds['review_model_seconds'], DEVELOPMENT_REVIEW_MODEL_SECONDS)
        self.assertEqual(bounds['review_activity_seconds'], 360); self.assertEqual(bounds['implementation_model_seconds'], 480)
        self.assertIn('never a candidate defect', bounds['note']); self.assertIn('materially changed prerequisite', bounds['note'])
        self.assertEqual(got['context']['actual_child_wait'], wait, 'the wait itself is unchanged')
        self.assertEqual(got['context']['host_answers'], []); self.assertNotIn('HOST_DIAGNOSIS_ANSWERS.json', got['files'])

    def test_the_hosts_own_answers_reach_the_next_diagnosis_as_a_named_file(self):
        host.record_host_answer(self.scope, 'The reviewer model bound is 300 s in the active release; the cut-off evidence was produced under 180 s.', 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 12})
        host.record_host_answer(self.scope, 'Another child, not this one.', 'other-child', {'phase': 'waiting_host_diagnosis', 'sequence': 13})
        got = self.deliver({'phase': 'waiting_review', 'results': []})
        answers = got['context']['host_answers']
        self.assertEqual(len(answers), 1, 'only this child s answers'); self.assertIn('300 s in the active release', answers[0]['reason'])
        self.assertEqual(json.loads(got['files']['HOST_DIAGNOSIS_ANSWERS.json']), answers, 'delivered as a file the inventory names')
        self.assertIn('HOST_DIAGNOSIS_ANSWERS.json', host.NAMED_ENTRIES)
        self.assertIn('not a decision for you', host.NAMED_ENTRIES['HOST_DIAGNOSIS_ANSWERS.json'])

    def test_everything_the_host_adds_is_registered_and_the_returned_diagnosis_still_binds_to_the_wait(self):
        """Review C found this class once: the host adds a key to the diagnosis workspace and recovery_request, which
        compares the returned context against the wait, then refuses EVERY non-hold diagnosis. The next thing this
        release does is exactly such a diagnosis, so the two sides are checked against each other here."""
        wait = {'phase': 'waiting_review', 'results': [], 'review': {'terminal_status': 'incomplete'}, 'review_recovery': 'retry'}
        host.record_host_answer(self.scope, 'The reviewer model bound is 300 s in the active release.', 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 2})
        got = self.deliver(wait)
        bound_to = {'task': got['context']['task'], 'actual_child_wait': got['context']['actual_child_wait']}
        added = set(got['context']) - set(bound_to)
        self.assertEqual(added, {'host_bounds', 'host_answers'}, 'exactly what this delivery point adds')
        self.assertTrue(added <= set(host.DIAGNOSIS_HOST_KEYS), 'and every one of them is registered')
        workspace = self.directory / 'calls/diag/workspace'; workspace.mkdir(parents=True)
        (workspace / 'CONTEXT.json').write_bytes(json.dumps({**got['context'], 'delivered_files': {'x': 1}}, ensure_ascii=False).encode())
        answer = {'action': 'retry', 'reason': 'The review was cut off at the host bound.', 'changed_prerequisite': 'The bound is now 300 s.'}
        with patch.object(host, 'call_result', return_value={'answer': answer}), \
             patch.object(host, 'load', return_value=self.task):
            outcome = host.recovery_request(self.scope, 'ap11-step-5', wait, 'diag')
        self.assertTrue(outcome['hold'], 'a retry still needs host-verified recovery, as before')
        self.assertNotIn('does not apply', str(outcome), 'but it is NOT refused as inapplicable to the wait')
        self.assertEqual(outcome['diagnosis'], answer)

    def test_the_interrupted_reviews_own_evidence_and_the_named_readers_reach_the_diagnosis(self):
        """The live diagnosis said, in its own words, that it could not justify a re-run because the review evidence
        directory was not delivered and the named readers were absent. Measured: that directory's event stream is 0
        bytes, which is itself the evidence that the host killed the process before it wrote anything."""
        evidence = Path(self.temp.name) / 'evidence'
        (evidence / 'review-1').mkdir(parents=True); (evidence / 'review-2').mkdir()
        (evidence / 'review-1/events.jsonl').write_bytes(b'')
        # Measured shape: provider_result carries the reviewer's OWN denied tool input, with an absolute host path,
        # plus an account-shaped usage object and the scope reservation. None of it may reach a model workspace.
        (evidence / 'review-1/result.json').write_bytes(json.dumps({
            'exit_code': 124, 'interrupted': 'deadline', 'elapsed_seconds': 182.201, 'attempt': 1,
            'provider_completed': False, 'model_started': True, 'thread_id': None, 'provider': 'claude', 'role': 'review',
            'evidence': 'evidence/runs/ap11-step-5/review-1', 'scope_reservation': 'task-' + 'a' * 64,
            'reported_list_cost_usd': 1.25832225,
            'usage': {'input_tokens': 58, 'output_tokens': 820, 'service_tier': 'standard', 'inference_geo': 'not_available'},
            'permission_denials': [{'tool_name': 'Read', 'tool_use_id': 'toolu_01NX',
                                    'tool_input': {'file_path': '/Users/someone/secret/outside.txt'}}]}).encode())
        (evidence / 'review-1/launch.json').write_bytes(
            b'{"seconds_limit": 180, "subscription": {"authMethod": "claude.ai", "subscriptionType": "max"},'
            b' "argv": ["/Users/someone/bin/claude"], "provider_pid": 4242}')
        (evidence / 'review-2/result.json').write_bytes(b'{"exit_code": 0, "provider_completed": true}')
        (evidence / 'not-a-review').mkdir(); (evidence / 'review-x').mkdir()
        # The implementation attempt carries the SAME provider shape, and used to be delivered raw (review L).
        (evidence / 'attempt-1').mkdir()
        (evidence / 'attempt-1/result.json').write_bytes(json.dumps({
            'attempt': 1, 'exit_code': 0, 'elapsed_seconds': 143.695, 'provider_completed': True, 'model_started': True,
            'provider': 'claude', 'role': 'implementation', 'thread_id': 'a-session-id',
            'evidence': 'evidence/runs/ap11-step-5/attempt-1', 'scope_reservation': 'task-' + 'b' * 64,
            'reported_list_cost_usd': 1.25832225, 'interrupted': "[Errno 2] No such file: '/Users/someone/bin/claude'",
            'usage': {'service_tier': 'standard', 'inference_geo': 'not_available'},
            'permission_denials': [{'tool_input': {'file_path': '/Users/someone/secret/outside.txt'}}]}).encode())
        # The HOST-TOOLING failure, in the shape activities.py really writes it: the cause is nested under details,
        # and CalledProcessError stringifies the whole git argv, so the text names absolute host paths.
        (evidence / 'attempt-1/acceptance.json').write_bytes(json.dumps({
            'passed': False, 'host_error': True,
            'candidate_files_sha256': {'tools/development_result.py': 'c' * 64},
            'details': {'passed': False,
                        'reason': "Command '['git', '-C', '/Users/someone/repos/task/commit-1', 'bundle', 'create',"
                                  " '/Users/someone/repos/evidence/attempt-1/candidate.bundle']' returned non-zero"
                                  " exit status 128."}}).encode())
        from runtime import task as task_module
        with patch.object(task_module, 'evidence_directory', return_value=evidence), \
             patch.object(host, 'git', return_value=b'# the existing reader\n'):
            got = self.deliver({'phase': 'waiting_review', 'review': {'terminal_status': 'incomplete'},
                                'results': [{'attempt': 1, 'workspace_name': 'commit-1'}]})
            self.assertEqual(host.review_attempts('ap11-step-5'), [1, 2], 'only real numbered review directories')
        first = json.loads(got['files']['review-1-run.json'])
        self.assertEqual(first['events_bytes'], 0, 'the empty stream is reported as empty; the emptiness is the evidence')
        self.assertEqual(first['events_lines'], 0)
        self.assertEqual((first['exit_code'], first['interrupted'], first['bound_seconds']), (124, 'deadline', 180))
        self.assertEqual(first['permission_denials'], 1, 'that a tool was denied is a number the host measured')
        self.assertTrue(first['usage_reported'], 'whether usage was reported at all, never the usage object')
        self.assertIn('never a finding about the candidate', first['note'])
        self.assertIn('review-2-run.json', got['files'])
        earlier = json.loads(got['files']['previous-1-run.json'])
        self.assertEqual(earlier['interrupted'], 'host error while running it',
                         'a host error string is classified, never passed through: it carries an absolute path')
        self.assertEqual((earlier['exit_code'], earlier['permission_denials'], earlier['usage_reported']), (0, 1, True))
        self.assertEqual(set(earlier), {'attempt_number', 'note', 'interrupted', 'permission_denials', 'usage_reported',
                                        'events_bytes', *(set(host.RUN_FIELDS) & set(earlier))},
                         'the implementation attempt goes through the same host record, not raw')
        verdict = json.loads(got['files']['previous-1-acceptance.json'])
        self.assertIs(verdict['passed'], False, 'the verdict itself still reaches the diagnosis')
        self.assertIn("not the frozen verifier's verdict on the candidate", verdict['withheld'])
        self.assertIn('writing outside the paths the task allows', verdict['withheld'])
        self.assertNotIn('never a finding about the candidate', verdict['withheld'],
                         'review L: the same host try catches a candidate that wrote outside its allowed paths, so '
                         'the sentence must not claim a host failure is never a finding about the candidate')
        self.assertNotIn('verifier_verdict', verdict, 'a host failure carries no verifier finding')
        self.assertEqual(set(verdict) - {'withheld'}, set(host.ACCEPTANCE_FIELDS) & set(verdict))
        self.assertEqual(host.ACCEPTANCE_FIELDS, ('passed', 'scope', 'checks', 'candidate_files_sha256'),
                         'pinned: any field added here has to be argued for in the open')
        for absent in ('reason', 'details', 'host_error'):
            self.assertNotIn(absent, verdict, 'the failure text is never delivered')
        blob = json.dumps(verdict)
        for secret in ('/Users/', 'candidate.bundle', 'returned non-zero'):
            self.assertNotIn(secret, blob, 'no host path or command line reaches a model workspace')
        delivered = b''.join(v for k, v in got['files'].items() if isinstance(v, bytes))
        for secret in (b'subscription', b'authMethod', b'/Users/', b'provider_pid', b'scope_reservation', b'"evidence"'):
            self.assertNotIn(secret, delivered, 'no host account, path or reservation material reaches a model workspace')
        # Review L: an assertion derived from the whitelist cannot detect a change to the whitelist. This pins the
        # tuple itself, so ANY field added to it fails here and has to be argued for in the open.
        # Argued in the open, 2026-09-22: 'model' and 'reported_model' were added when the model became a
        # release-bound selection. They are named model ids - which model the host started, and which one the
        # provider said it was - not host text, paths or account material. Without them a diagnosis cannot
        # tell two runs apart at all, because a release that changes only the selection keeps the same
        # runtime_revision, which previously implied the model.
        self.assertEqual(host.RUN_FIELDS, ('attempt', 'elapsed_seconds', 'exit_code', 'provider_completed',
                                           'model_started', 'process_group_removed', 'model', 'reported_model'),
                         'the delivered whitelist is exactly these host-measured scalars')
        self.assertEqual(set(first), {'review_number', 'note', 'bound_seconds', 'events_bytes', 'events_lines',
                                      'permission_denials', 'usage_reported', 'interrupted', *host.RUN_FIELDS} & set(first),
                         'and the record carries nothing beyond them and the host-derived fields')
        for reader in ('tools/kontor_result.py', 'tools/agarbild.py'):
            self.assertEqual(got['files'][reader], b'# the existing reader\n', 'the readers the frozen goal names')

    def test_a_review_run_the_host_cannot_read_is_reported_as_such_and_never_vanishes(self):
        """A diagnosis must be able to tell 'no attempt' from 'the host cannot read its own record of one'."""
        evidence = Path(self.temp.name) / 'ev2'
        (evidence / 'review-1').mkdir(parents=True); (evidence / 'review-1/result.json').write_bytes(b'{ broken')
        (evidence / 'review-2').mkdir()
        (evidence / 'review-2/result.json').write_bytes(b'{"exit_code": 0, "provider_completed": true}')
        (evidence / 'review-2/events.jsonl').write_bytes(b'x' * (host.EVENT_STREAM_LIMIT + 1))
        from runtime import task as task_module
        with patch.object(task_module, 'evidence_directory', return_value=evidence):
            broken = host.review_run_record('ap11-step-5', 1)
            missing = host.review_run_record('ap11-step-5', 9)
            oversized = host.review_run_record('ap11-step-5', 2)
        self.assertIn('could not read its own record', broken['unavailable'])
        self.assertEqual(broken['review_number'], 1, 'the run is still named')
        # Review L: saying 'the host could not read its own record' about a run that never happened is an invention.
        self.assertIsNone(missing, 'a run that never happened yields no record at all')
        self.assertEqual(oversized['events_bytes'], host.EVENT_STREAM_LIMIT + 1, 'the real size, not a sentence')
        self.assertNotIn('events_lines', oversized, 'lines are counted only when the host can read the stream')

    def test_the_host_marks_its_own_cause_where_the_failure_actually_happens(self):
        """The record the diagnosis reads is only as honest as the record the activity writes. Measured: the mutant
        that removed the marker was 'killed' by an unrelated timing test, so nothing here actually held it. The
        candidate-hang case is review L's third door into the same inversion: the frozen recipe runs the CANDIDATE's
        own code under its own timeout, so a hang there is the candidate's outcome, not the host's tooling."""
        from runtime import activities
        import subprocess as sp
        task = bound_task()
        cases = (('host tooling raised', OSError('git bundle: no such path /Users/x'), None, True),
                 ('the verifier rejected the candidate', None, None, False),
                 ('the candidate hung under the verifier own timeout', None,
                  sp.TimeoutExpired(cmd=['/Users/someone/bin/python3.12'], timeout=120), False),
                 ('the verifier itself crashed', None, ValueError('recipe blew up'), False))
        for number, (label, freeze_failure, verify_failure, host_cause) in enumerate(cases, 1):
            with self.subTest(label=label):
                evidence = Path(self.temp.name) / ('written-' + str(number))
                evidence.mkdir()

                def verifier(_frozen):
                    if verify_failure is not None:
                        raise verify_failure
                    return {'passed': False, 'checks': ['a frozen check'], 'failed': ['duplicate row not refused']}

                def prepare(*_a, **_k):
                    if freeze_failure is not None:
                        raise freeze_failure
                    return {'workspace_name': 'commit-1', 'candidate': 'c' * 40, 'candidate_files_sha256': {}}

                with patch.object(activities, 'load', return_value=task), \
                     patch.object(activities, 'before_activity', return_value=None), \
                     patch.object(activities, 'invoke', return_value={'provider_completed': True, 'evidence': evidence.name}), \
                     patch.object(activities, 'ROOT', Path(self.temp.name)), \
                     patch.object(activities, 'task_directory', return_value=Path(self.temp.name)), \
                     patch.object(activities, 'prepare', side_effect=prepare), \
                     patch.object(activities, 'git', return_value=b''), \
                     patch.object(activities, 'frozen_verifier', return_value=verifier):
                    activities.execute_implementation({'task_id': task['id'], 'task_digest': digest(task), 'number': 1})
                written = json.loads((evidence / 'acceptance.json').read_text())
                self.assertIs(written['passed'], False)
                self.assertEqual(written.get('host_error') is True, host_cause,
                                 'the host marks its own cause, and only its own')
                self.assertEqual(written.get('verifier_rejected') is True, not host_cause,
                                 'and marks the other cause too, or the finding is lost as an unrecorded cause')
                self.assertNotEqual(written.get('host_error'), written.get('verifier_rejected'),
                                    'exactly one cause is recorded, never both and never neither')
                if not host_cause:
                    self.assertNotIn('/Users/', json.dumps(written.get('details') or {}),
                                     'a candidate outcome never carries the host error text')

    def test_the_legacy_verifier_branch_marks_the_same_two_causes(self):
        """Both branches of execute_implementation were changed, so both are measured. A task without a frozen
        acceptance takes the legacy path; the live AP11 child does not, so this is the other branch of the same
        guard rather than a separate behaviour."""
        from runtime import activities
        import subprocess as sp
        legacy = {k: v for k, v in bound_task().items() if k != 'acceptance_sha256'}
        for number, (failure, host_cause) in enumerate(((None, False), (sp.TimeoutExpired(cmd=['x'], timeout=9), False),
                                                        (OSError('snapshot failed /Users/x'), True)), 1):
            with self.subTest(number=number):
                evidence = Path(self.temp.name) / ('legacy-' + str(number)); evidence.mkdir()
                def snapshot(*_a, **_k):
                    if isinstance(failure, OSError):
                        raise failure
                    return {}
                def verify(_candidate):
                    if failure is not None and not isinstance(failure, OSError):
                        raise failure
                    return {'passed': False, 'failed': ['legacy check']}
                with patch.object(activities, 'load', return_value=legacy), \
                     patch.object(activities, 'before_activity', return_value=None), \
                     patch.object(activities, 'invoke', return_value={'provider_completed': True, 'evidence': evidence.name}), \
                     patch.object(activities, 'ROOT', Path(self.temp.name)), \
                     patch.object(activities, 'task_directory', return_value=Path(self.temp.name)), \
                     patch.object(activities, 'snapshot', side_effect=snapshot), \
                     patch.object(activities, 'legacy_verify', side_effect=verify):
                    activities.execute_implementation({'task_id': legacy['id'], 'task_digest': digest(legacy), 'number': 1})
                written = json.loads((evidence / 'acceptance.json').read_text())
                self.assertEqual(written.get('host_error') is True, host_cause)
                self.assertEqual(written.get('verifier_rejected') is True, not host_cause,
                                 'a legacy verifier that raises is still the candidate outcome, not the host failing')

    def test_a_verifier_that_a_candidate_never_lets_finish_is_not_the_host_failing(self):
        """The delivered record for that case, end to end."""
        from runtime import activities
        import subprocess as sp
        evidence = Path(self.temp.name) / 'hang'; (evidence / 'attempt-1').mkdir(parents=True)
        def hanging(_frozen):
            raise sp.TimeoutExpired(cmd=['/opt/homebrew/bin/python3.12', '-I', '/Users/someone/tools/x.py'], timeout=120)
        validation = activities.run_verifier(hanging, Path('candidate'))
        self.assertIs(validation['passed'], False)
        self.assertEqual(validation['reason'], 'the frozen verifier did not complete on this candidate')
        self.assertNotIn('/Users/', json.dumps(validation), 'the timeout text names host paths and is not kept')
        (evidence / 'attempt-1/acceptance.json').write_bytes(json.dumps({
            'passed': False, 'verifier_rejected': True, 'details': validation, 'candidate_files_sha256': {}}).encode())
        from runtime import task as task_module
        with patch.object(task_module, 'evidence_directory', return_value=evidence):
            record = host.acceptance_record('ap11-step-5', 1)
        self.assertNotIn('withheld', record, 'a candidate the verifier could not finish on is not a host failure')
        self.assertEqual(record['verifier_verdict']['reason'], 'the frozen verifier did not complete on this candidate')
        # Review L: "did not complete" is not the statement "ran and did not pass" - the recipe may never have
        # started, and the note must not claim a verdict that was never reached.
        self.assertIs(record['verifier_verdict']['verifier_incomplete'], True)
        self.assertIn('did not complete', record['note'])
        self.assertNotIn('ran and did not pass', record['note'])

    def test_a_rejected_candidate_is_never_reported_as_a_host_failure(self):
        """Review L, blocking twice. First both non-pass causes were collapsed into the host-tooling sentence, so a
        candidate the frozen verifier really rejected was described to the diagnosis as the host's own fault. Then the
        shape test that replaced it read the LIVE recipe's own rejection branch, which returns exactly
        {'passed', 'reason'}, as a host failure - and the rejection branch that carries 6000 bytes of subprocess
        stderr was delivered whole, absolute host paths and all. These are the shapes that recipe really returns."""
        from runtime import activities

        def wrapped(validation):
            """The tail of execute_implementation, verbatim: how the record actually reaches disk."""
            host_error = isinstance(validation, dict) and validation.get('host_error') is True
            return {'passed': False, 'details': validation,
                    **({'host_error': True} if host_error else {'verifier_rejected': True}),
                    'candidate_files_sha256': {}}

        evidence = Path(self.temp.name) / 'causes'
        # 1: the live recipe, returncode branch - its own words plus raw subprocess stderr naming host paths.
        recipe_stderr = {'passed': False, 'reason': 'AP11 reconciliation recipe failed',
                         'stderr': 'Traceback (most recent call last):\n  File "/Users/someone/repos/tasks/'
                                   'ap11-step-5/commit-1/tools/development_result.py", line 41, in reconcile\n'}
        # 2: the live recipe, unparsable-result branch - exactly {'passed', 'reason'}, and a real rejection.
        recipe_missing = {'passed': False, 'reason': 'Missing recipe result'}
        # 3: the host's own tooling raising, as activities.py records it.
        host_raised = {'passed': False, 'host_error': True,
                       'reason': "Command '['git', '-C', '/Users/someone/x', 'bundle']' returned non-zero exit status 128."}
        # 4: a record written before the host marked its own cause at all.
        legacy = {'passed': False, 'details': {'passed': False, 'reason': 'anything at all'}, 'candidate_files_sha256': {}}
        shapes = {1: wrapped(recipe_stderr), 2: wrapped(recipe_missing), 3: wrapped(host_raised), 4: legacy}
        for number, content in shapes.items():
            (evidence / ('attempt-' + str(number))).mkdir(parents=True)
            (evidence / ('attempt-' + str(number)) / 'acceptance.json').write_bytes(json.dumps(content).encode())
        from runtime import task as task_module
        with patch.object(task_module, 'evidence_directory', return_value=evidence):
            got = {n: host.acceptance_record('ap11-step-5', n) for n in shapes}

        stderr_case = got[1]
        self.assertIn('verifier_verdict', stderr_case, 'the live recipe returncode branch IS a candidate finding')
        self.assertEqual(stderr_case['verifier_verdict'], {'passed': False, 'reason': 'AP11 reconciliation recipe failed'},
                         'its own verdict fields, never the subprocess output it collected')
        self.assertNotIn('/Users/', json.dumps(stderr_case), 'the stderr with host paths never reaches the workspace')
        self.assertIn('subprocess output, is not delivered', stderr_case['note'])

        missing_case = got[2]
        self.assertIn('verifier_verdict', missing_case, 'and so is the unparsable-result branch')
        self.assertNotIn('withheld', missing_case, 'a real rejection is never described as the host failing')
        self.assertEqual(missing_case['verifier_verdict']['reason'], 'Missing recipe result')
        self.assertIn('ran and did not pass the candidate', missing_case['note'],
                      'a verifier that really ran is stated as having run')
        self.assertNotIn('verifier_incomplete', missing_case['verifier_verdict'])

        host_case = got[3]
        self.assertIn("not the frozen verifier's verdict on the candidate", host_case['withheld'])
        self.assertNotIn('verifier_verdict', host_case)
        self.assertNotIn('/Users/', json.dumps(host_case))

        unmarked = got[4]
        self.assertIn('cannot say whether its own tooling failed', unmarked['cause_unrecorded'])
        self.assertNotIn('withheld', unmarked, 'an unrecorded cause is not asserted to be either one')
        self.assertNotIn('verifier_verdict', unmarked)
        self.assertNotIn('anything at all', json.dumps(unmarked), 'and neither text is delivered')

        self.assertEqual(host.VERIFIER_FIELDS, ('passed', 'scope', 'checks', 'failed', 'reason', 'verifier_incomplete'),
                         'pinned: any field added here has to be argued for in the open. verifier_incomplete is on '
                         'the list because the HOST sets it in run_verifier, not the recipe, and the receiver needs '
                         'it to tell "did not complete" from "ran and did not pass"')

    def test_an_oversized_verifier_verdict_is_reported_rather_than_delivered(self):
        evidence = Path(self.temp.name) / 'big'; (evidence / 'attempt-1').mkdir(parents=True)
        (evidence / 'attempt-1/acceptance.json').write_bytes(json.dumps({
            'passed': False, 'verifier_rejected': True, 'candidate_files_sha256': {},
            'details': {'passed': False, 'failed': ['x' * (host.VERIFIER_LIMIT + 100)]}}).encode())
        from runtime import task as task_module
        with patch.object(task_module, 'evidence_directory', return_value=evidence):
            record = host.acceptance_record('ap11-step-5', 1)
        self.assertIn('oversized', record['verifier_verdict'])
        self.assertNotIn('x' * 100, json.dumps(record), 'the bulk is reported, not delivered')

    def test_the_host_vocabulary_and_the_stream_bound_are_the_ones_the_host_actually_uses(self):
        """Review L: dropping a word from HOST_INTERRUPTIONS would silently degrade a real kill to a host error, and
        EVENT_STREAM_LIMIT duplicated the reader's own bound by hand with nothing binding the two."""
        import inspect as inspection
        from runtime import attempt as attempt_module
        source = inspection.getsource(attempt_module)
        for word in host.HOST_INTERRUPTIONS:
            self.assertIn(repr(word), source, 'a word this host never assigns is not part of its vocabulary')
        self.assertEqual(host.HOST_INTERRUPTIONS, ('deadline', 'signal', 'active instruction/configuration binding changed'))
        self.assertEqual(host.EVENT_STREAM_LIMIT,
                         inspection.signature(read_regular).parameters['limit'].default,
                         'the stream bound is the one the reader actually applies')

    def test_a_reader_the_host_cannot_fetch_never_fails_the_diagnosis(self):
        import subprocess as sp
        with patch.object(host, 'git', side_effect=sp.CalledProcessError(128, 'git')):
            got = self.deliver({'phase': 'waiting_review', 'results': []})
        self.assertNotIn('tools/kontor_result.py', got['files'])
        self.assertEqual(got['role'], 'diagnosis', 'the diagnosis is still prepared')

    def test_bounds_that_cannot_be_derived_do_not_fail_the_diagnosis(self):
        self.task = {'id': 'ap11-step-5', 'allowed_paths': ['tools/a.py'], 'steps': [{'provider': 'claude'}]}
        got = self.deliver({'phase': 'waiting_diagnosis', 'results': []})
        self.assertIn('undetermined', got['context']['host_bounds'], 'stated as underivable, never an exception')
        self.assertEqual(got['role'], 'diagnosis')


class HostContinuationTests(unittest.IsolatedAsyncioTestCase):
    """The host's own way out of a diagnosis wait. It must be usable exactly where the chain actually stands and
    nowhere else, and it must never be a second door into starting work: no interactive start is consumed and the
    control state is not rewritten to make the answer fit."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; self.directory.mkdir(parents=True)
        self.state = {'phase': 'waiting_host_diagnosis', 'sequence': 2, 'children': ['ap11-step-4', 'ap11-step-5'], 'results': []}
        self.control = 'active'

    def rig(self):
        from unittest.mock import AsyncMock, Mock
        handle = SimpleNamespace(signal=AsyncMock(), query=AsyncMock(side_effect=lambda _: dict(self.state)), cancel=AsyncMock())
        scope = SimpleNamespace(control=Mock(), directory=self.directory, expected='fixture',
                                inspect=lambda: {'control': self.control, 'tasks': {}})
        service = AsyncMock(); service.__aenter__.return_value = SimpleNamespace(get_workflow_handle=lambda _: handle, start_workflow=AsyncMock())
        return handle, scope, service

    async def operate(self, action, reason):
        from unittest.mock import patch as patched
        handle, scope, service = self.rig()
        with patched('runtime.development_control.require_active_code', return_value={'development': {'contract_sha256': 'fixture'}, 'config_sha256': 'fixture'}), \
             patched('runtime.development_control.active_scope', return_value=(scope, {})), \
             patched('runtime.development_control.SharedService', return_value=service):
            from runtime.development_control import operate
            try:
                return await operate(action, reason), handle, scope, None
            except ValueError as error:
                return None, handle, scope, error

    async def test_the_host_answers_the_waiting_parent_without_spending_an_interactive_start(self):
        result, handle, scope, error = await self.operate('continue', 'The reviewer model bound is 300 s in the active release.')
        self.assertIsNone(error)
        self.assertEqual(handle.signal.await_args.args[0].__name__, 'continue_after_diagnosis')
        self.assertEqual(handle.signal.await_args.args[1], 'The reviewer model bound is 300 s in the active release.')
        answers = host.host_answers(SimpleNamespace(directory=self.directory))
        self.assertEqual(len(answers), 1)
        self.assertEqual((answers[0]['task'], answers[0]['parent_sequence']), ('ap11-step-5', 2), 'bound to the child actually waited on')
        self.assertEqual(result['host_answer']['reason'], answers[0]['reason'], 'the recorded answer is reported back')
        scope.control.assert_not_called(); handle.cancel.assert_not_awaited()

    async def test_it_is_refused_anywhere_the_parent_is_not_actually_waiting_for_a_diagnosis(self):
        for phase in ('waiting_review', 'waiting_control', 'running', 'stopped', None):
            self.state = {**self.state, 'phase': phase}
            with self.subTest(phase=phase):
                result, handle, scope, error = await self.operate('continue', 'a host fact')
                self.assertIn('waiting for host diagnosis', str(error)); self.assertIn(str(phase), str(error))
                handle.signal.assert_not_awaited(); self.assertEqual(host.host_answers(SimpleNamespace(directory=self.directory)), [])

    async def test_a_closed_or_paused_goal_is_resumed_explicitly_first_and_never_by_this_answer(self):
        for control in ('paused', 'stopped', 'revoked', 'exhausted'):
            self.control = control
            with self.subTest(control=control):
                result, handle, scope, error = await self.operate('continue', 'a host fact')
                self.assertIn('Resume the finite goal explicitly', str(error))
                scope.control.assert_not_called(); handle.signal.assert_not_awaited()
                self.assertEqual(host.host_answers(SimpleNamespace(directory=self.directory)), [], 'nothing is recorded for a refused answer')

    async def test_the_answer_must_say_something(self):
        for reason in (None, '', '   '):
            with self.subTest(reason=reason):
                result, handle, scope, error = await self.operate('continue', reason)
                self.assertIn('Explicit scoped reason required', str(error)); handle.signal.assert_not_awaited()

    async def test_an_answer_that_cannot_be_recorded_never_spends_the_continuation(self):
        """Review G, blocking: the signal is sent before the answer is written, so a refusal at the write would
        consume the operator's one continuation, record nothing, and leave the parent out of the phase the command
        requires - with the operator told it failed. Every refusal therefore runs before the signal."""
        result, handle, scope, error = await self.operate('continue', 'x' * (host.ANSWER_LIMIT + 1))
        self.assertIn('Unbounded host diagnosis answer', str(error))
        handle.signal.assert_not_awaited()
        self.assertEqual(host.host_answers(SimpleNamespace(directory=self.directory)), [], 'and nothing was recorded')


class HostVerifiedContinuationTests(unittest.TestCase):
    """The half that makes the host answer mean something. Measured by reading the path the chain would actually
    take: recovery_request returned hold for everything but `repair`, so a review the HOST interrupted could never be
    re-run and the continuation command would lead straight back into the same wait. The parent already knows how to
    signal review_only to its child; only this gate was shut."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls/diag/workspace').mkdir(parents=True)
        self.task = bound_task()
        self.scope = SimpleNamespace(directory=self.directory,
                                     inspect=lambda: {'tasks': {'ap11-step-5': {'task_sha256': digest(self.task), 'work': 'reconciliation'}}})
        self.state = {'phase': 'waiting_review', 'attempts': 1, 'review_number': 1, 'review_recovery': 'review_only',
                      'waiting_reason': 'Mandatory review evidence unfinished or wrong scope: incomplete',
                      'results': [{'attempt': 1, 'candidate': 'c' * 40, 'provider_completed': True, 'phase_acceptance_passed': True,
                                   'thread_id': 'impl-run'}],
                      'review': {'terminal_status': 'incomplete',
                                 'provider_result': {'exit_code': 124, 'interrupted': 'deadline', 'elapsed_seconds': 182.201,
                                                     'provider_completed': False, 'thread_id': None}}}
        self.answer = {'action': 'review_only', 'reason': 'The review was interrupted by the host, not by the candidate.',
                       'changed_prerequisite': 'The review model bound is 300 s in the active release; the cut-off ran under 180 s.'}

    def request(self, answer=None, nonce='diag'):
        stage = self.directory / 'calls' / nonce / 'workspace'; stage.mkdir(parents=True, exist_ok=True)
        (stage / 'CONTEXT.json').write_bytes(json.dumps({'task': self.task, 'actual_child_wait': self.state,
                                                         'host_bounds': {'note': 'n'}, 'host_answers': [],
                                                         'delivered_files': {'files': []}}, ensure_ascii=False).encode())
        with patch.object(host, 'call_result', return_value={'answer': answer or self.answer}), \
             patch.object(host, 'load', return_value=self.task):
            return host.recovery_request(self.scope, 'ap11-step-5', self.state, nonce)

    def record(self, reason='The reviewer model bound was raised from 180 to 300 s in the active release.'):
        return host.record_host_answer(self.scope, reason, 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 12})

    def test_without_a_recorded_host_answer_an_interrupted_review_still_cannot_continue(self):
        outcome = self.request()
        self.assertTrue(outcome['hold']); self.assertIn('model text is not recovery authority', outcome['reason'])

    def test_a_recorded_host_answer_lets_the_model_re_run_the_review_it_did_not_fail(self):
        self.record()
        outcome = self.request()
        self.assertNotIn('hold', outcome)
        self.assertEqual(outcome['action'], 'review_only')
        self.assertEqual(outcome['request']['action'], 'review_only')
        self.assertEqual(outcome['request']['candidate'], 'c' * 40)
        self.assertEqual(outcome['request']['review_number'], 1)
        self.assertEqual(outcome['request']['expected_attempt'], 1)
        self.assertIn('interrupted by the host', outcome['request']['reason'])
        self.assertIn('300 s', outcome['request']['reason'], 'the changed prerequisite travels with it')
        self.assertTrue((self.directory / 'calls/diag/recovery.json').is_file(), 'the continuation is recorded')

    def test_one_host_answer_authorizes_exactly_one_continuation(self):
        """Review G, blocking: the binding included state['review'], which a re-run rewrites (new attempt number, new
        evidence path, new reservation nonce), so one answer authorized an unbounded chain of automatic re-runs. The
        second request below carries exactly the review record a cut-off re-run produces."""
        self.record(); self.request()
        rerun = {**self.state, 'review_number': 2,
                 'review': {'terminal_status': 'incomplete',
                            'provider_result': {'attempt': 2, 'exit_code': 124, 'interrupted': 'deadline',
                                                'elapsed_seconds': 301.4, 'evidence': 'evidence/runs/ap11-step-5/review-2',
                                                'scope_reservation': 'task-' + 'e' * 64, 'provider_completed': False}}}
        self.state = rerun
        with self.assertRaisesRegex(ValueError, 'Repeated unchanged diagnosis'):
            self.request(nonce='diag2')

    def test_a_later_host_answer_is_a_new_fact_and_may_justify_a_new_continuation(self):
        self.record(); self.request()
        self.record('A second, later host fact about this wait.')
        self.assertEqual(self.request(nonce='diag3')['action'], 'review_only')

    def test_the_action_must_be_the_one_the_host_itself_measures(self):
        self.record()
        for action in ('retry', 'repair'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'must not become a candidate repair'):
                self.request({**self.answer, 'action': action}, nonce='diag-' + action)

    def test_a_host_answer_does_not_open_the_other_waits(self):
        """Only the interrupted review is opened here. A waiting_diagnosis retry still needs host recovery."""
        self.record()
        self.state = {**self.state, 'phase': 'waiting_diagnosis'}
        outcome = self.request({**self.answer, 'action': 'retry'}, nonce='diag-retry')
        self.assertTrue(outcome['hold']); self.assertIn('model text is not recovery authority', outcome['reason'])

    def test_a_review_that_really_rejected_the_candidate_is_not_re_run_as_a_host_failure(self):
        self.record()
        self.state = {**self.state, 'review_recovery': 'review_only',
                      'review': {'verdict': 'rejected', 'blocking_findings': ['a concrete finding'], 'summary': 's',
                                 'scope': 'whole_task', 'terminal_status': 'completed', 'reviewer_run': 'review-run',
                                 'task_id': 'ap11-step-5', 'task_sha256': digest(self.task), 'candidate': 'c' * 40,
                                 'acceptance_sha256': self.task['acceptance_sha256']}}
        outcome = self.request(nonce='diag-rejected')
        self.assertTrue(outcome['hold']); self.assertIn('no longer measures this wait', outcome['reason'])

    def test_the_repair_path_still_requires_an_independently_bound_rejection(self):
        self.record()
        self.state = {**self.state, 'review_recovery': 'repair'}
        outcome = self.request({**self.answer, 'action': 'repair'}, nonce='diag-repair2')
        self.assertTrue(outcome['hold']); self.assertIn('No independently bound candidate rejection', outcome['reason'])




class Policy:
    def schema(self, role, work=None):
        return {'type': 'object', 'role': role, 'work': work}

    def instructions(self, role, work=None):
        return 'fixture instructions for ' + role + ' ' + str(work)


class HostAnswerRobustnessTests(unittest.TestCase):
    """Review E, blocking: the answer had no length bound while read_regular refuses anything over 262144 bytes, so a
    single `continue --reason "<a pasted log>"` wrote a file that could never be read back. host_answers then raised
    for the whole scope, which took every future diagnosis with it -- and the only command out of that wait reads the
    same directory, so the live goal could not be recovered from inside itself."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.scope = SimpleNamespace(directory=self.directory)

    def test_an_answer_too_long_to_read_back_is_refused_at_the_write(self):
        with self.assertRaisesRegex(ValueError, 'Unbounded host diagnosis answer'):
            host.record_host_answer(self.scope, 'x' * (host.ANSWER_LIMIT + 1), 'ap11-step-5', {})
        self.assertEqual(host.host_answers(self.scope), [], 'and nothing is written')
        host.record_host_answer(self.scope, 'x' * host.ANSWER_LIMIT, 'ap11-step-5', {})
        self.assertEqual(len(host.host_answers(self.scope, 'ap11-step-5')), 1, 'the bound itself is still accepted')

    def test_an_unreadable_answer_is_reported_and_never_stops_the_next_diagnosis(self):
        host.record_host_answer(self.scope, 'A real host fact.', 'ap11-step-5', {'phase': 'waiting_host_diagnosis', 'sequence': 12})
        oversized = self.directory / host.HOST_ANSWERS / 'answer-002.json'
        oversized.write_bytes(b'{"reason": "' + b'y' * 300000 + b'"}')
        (self.directory / host.HOST_ANSWERS / 'answer-003.json').write_bytes(b'not json at all')
        answers = host.host_answers(self.scope)
        self.assertEqual(len(answers), 3)
        self.assertEqual([a.get('unreadable') for a in answers], [None, 'answer-002.json', 'answer-003.json'])
        self.assertIn('absent evidence', answers[1]['note'])
        facts = host.host_answer_facts(self.scope, 'ap11-step-5')
        self.assertEqual([f['reason'] for f in facts], ['A real host fact.'], 'only readable answers are host facts')

    def test_a_scope_whose_only_answer_is_unreadable_authorizes_nothing_and_still_records(self):
        directory = self.directory / host.HOST_ANSWERS; directory.mkdir(mode=0o700)
        (directory / 'answer-001.json').write_bytes(b'{ broken')
        self.assertEqual(host.host_answer_facts(self.scope, 'ap11-step-5'), [], 'an unreadable answer is not a fact')
        entry = host.record_host_answer(self.scope, 'A readable fact after a broken one.', 'ap11-step-5', {})
        self.assertEqual(entry['reason'], 'A readable fact after a broken one.')
        self.assertTrue((directory / 'answer-002.json').is_file(), 'numbered past the broken file, never colliding')

    def test_a_removed_answer_does_not_make_the_next_one_collide(self):
        for reason in ('first', 'second', 'third'):
            host.record_host_answer(self.scope, reason, 'ap11-step-5', {})
        directory = self.directory / host.HOST_ANSWERS
        (directory / 'answer-002.json').unlink()
        entry = host.record_host_answer(self.scope, 'after a removal', 'ap11-step-5', {})
        self.assertTrue((directory / 'answer-004.json').is_file(), 'numbered from the highest name, not from the count')
        self.assertEqual([a['reason'] for a in host.host_answers(self.scope, 'ap11-step-5')],
                         ['first', 'third', 'after a removal'], 'and nothing earlier was overwritten')
        self.assertEqual(entry['reason'], 'after a removal')

    def test_an_answer_bound_to_no_child_is_never_delivered_as_a_fact_about_one(self):
        host.record_host_answer(self.scope, 'A parent-level host fact, before any child existed.', None, {})
        self.assertEqual(len(host.host_answers(self.scope)), 1, 'it is kept and visible in the whole listing')
        self.assertEqual(host.host_answers(self.scope, 'ap11-step-5'), [])
        self.assertEqual(host.host_answer_facts(self.scope, 'ap11-step-5'), [], 'and it authorizes nothing for a child')


class GateEquivalenceTests(unittest.TestCase):
    """Review E proved the reorder changes only which message is raised. Kept here as a standing check: the old order
    is reimplemented verbatim and compared against the real gate over the whole space the reorder touches."""
    def setUp(self):
        self.task = bound_task()
        self.subject = {'task_id': self.task['id'], 'task_sha256': digest(self.task), 'base': self.task['base'],
                        'candidate': 'c' * 40, 'acceptance_sha256': self.task['acceptance_sha256'],
                        'completed_steps': [0], 'implementation_runs': ['impl-run']}

    @staticmethod
    def former_order(task, subject, tests, review):
        for evidence in (tests, review):
            for field in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256'):
                if evidence.get(field) != subject.get(field):
                    raise GateClosed('Stale or mismatched evidence: ' + field)
            if evidence.get('scope') != 'whole_task' or evidence.get('terminal_status') != 'completed':
                raise GateClosed('Mandatory evidence unfinished or wrong scope')
        return True

    def variants(self, extra):
        identity = {k: self.subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
        shapes = [identity, {k: v for k, v in identity.items() if k != 'task_id'}]
        for field in identity:
            shapes.append({**identity, field: 'wrong'})
        for shape in shapes:
            for scope in ('whole_task', 'file', None):
                for terminal in ('completed', 'incomplete', None):
                    evidence = {**shape, **extra}
                    if scope is not None:
                        evidence['scope'] = scope
                    if terminal is not None:
                        evidence['terminal_status'] = terminal
                    yield evidence

    def test_the_reorder_refuses_exactly_what_the_former_order_refused(self):
        compared = divergences = 0
        for tests in self.variants({'passed': True}):
            for review in self.variants({'verdict': 'approved', 'blocking_findings': [], 'reviewer_run': 'review-run'}):
                def outcome(gate):
                    try:
                        return bool(gate(self.task, self.subject, tests, review))
                    except GateClosed:
                        return False
                compared += 1
                if outcome(require_gate) != outcome(self.former_order):
                    divergences += 1
        self.assertGreater(compared, 2000, 'the whole space the reorder touches')
        self.assertEqual(divergences, 0, 'only the message changed, never whether the gate refuses')


class BoundsResilienceTests(unittest.TestCase):
    def test_a_task_whose_profile_the_host_cannot_read_is_stated_as_undetermined(self):
        for task in ({'id': 'x'}, {'attempt_seconds': True}, {'attempt_seconds': 'many'},
                     # a finite child whose bounded profile the host refuses: activity_seconds raises ScopeClosed
                     {'attempt_seconds': 480, 'allowed_paths': ['only/one.py'], 'development': {'work': 'reconciliation'}},
                     {'attempt_seconds': 900, 'allowed_paths': ['a.py', 'b.py'], 'development': {'work': 'reconciliation'}}):
            with self.subTest(task=task):
                bounds = host.host_bounds(task)
                self.assertIn('undetermined', bounds); self.assertIn('note', bounds)
        self.assertEqual(host.host_bounds(bound_task())['review_model_seconds'], DEVELOPMENT_REVIEW_MODEL_SECONDS)


class RealDeliveryTests(unittest.TestCase):
    """Through the REAL prepare_call: review E observed that nothing proved the new files survive its name check,
    its total bound and the inventory."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.scope = SimpleNamespace(directory=self.directory)

    def test_every_name_this_delivery_point_actually_builds_survives_the_real_prepare_call(self):
        """Review G, blocking: the earlier version of this test staged 'review-1-events.jsonl.json', a name the code
        cannot produce, while the real key 'review-1-events.jsonl' fails prepare_call's suffix check - so every
        diagnosis of a child with a review attempt would have raised before any model ran. The names below are the
        ones diagnosis_call really constructs."""
        files = {'TASK.md': b'brief', 'VERIFICATION_RECIPE.py': b'recipe', 'tools/kontor_result.py': b'# reader\n',
                 'tools/agarbild.py': b'# ap08\n', 'previous-1-result.json': b'{}',
                 'review-1-run.json': json.dumps({'review_number': 1, 'exit_code': 124, 'events_bytes': 0}).encode(),
                 'HOST_DIAGNOSIS_ANSWERS.json': json.dumps([{'task': 'ap11-step-5', 'reason': 'bound raised'}]).encode()}
        with patch.object(host, 'active_scope', return_value=(self.scope, {})), patch.object(host, 'policy', return_value=Policy()):
            host.prepare_call('expected', 'diag', 'diagnosis', 'reconciliation', {'task': {}, 'actual_child_wait': {}}, files)
        workspace = self.directory / 'calls/diag/workspace'
        context = json.loads((workspace / 'CONTEXT.json').read_text())
        listed = {e['path']: e for e in context['delivered_files']['files']}
        for name in files:
            self.assertIn(name, listed, 'named in the inventory a reader without directory listing depends on')
            self.assertTrue((workspace / name).is_file())
        self.assertEqual(json.loads((workspace / 'review-1-run.json').read_text())['events_bytes'], 0)
        self.assertIn('never a finding about the candidate', listed['review-1-run.json']['meaning'])
        self.assertIn('not a decision for you', listed['HOST_DIAGNOSIS_ANSWERS.json']['meaning'])
        self.assertIn('reuse, not to re-create', listed['tools/kontor_result.py']['meaning'])

    def test_the_delivery_point_builds_no_name_the_real_prepare_call_would_refuse(self):
        """The general form of the same defect: whatever diagnosis_call puts in files must pass the name check."""
        evidence = Path(self.temp.name) / 'ev'; (evidence / 'review-1').mkdir(parents=True)
        (evidence / 'review-1/events.jsonl').write_bytes(b'')
        (evidence / 'review-1/result.json').write_bytes(b'{"exit_code": 124, "elapsed_seconds": 182.201}')
        (evidence / 'review-1/launch.json').write_bytes(b'{"seconds_limit": 180, "subscription": {"authMethod": "claude.ai"}}')
        task = bound_task()
        scope = SimpleNamespace(directory=self.directory,
                                inspect=lambda: {'tasks': {'ap11-step-5': {'task_sha256': digest(task), 'work': 'reconciliation'}}})
        from runtime import task as task_module
        built = {}
        def prepare(expected, key, role, work, context, files, extra=None):
            built.update(files); return {'nonce': key}
        (self.directory / 'release/development-context').mkdir(parents=True, exist_ok=True)
        for name, content in (('goal.md', b'G'), ('authority.md', b'A')):
            (self.directory / 'release/development-context' / name).write_bytes(content)
        (self.directory / 'release/office').mkdir(parents=True, exist_ok=True)
        (self.directory / 'release/office/AGENTS.md').write_bytes(b'rules')
        (self.directory / 'contract.json').write_bytes(b'{}')
        with patch.object(host, 'active_scope', return_value=(scope, {'directory': str(self.directory / 'release')})), \
             patch.object(host, 'load', return_value=task), patch.object(host, 'goal_amendments', return_value={}), \
             patch.object(host, 'task_directory', return_value=self.directory / 'task'), \
             patch.object(host, 'read_regular', side_effect=readable), \
             patch.object(task_module, 'evidence_directory', return_value=evidence), \
             patch.object(host, 'git', return_value=b'# reader\n'), \
             patch.object(host, 'prepare_call', side_effect=prepare):
            host.diagnosis_call('expected', 'ap11-step-5', {'phase': 'waiting_review', 'results': []}, 'diag2')
        self.assertIn('review-1-run.json', built, 'the run record is built under a name the delivery point accepts')
        # Review I: re-implementing one clause of the rule is the same shape as the defect this test exists for. The
        # names diagnosis_call really built go through the REAL prepare_call, which owns the rule.
        real = SimpleNamespace(directory=Path(self.temp.name) / 'through')
        (real.directory / 'calls').mkdir(parents=True)
        with patch.object(host, 'active_scope', return_value=(real, {})), patch.object(host, 'policy', return_value=Policy()):
            host.prepare_call('expected', 'through', 'diagnosis', 'reconciliation',
                              {'task': {}, 'actual_child_wait': {}}, built)
        listed = {e['path'] for e in json.loads((real.directory / 'calls/through/workspace/CONTEXT.json').read_text())['delivered_files']['files']}
        self.assertTrue(set(built) <= listed, 'every name the delivery point built survived the real prepare_call')
        record = json.loads(built['review-1-run.json'])
        self.assertEqual((record['exit_code'], record['bound_seconds'], record['events_bytes']), (124, 180, 0))
        self.assertNotIn('subscription', built['review-1-run.json'].decode(), 'no host account material reaches a model')
        self.assertNotIn('authMethod', built['review-1-run.json'].decode())


if __name__ == '__main__':
    unittest.main()
