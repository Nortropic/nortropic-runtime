"""Discoverability of the delivered context, and the single bound extra interactive start.

Measured cause (interactive-retry-3, 2026-09-22): the restricted Claude profile cannot list directories, CONTEXT.json
named seven of eleven delivered files, and the driver answered hold after guessing some fifty names. The host binding
(input.json workspace_sha256) already knew every file; the reader did not. The fix restates that binding inside
CONTEXT.json for every role at the single delivery point, and the owner's separately reviewed decision allows ONE
further interactive start after that hold, bound to the hold's real bytes, the decision and its review.
"""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import development_host as host
from runtime import development_interactive as interactive


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Policy:
    def schema(self, role, work=None):
        return {'type': 'object', 'role': role, 'work': work}

    def instructions(self, role, work=None):
        return 'fixture instructions for ' + role + ' ' + str(work)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.scope = SimpleNamespace(directory=self.directory)

    def deliver(self, nonce, context, files, extra=None, role='driver'):
        with patch.object(host, 'active_scope', return_value=(self.scope, {})), patch.object(host, 'policy', return_value=Policy()):
            request = host.prepare_call('expected', nonce, role, 'reconciliation', context, files, extra)
        workspace = self.directory / 'calls' / nonce / 'workspace'
        return request, workspace, json.loads((workspace / 'CONTEXT.json').read_text()), json.loads((self.directory / 'calls' / nonce / 'input.json').read_text())

    def test_every_delivered_file_is_listed_with_its_exact_path_hash_and_size(self):
        files = {'authority.md': b'A', 'goal.md': b'G', 'observation.md': b'O', 'VERIFICATION_RECIPE.py': b'def verify(): pass\n',
                 'tools/kontor_result.py': b'# reader\n', 'tools/agarbild.py': b'# ap08\n', 'AGENTS.md': b'# rules\n',
                 'GOAL_AMENDMENT_1.md': b'amend', 'GOAL_AMENDMENT_1_REVIEW.json': b'{}'}
        request, workspace, context, data = self.deliver('interactive-retry-4', {'sources': [{'id': 'goal'}], 'task_id': 't'}, files)
        listed = {e['path']: e for e in context['delivered_files']['files']}
        expected = {**files, 'OUTPUT_SCHEMA.json': json.dumps(Policy().schema('driver', 'reconciliation')).encode()}
        self.assertEqual(set(listed), set(expected), 'exactly the delivered files, and CONTEXT.json itself is not listed')
        for name, content in expected.items():
            self.assertEqual(listed[name]['sha256'], sha(content)); self.assertEqual(listed[name]['size'], len(content))
            self.assertEqual(sha((workspace / name).read_bytes()), sha(content), 'the inventory restates the real bytes on disk')
        self.assertEqual(listed['VERIFICATION_RECIPE.py']['meaning'][:22], 'the FROZEN host verifi')
        for name in ('tools/kontor_result.py', 'tools/agarbild.py', 'AGENTS.md', 'OUTPUT_SCHEMA.json'):
            self.assertIn('meaning', listed[name])
        self.assertEqual(listed['GOAL_AMENDMENT_1.md']['meaning'][:10], 'separately')
        self.assertEqual(context['delivered_files']['named_entries'], ['AGENTS.md', 'OUTPUT_SCHEMA.json', 'VERIFICATION_RECIPE.py', 'tools/agarbild.py', 'tools/kontor_result.py'])
        self.assertEqual(context['delivered_files']['files'], sorted(context['delivered_files']['files'], key=lambda e: e['path']))
        self.assertIn('never guess names', context['delivered_files']['note']); self.assertIn('confers no authority', context['delivered_files']['note'])
        # The host binding still covers CONTEXT.json itself, exactly as before.
        self.assertEqual(set(data['workspace_sha256']), set(expected) | {'CONTEXT.json'})
        self.assertEqual(data['workspace_sha256']['CONTEXT.json'], sha((workspace / 'CONTEXT.json').read_bytes()))
        self.assertEqual(context['sources'], [{'id': 'goal'}], 'the meaning of the sources is untouched by the inventory')
        self.assertEqual(data['prompt'], 'fixture instructions for driver reconciliation', 'instruction and schema are delivered for THIS work')
        self.assertEqual(data['schema'], {'type': 'object', 'role': 'driver', 'work': 'reconciliation'})

    def test_reused_context_gets_the_inventory_of_the_new_workspace_not_the_old_one(self):
        stale = {'note': 'old', 'files': [{'path': 'ghost.md', 'sha256': 'x', 'size': 1}], 'named_entries': ['ghost.md']}
        files = {'goal.md': b'G', 'VERIFICATION_RECIPE.py': b'R'}
        _, _, context, _ = self.deliver('review-1', {'delivered_files': stale, 'sources': []}, files, extra={'DRAFT.json': b'{"draft":1}'}, role='preparation-review')
        paths = [e['path'] for e in context['delivered_files']['files']]
        self.assertEqual(paths, ['DRAFT.json', 'OUTPUT_SCHEMA.json', 'VERIFICATION_RECIPE.py', 'goal.md'])
        self.assertIn('DRAFT.json', context['delivered_files']['named_entries']); self.assertNotIn('ghost.md', json.dumps(context))

    def test_a_source_named_context_json_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'written by the host'):
            self.deliver('x', {}, {'CONTEXT.json': b'{}', 'goal.md': b'G'})

    def test_diagnosis_and_final_review_workspaces_carry_the_inventory_too(self):
        for role, files in (('diagnosis', {'previous-1-result.json': b'{}', 'tools/kontor_result.py': b'r'}),
                            ('final-review', {'NATIVE_HISTORY.json': b'[]', 'interactive/retry3-answer.json': b'{"action":"hold"}', 'AGENTS.md': b'a'})):
            with self.subTest(role=role):
                _, _, context, data = self.deliver('call-' + role, {'sources': []}, files, role=role)
                self.assertEqual({e['path'] for e in context['delivered_files']['files']}, set(files) | {'OUTPUT_SCHEMA.json'})
                self.assertEqual(set(data['workspace_sha256']), set(files) | {'OUTPUT_SCHEMA.json', 'CONTEXT.json'})


class ReviewDeliveryTests(unittest.TestCase):
    """The preparation reviewer's workspace is built from the driver's binding through the same delivery point. The
    driver's binding lists CONTEXT.json and OUTPUT_SCHEMA.json (host-written); re-delivering them was refused since the
    inventory release (found by review D). Only the delivered sources come along; the reviewer gets its own host files."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True); (self.directory / 'drafts').mkdir()
        self.scope = SimpleNamespace(directory=self.directory)

    def test_review_call_redelivers_only_the_driver_sources_and_gets_its_own_context_and_schema(self):
        sources = {'goal.md': b'G', 'VERIFICATION_RECIPE.py': b'R', 'tools/kontor_result.py': b'k', 'AGENTS.md': b'a'}
        with patch.object(host, 'active_scope', return_value=(self.scope, {})), patch.object(host, 'policy', return_value=Policy()):
            host.prepare_call('expected', 'interactive-retry-5', 'driver', 'reconciliation', {'sources': [], 'task_id': 't'}, sources)
            binding = json.loads((self.directory / 'calls/interactive-retry-5/input.json').read_text())['workspace_sha256']
            self.assertIn('CONTEXT.json', binding); self.assertIn('OUTPUT_SCHEMA.json', binding)     # the measured binding form
            draft = json.dumps({'driver_nonce': 'interactive-retry-5', 'work': 'reconciliation', 'context': {'sources': [], 'task_id': 't', 'delivered_files': {'stale': True}}, 'task': {}}).encode()
            (self.directory / 'drafts/interactive-retry-5').mkdir(); (self.directory / 'drafts/interactive-retry-5/draft.json').write_bytes(draft)
            request = host.review_call('expected', {'draft': 'interactive-retry-5', 'sha256': sha(draft)}, 'review-1')
        self.assertEqual(request['nonce'], 'review-1'); workspace = self.directory / 'calls/review-1/workspace'
        context = json.loads((workspace / 'CONTEXT.json').read_text()); data = json.loads((self.directory / 'calls/review-1/input.json').read_text())
        self.assertEqual({e['path'] for e in context['delivered_files']['files']}, set(sources) | {'DRAFT.json', 'OUTPUT_SCHEMA.json'})
        self.assertEqual(set(data['workspace_sha256']), set(sources) | {'DRAFT.json', 'OUTPUT_SCHEMA.json', 'CONTEXT.json'})
        self.assertEqual((workspace / 'DRAFT.json').read_bytes(), draft); self.assertEqual(data['role'], 'preparation-review'); self.assertEqual(data['work'], 'reconciliation')
        self.assertEqual(json.loads((workspace / 'OUTPUT_SCHEMA.json').read_text()), Policy().schema('preparation-review', 'reconciliation'), 'the reviewer schema, not the driver schema')
        for name, content in sources.items():
            self.assertEqual((workspace / name).read_bytes(), content)


class DiagnosisDeliveryTests(unittest.TestCase):
    """The diagnosis role reads through the same delivery point; its recovery must still bind to task and wait (review C)."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        from runtime.integration import digest
        self.task = {'id': 'fixture', 'target': 'Nortropic/nortropic-projektkontor', 'base': 'a' * 40, 'steps': [{'provider': 'claude'}], 'acceptance_sha256': 'b' * 64}
        self.scope = SimpleNamespace(directory=self.directory, inspect=lambda: {'tasks': {'fixture': {'task_sha256': digest(self.task)}}})

    def delivered(self, nonce, state):
        """A diagnosis workspace written by the real prepare_call (inventory included), as diagnosis_call writes it."""
        with patch.object(host, 'active_scope', return_value=(self.scope, {})), patch.object(host, 'policy', return_value=Policy()):
            host.prepare_call('expected', nonce, 'diagnosis', 'reconciliation', {'task': self.task, 'actual_child_wait': state},
                              {'TASK.md': b'brief', 'VERIFICATION_RECIPE.py': b'recipe', 'tools/x.py': b'candidate'})
        context = json.loads((self.directory / 'calls' / nonce / 'workspace/CONTEXT.json').read_text())
        self.assertIn('delivered_files', context); return context

    def recover(self, nonce, state, answer):
        with patch.object(host, 'call_result', return_value={'answer': answer}), patch.object(host, 'load', return_value=self.task):
            return host.recovery_request(self.scope, 'fixture', state, nonce)

    def test_retry_diagnosis_delivered_with_the_inventory_still_yields_the_controlled_hold(self):
        state = {'phase': 'waiting_diagnosis', 'attempts': 1, 'results': [{'candidate': 'c' * 40, 'phase_acceptance_passed': True, 'provider_completed': True, 'thread_id': 'impl'}], 'review_number': 1, 'review_recovery': 'retry'}
        self.delivered('first', state)
        result = self.recover('first', state, {'action': 'retry', 'reason': 'specific diagnosis', 'changed_prerequisite': 'model claims it is fixed'})
        self.assertTrue(result['hold'], 'an unchanged host condition is still a hold, not a host error about the context')

    def test_bound_rejection_delivered_with_the_inventory_still_yields_the_repair_record(self):
        state = {'phase': 'waiting_review', 'attempts': 1, 'results': [{'candidate': 'c' * 40, 'phase_acceptance_passed': True, 'provider_completed': True, 'thread_id': 'impl'}],
                 'review_number': 1, 'review_recovery': 'repair', 'review': {'task_id': 'fixture', 'task_sha256': 'x', 'candidate': 'c' * 40, 'acceptance_sha256': 'b' * 64, 'scope': 'whole_task',
                 'terminal_status': 'completed', 'verdict': 'rejected', 'blocking_findings': ['Frozen requirement X fails for empty input'], 'summary': 'Concrete bounded candidate defect', 'reviewer_run': 'independent'}}
        from runtime.integration import digest
        state['review']['task_sha256'] = digest(self.task)
        self.delivered('first', state)
        result = self.recover('first', state, {'action': 'repair', 'reason': 'specific diagnosis', 'changed_prerequisite': 'Frozen requirement X fails for empty input'})
        self.assertEqual(result['action'], 'repair')

    def test_a_diagnosis_for_another_wait_or_task_is_still_refused(self):
        state = {'phase': 'waiting_diagnosis', 'attempts': 1, 'results': [{'candidate': 'c' * 40, 'phase_acceptance_passed': True, 'provider_completed': True, 'thread_id': 'impl'}], 'review_number': 1, 'review_recovery': 'retry'}
        self.delivered('first', state); other = {**state, 'attempts': 2}
        with self.assertRaisesRegex(ValueError, 'does not apply'):
            self.recover('first', other, {'action': 'retry', 'reason': 'specific diagnosis', 'changed_prerequisite': 'x'})


class ExtensionTests(unittest.TestCase):
    """Extra interactive starts: an ordered list of separately reviewed owner decisions, each bound to how the start it
    follows REALLY ended (hold, or a task the frozen policy refused), never rewriting that ending."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.directory = self.root / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.release = self.root / 'release'; self.ctx = self.release / 'development-context'; self.ctx.mkdir(parents=True)
        self.entries = []
        self.bind('interactive-retry-4', 'interactive-retry-3', 'hold', b'# decision 1: one further start after the hold\n')
        self.config = {'directory': str(self.release), 'development': {'interactive_extensions': list(self.entries)}}
        self.state = {'control': 'paused', 'tasks': {}, 'calls': [], 'integrated': {}}
        self.scope = SimpleNamespace(directory=self.directory, inspect=lambda: self.state)

    def bind(self, nonce, after, outcome, decision, name=None):
        name = name or nonce; (self.ctx / (name + '.md')).write_bytes(decision)
        review = json.dumps({'verdict': 'approved', 'blocking_findings': [], 'extends': nonce, 'after': after, 'previous_outcome': outcome, 'decision_sha256': sha(decision), 'reviewer': 'separate'}).encode()
        (self.ctx / (name + '-review.json')).write_bytes(review)
        entry = {'nonce': nonce, 'after': after, 'previous_outcome': outcome, 'decision': name + '.md', 'decision_sha256': sha(decision), 'review': name + '-review.json', 'review_sha256': sha(review)}
        self.entries.append(entry); return entry

    def end(self, nonce, answer, completed=True):
        stage = self.directory / 'calls' / nonce; stage.mkdir(parents=True, exist_ok=True)
        if not (stage / 'input.json').exists(): (stage / 'input.json').write_text(json.dumps({'nonce': nonce}))
        (stage / 'consumed.json').write_text('{}'); (stage / 'session-exit.json').write_text(json.dumps({'process_absent': True, 'provider_pid': 4242}))
        (stage / 'result.json').write_text(json.dumps({'completed': completed, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}}))
        (stage / 'workspace/.scratch').mkdir(parents=True, exist_ok=True); (stage / 'workspace/.scratch/answer.json').write_text(json.dumps(answer))

    def chain_to_third_hold(self):
        """start, retry-1, retry-2 ended failed with real bindings; retry-3 ENDED COMPLETED with the answer hold (never rewritten)."""
        previous = None
        for nonce in (interactive.NONCE, *interactive.RETRIES):
            stage = self.directory / 'calls' / nonce; stage.mkdir(parents=True); (stage / 'input.json').write_text(json.dumps({'nonce': nonce}))
            if previous:
                (self.directory / interactive.binding_name(nonce)).write_text(json.dumps({'previous': previous, 'nonce': nonce, 'diagnosis': 'diagnosed ' + nonce,
                    'previous_result_sha256': sha((self.directory / 'calls' / previous / 'result.json').read_bytes()), 'input_sha256': sha((stage / 'input.json').read_bytes())}))
            (stage / 'consumed.json').write_text('{}'); (stage / 'session-exit.json').write_text(json.dumps({'process_absent': True, 'provider_pid': 4242}))
            if nonce == interactive.RETRIES[-1]:
                self.end(nonce, {'action': 'hold', 'reason': 'insufficient'})
            else:
                (stage / 'result.json').write_text(json.dumps({'completed': False, 'process_group_removed': True}))
            previous = nonce

    def patches(self, config=None):
        def prepare(*args):
            new = self.directory / 'calls' / args[1]; new.mkdir(); raw = json.dumps({'actual': args[1]}).encode(); (new / 'input.json').write_bytes(raw)
            return {'contract_sha256': 'x', 'nonce': args[1], 'input_sha256': sha(raw)}
        self.calls = []
        def base_context(scope, cfg, work, key, *, paused_interactive_recovery=False):
            self.calls.append((work, key, paused_interactive_recovery)); return {}, {}
        return [patch.object(interactive, 'active_scope', return_value=(self.scope, self.config if config is None else config)),
                patch.object(interactive, 'process_identity', return_value=''), patch.object(interactive.os, 'killpg', side_effect=ProcessLookupError),
                patch.object(interactive.host, 'base_context', side_effect=base_context), patch.object(interactive.host, 'prepare_call', side_effect=prepare)]

    def run_patched(self, function, *args, config=None):
        patches = self.patches(config)
        for p in patches: p.start()
        try:
            return function(*args)
        finally:
            for p in patches: p.stop()

    def test_extension_list_is_read_only_from_the_active_configuration(self):
        self.assertEqual(interactive.extensions({'development': {}}), ())
        self.assertEqual([e['nonce'] for e in interactive.extensions(self.config)], ['interactive-retry-4'])
        e = self.entries[0]
        for broken in ([{**e, 'nonce': 'interactive-retry-5'}], [{**e, 'after': 'interactive-retry-2'}], [{**e, 'previous_outcome': 'refused'}], [{k: v for k, v in e.items() if k != 'review'}],
                       [{**e, 'extra': 'x'}], [{**e, 'decision': '../' + e['decision']}], [e, e], {'nonce': 'x'}, []):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                interactive.extensions({'directory': str(self.release), 'development': {'interactive_extensions': broken}})
        (self.ctx / 'interactive-retry-4.md').write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'decision or review changed'): interactive.extensions(self.config)
        (self.ctx / 'interactive-retry-4.md').write_bytes(b'# decision 1: one further start after the hold\n')
        pristine = (self.ctx / 'interactive-retry-4-review.json').read_bytes()
        for change in ({'verdict': 'rejected'}, {'blocking_findings': ['x']}, {'extends': 'interactive-retry-5'}, {'after': 'interactive-retry-2'}, {'decision_sha256': 'f' * 64}, {'previous_outcome': 'task-refused'}):
            with self.subTest(change=change):
                bad = {**json.loads(pristine), **change}; raw = json.dumps(bad).encode(); (self.ctx / 'interactive-retry-4-review.json').write_bytes(raw)
                config = json.loads(json.dumps(self.config)); config['development']['interactive_extensions'][0]['review_sha256'] = sha(raw)
                with self.assertRaisesRegex(ValueError, 'not separately approved'): interactive.extensions(config)
        (self.ctx / 'interactive-retry-4-review.json').write_bytes(pristine); self.assertEqual(len(interactive.extensions(self.config)), 1)
        # A third decision, however well-formed and approved on its own, has no start to bind: the chain is two long.
        self.bind('interactive-retry-5', 'interactive-retry-4', 'task-refused', b'# decision 2\n'); self.bind('interactive-retry-6', 'interactive-retry-5', 'hold', b'# decision 3\n')
        self.assertEqual(len(interactive.extensions({'directory': str(self.release), 'development': {'interactive_extensions': self.entries[:2]}})), 2)
        with self.assertRaisesRegex(ValueError, 'extension list'): interactive.extensions({'directory': str(self.release), 'development': {'interactive_extensions': list(self.entries)}})

    def test_no_fourth_start_without_the_bound_extension_even_after_a_hold(self):
        self.chain_to_third_hold()
        with self.assertRaisesRegex(ValueError, 'No further interactive start'):
            self.run_patched(interactive.prepare_retry, 'x', 'diagnosed', config={'development': {}})
        self.assertFalse((self.directory / 'interactive-retry-4.json').exists()); self.assertEqual(self.calls, [])

    def test_fourth_start_only_after_a_completed_hold_never_after_a_failed_third(self):
        self.chain_to_third_hold(); third = self.directory / 'calls' / interactive.RETRIES[-1]
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'interactive': True}}))
        with self.assertRaisesRegex(ValueError, 'answered hold'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')   # no native thread identity
        (third / 'result.json').write_text(json.dumps({'completed': False, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea'}}))
        with self.assertRaisesRegex(ValueError, 'answered hold'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}}))
        (third / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'task', 'work': 'reconciliation'}))
        with self.assertRaisesRegex(ValueError, 'answered hold'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        self.assertFalse((self.directory / 'interactive-retry-4.json').exists())

    def test_fourth_start_is_bound_to_the_hold_bytes_the_decision_and_the_review(self):
        self.chain_to_third_hold(); third = self.directory / 'calls' / interactive.RETRIES[-1]
        request = self.run_patched(interactive.prepare_retry, 'x', 'Diagnosed host defect: seven of eleven delivered files named; corrected inventory')
        self.assertEqual(request['nonce'], 'interactive-retry-4'); self.assertEqual(self.calls, [('reconciliation', 'interactive-retry-4', True)])
        binding = json.loads((self.directory / 'interactive-retry-4.json').read_text())
        self.assertEqual((binding['previous'], binding['previous_outcome']), ('interactive-retry-3', 'hold')); self.assertEqual(binding['previous_result_sha256'], sha((third / 'result.json').read_bytes()))
        self.assertEqual(binding['previous_answer_sha256'], sha((third / 'workspace/.scratch/answer.json').read_bytes()))
        self.assertEqual(binding['decision_sha256'], self.entries[0]['decision_sha256']); self.assertEqual(binding['review_sha256'], self.entries[0]['review_sha256'])
        self.assertEqual(self.run_patched(interactive.selected_nonce, self.scope, self.config), 'interactive-retry-4')
        self.assertEqual(self.run_patched(interactive.pending, 'x'), {'contract_sha256': 'x', 'nonce': 'interactive-retry-4', 'input_sha256': binding['input_sha256']})
        self.assertEqual(json.loads((third / 'result.json').read_text())['completed'], True, 'the hold session is never rewritten')
        # No fifth without a second reviewed decision.
        self.end('interactive-retry-4', {'action': 'task', 'work': 'reconciliation', 'depends_on': 'none: prose'})
        with self.assertRaisesRegex(ValueError, 'No further interactive start'): self.run_patched(interactive.prepare_retry, 'x', 'fifth')
        # The binding is void if the hold bytes, the answer, or the activated decision differ.
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}, 'x': 1}))
        with self.assertRaisesRegex(ValueError, 'extension evidence changed'): interactive.selected_nonce(self.scope, self.config)
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}}))
        (third / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'reworded'}))
        with self.assertRaisesRegex(ValueError, 'extension evidence changed'): interactive.selected_nonce(self.scope, self.config)
        (third / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'insufficient'}))
        # A DIFFERENT but self-consistent activated decision (other document, its own approved review) does not fit this binding.
        other_root = self.root / 'other'; other_ctx = other_root / 'development-context'; other_ctx.mkdir(parents=True)
        second = b'# another decision\n'; (other_ctx / 'interactive-retry-4.md').write_bytes(second)
        review2 = json.dumps({'verdict': 'approved', 'blocking_findings': [], 'extends': 'interactive-retry-4', 'after': 'interactive-retry-3', 'previous_outcome': 'hold', 'decision_sha256': sha(second)}).encode(); (other_ctx / 'interactive-retry-4-review.json').write_bytes(review2)
        other = {'directory': str(other_root), 'development': {'interactive_extensions': [{'nonce': 'interactive-retry-4', 'after': 'interactive-retry-3', 'previous_outcome': 'hold',
                 'decision': 'interactive-retry-4.md', 'decision_sha256': sha(second), 'review': 'interactive-retry-4-review.json', 'review_sha256': sha(review2)}]}}
        self.assertEqual(interactive.extensions(other)[0]['decision_sha256'], sha(second), 'valid on its own')
        with self.assertRaisesRegex(ValueError, 'not the activated one'): interactive.selected_nonce(self.scope, other)
        self.assertEqual(interactive.selected_nonce(self.scope, self.config), 'interactive-retry-4')
        self.assertEqual(interactive.selected_nonce(self.scope), 'interactive-retry-4', 'structural check alone without a configuration')

    def test_the_first_extension_binding_as_the_previous_release_wrote_it_is_still_accepted(self):
        """The real interactive-retry-4.json on the host carries exactly these keys (no previous_outcome): the new
        release must accept the chain as it exists on disk, and only the first binding may omit the ending."""
        self.chain_to_third_hold(); self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fourth')
        path = self.directory / 'interactive-retry-4.json'; written = json.loads(path.read_text()); del written['previous_outcome']
        self.assertEqual(sorted(written), ['decision_sha256', 'diagnosis', 'input_sha256', 'nonce', 'previous', 'previous_answer_sha256', 'previous_result_sha256', 'review_sha256'])
        path.write_text(json.dumps(written))
        self.assertEqual(interactive.selected_nonce(self.scope, self.config), 'interactive-retry-4'); self.assertEqual(interactive.selected_nonce(self.scope), 'interactive-retry-4')
        # A first binding that names a wrong ending explicitly is still refused; the omission only ever means hold.
        path.write_text(json.dumps({**written, 'previous_outcome': 'task-refused'}))
        with self.assertRaises(ValueError): interactive.selected_nonce(self.scope, self.config)
        path.write_text(json.dumps(written))
        # The second binding may not omit its ending.
        self.end('interactive-retry-4', {'action': 'task', 'work': 'reconciliation', 'depends_on': 'prose'})
        self.bind('interactive-retry-5', 'interactive-retry-4', 'task-refused', b'# decision 2\n'); self.config['development']['interactive_extensions'] = list(self.entries)
        self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fifth'); fifth = self.directory / 'interactive-retry-5.json'; second = json.loads(fifth.read_text())
        self.assertEqual(second['previous_outcome'], 'task-refused'); del second['previous_outcome']; fifth.write_text(json.dumps(second))
        with self.assertRaisesRegex(ValueError, 'Exact host interactive extension binding'): interactive.selected_nonce(self.scope, self.config)

    def test_fifth_start_follows_only_a_task_the_host_refused_and_never_rewrites_it(self):
        """The fourth retry answered task; the frozen policy refused it (no draft was written). The fifth start is bound to
        exactly that ending; a hold, a failed session, a session whose draft exists, or a rewritten answer does not fit."""
        self.chain_to_third_hold(); self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fourth')
        refused = {'action': 'task', 'work': 'reconciliation', 'depends_on': 'none: first task of the application', 'brief': 'A', 'reason': 'r', 'requirements': [], 'tests': []}
        self.end('interactive-retry-4', refused); fourth = self.directory / 'calls' / 'interactive-retry-4'
        self.bind('interactive-retry-5', 'interactive-retry-4', 'task-refused', b'# decision 2: one further start after the refused task answer\n')
        self.config['development']['interactive_extensions'] = list(self.entries)
        # Wrong outcome named in the second decision: the real ending was a task answer, not a hold.
        wrong = json.loads(json.dumps(self.config)); wrong['development']['interactive_extensions'][1]['previous_outcome'] = 'hold'
        with self.assertRaises(ValueError): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fifth', config=wrong)
        self.assertFalse((self.directory / 'interactive-retry-5.json').exists())
        # And the reverse: a fourth that really answered hold (no draft either) is not a refused task.
        (fourth / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'insufficient'}))
        with self.assertRaisesRegex(ValueError, 'task answer the host refused'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fifth')
        (fourth / 'workspace/.scratch/answer.json').write_text(json.dumps(refused))
        # A draft that exists means the host accepted the task: no refusal to follow.
        (self.directory / 'drafts' / 'interactive-retry-4').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'task answer the host refused'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fifth')
        (self.directory / 'drafts' / 'interactive-retry-4').rmdir(); (self.directory / 'drafts').rmdir()
        request = self.run_patched(interactive.prepare_retry, 'x', 'Diagnosed host defect: depends_on stated as explanation, not identity; contract corrected')
        self.assertEqual(request['nonce'], 'interactive-retry-5'); self.assertEqual(self.calls[-1], ('reconciliation', 'interactive-retry-5', True))
        binding = json.loads((self.directory / 'interactive-retry-5.json').read_text())
        self.assertEqual((binding['previous'], binding['previous_outcome']), ('interactive-retry-4', 'task-refused'))
        self.assertEqual(binding['previous_answer_sha256'], sha((fourth / 'workspace/.scratch/answer.json').read_bytes()))
        self.assertEqual(json.loads((fourth / 'workspace/.scratch/answer.json').read_text()), refused, 'the refused task answer is never rewritten')
        self.assertEqual(interactive.selected_nonce(self.scope, self.config), 'interactive-retry-5')
        # No sixth: the chain of reviewed decisions is exhausted.
        self.end('interactive-retry-5', {'action': 'task', 'work': 'reconciliation', 'depends_on': ''})
        with self.assertRaisesRegex(ValueError, 'Only explicit'): self.run_patched(interactive.prepare_retry, 'x', 'sixth')
        # A binding that names another previous start than the chain's real one is refused (review D's surviving mutant).
        fifth = self.directory / 'interactive-retry-5.json'; kept = fifth.read_text(); fifth.write_text(json.dumps({**json.loads(kept), 'previous': 'interactive-retry-3'}))
        with self.assertRaisesRegex(ValueError, 'Exact host interactive extension binding'): interactive.selected_nonce(self.scope, self.config)
        fifth.write_text(kept)
        # A rewritten fourth answer voids the fifth binding.
        (fourth / 'workspace/.scratch/answer.json').write_text(json.dumps({**refused, 'depends_on': ''}))
        with self.assertRaisesRegex(ValueError, 'extension evidence changed'): interactive.selected_nonce(self.scope, self.config)

    def test_whole_goal_evidence_includes_every_followed_ending_and_binding(self):
        self.chain_to_third_hold(); self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        files = interactive.retry_evidence(self.scope, 'interactive-retry-4')
        self.assertIn('interactive/RETRY4_BINDING.json', files); self.assertIn('interactive/retry3-result.json', files); self.assertIn('interactive/retry3-session-exit.json', files)
        self.assertEqual(json.loads(files['interactive/retry3-answer.json'])['action'], 'hold')
        self.assertNotIn('interactive/retry2-answer.json', files, 'only the endings that extensions follow are added')
        self.end('interactive-retry-4', {'action': 'task', 'work': 'reconciliation', 'depends_on': 'prose'})
        self.bind('interactive-retry-5', 'interactive-retry-4', 'task-refused', b'# decision 2\n'); self.config['development']['interactive_extensions'] = list(self.entries)
        self.run_patched(interactive.prepare_retry, 'x', 'diagnosed fifth')
        files = interactive.retry_evidence(self.scope, 'interactive-retry-5')
        self.assertEqual(json.loads(files['interactive/retry4-answer.json'])['action'], 'task'); self.assertIn('interactive/RETRY5_BINDING.json', files)
        self.assertEqual(json.loads(files['interactive/retry3-answer.json'])['action'], 'hold')

    def test_fourth_start_requires_the_explicit_pause_like_every_recovery(self):
        self.chain_to_third_hold(); self.state['control'] = 'active'
        with self.assertRaisesRegex(ValueError, 'Only explicit'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        self.assertFalse((self.directory / 'interactive-retry-4.json').exists())


if __name__ == '__main__':
    unittest.main()
