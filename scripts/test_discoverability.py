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
    def schema(self, role):
        return {'type': 'object', 'role': role}

    def instructions(self, role):
        return 'fixture instructions for ' + role


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
        expected = {**files, 'OUTPUT_SCHEMA.json': json.dumps(Policy().schema('driver')).encode()}
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
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.directory = self.root / 'scope'; (self.directory / 'calls').mkdir(parents=True)
        self.release = self.root / 'release'; (self.release / 'development-context').mkdir(parents=True)
        self.decision = b'# Owner decision: one further interactive start after the third retry answered hold\n'
        (self.release / 'development-context/interactive-extension-1.md').write_bytes(self.decision)
        self.review = {'verdict': 'approved', 'blocking_findings': [], 'extends': 'interactive-retry-4', 'after': 'interactive-retry-3',
                       'decision_sha256': sha(self.decision), 'reviewer': 'separate'}
        (self.release / 'development-context/interactive-extension-1-review.json').write_text(json.dumps(self.review))
        self.config = {'directory': str(self.release), 'development': {'interactive_extension': {
            'nonce': 'interactive-retry-4', 'after': 'interactive-retry-3', 'decision': 'interactive-extension-1.md', 'decision_sha256': sha(self.decision),
            'review': 'interactive-extension-1-review.json', 'review_sha256': sha((self.release / 'development-context/interactive-extension-1-review.json').read_bytes())}}}
        self.state = {'control': 'paused', 'tasks': {}, 'calls': [], 'integrated': {}}
        self.scope = SimpleNamespace(directory=self.directory, inspect=lambda: self.state)

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
                (stage / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}}))
                (stage / 'workspace/.scratch').mkdir(parents=True); (stage / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'insufficient'}))
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

    def test_extension_binding_is_read_only_from_the_active_configuration(self):
        self.assertIsNone(interactive.extension({'development': {}}))
        self.assertEqual(interactive.extension(self.config)['nonce'], 'interactive-retry-4')
        for broken in ({**self.config['development']['interactive_extension'], 'nonce': 'interactive-retry-5'},
                       {**self.config['development']['interactive_extension'], 'after': 'interactive-retry-2'},
                       {k: v for k, v in self.config['development']['interactive_extension'].items() if k != 'review'},
                       {**self.config['development']['interactive_extension'], 'extra': 'x'},
                       {**self.config['development']['interactive_extension'], 'decision': '../interactive-extension-1.md'}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                interactive.extension({'directory': str(self.release), 'development': {'interactive_extension': broken}})
        (self.release / 'development-context/interactive-extension-1.md').write_bytes(self.decision + b'edited')
        with self.assertRaisesRegex(ValueError, 'decision or review changed'): interactive.extension(self.config)
        (self.release / 'development-context/interactive-extension-1.md').write_bytes(self.decision)
        for change in ({'verdict': 'rejected'}, {'blocking_findings': ['x']}, {'extends': 'interactive-retry-5'}, {'after': 'interactive-retry-2'}, {'decision_sha256': 'f' * 64}):
            with self.subTest(change=change):
                bad = {**self.review, **change}; raw = json.dumps(bad).encode(); (self.release / 'development-context/interactive-extension-1-review.json').write_bytes(raw)
                config = json.loads(json.dumps(self.config)); config['development']['interactive_extension']['review_sha256'] = sha(raw)
                with self.assertRaisesRegex(ValueError, 'not separately approved'): interactive.extension(config)

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
        self.assertEqual(binding['previous'], 'interactive-retry-3'); self.assertEqual(binding['previous_result_sha256'], sha((third / 'result.json').read_bytes()))
        self.assertEqual(binding['previous_answer_sha256'], sha((third / 'workspace/.scratch/answer.json').read_bytes()))
        self.assertEqual(binding['decision_sha256'], sha(self.decision)); self.assertEqual(binding['review_sha256'], self.config['development']['interactive_extension']['review_sha256'])
        self.assertEqual(self.run_patched(interactive.selected_nonce, self.scope, self.config), 'interactive-retry-4')
        self.assertEqual(self.run_patched(interactive.pending, 'x'), {'contract_sha256': 'x', 'nonce': 'interactive-retry-4', 'input_sha256': binding['input_sha256']})
        self.assertEqual(json.loads((third / 'result.json').read_text())['completed'], True, 'the hold session is never rewritten')
        # No fifth: the extension is not a general retry right.
        with self.assertRaisesRegex(ValueError, 'Only explicit'): self.run_patched(interactive.prepare_retry, 'x', 'fifth')
        # The binding is void if the hold bytes, the answer, or the activated decision differ.
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}, 'x': 1}))
        with self.assertRaisesRegex(ValueError, 'extension evidence changed'): interactive.selected_nonce(self.scope, self.config)
        (third / 'result.json').write_text(json.dumps({'completed': True, 'process_group_removed': True, 'provider': {'thread_id': 'a1ea', 'interactive': True}}))
        (third / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'reworded'}))
        with self.assertRaisesRegex(ValueError, 'extension evidence changed'): interactive.selected_nonce(self.scope, self.config)
        (third / 'workspace/.scratch/answer.json').write_text(json.dumps({'action': 'hold', 'reason': 'insufficient'}))
        other = json.loads(json.dumps(self.config)); other['development']['interactive_extension']['decision_sha256'] = 'e' * 64
        (self.release / 'development-context/interactive-extension-1.md').write_bytes(b'other decision')
        with self.assertRaises(ValueError): interactive.selected_nonce(self.scope, other)
        (self.release / 'development-context/interactive-extension-1.md').write_bytes(self.decision)
        # A DIFFERENT but self-consistent activated extension (other decision, its own approved review) does not fit this binding.
        second = b'# another decision\n'; (self.release / 'development-context/interactive-extension-2.md').write_bytes(second)
        review2 = json.dumps({**self.review, 'decision_sha256': sha(second)}).encode(); (self.release / 'development-context/interactive-extension-2-review.json').write_bytes(review2)
        other = {'directory': str(self.release), 'development': {'interactive_extension': {'nonce': 'interactive-retry-4', 'after': 'interactive-retry-3',
                 'decision': 'interactive-extension-2.md', 'decision_sha256': sha(second), 'review': 'interactive-extension-2-review.json', 'review_sha256': sha(review2)}}}
        self.assertEqual(interactive.extension(other)['decision'], 'interactive-extension-2.md', 'valid on its own')
        with self.assertRaisesRegex(ValueError, 'not the activated one'): interactive.selected_nonce(self.scope, other)
        self.assertEqual(interactive.selected_nonce(self.scope, self.config), 'interactive-retry-4')
        self.assertEqual(interactive.selected_nonce(self.scope), 'interactive-retry-4', 'structural check alone without a configuration')

    def test_whole_goal_evidence_includes_the_hold_answer_and_the_fourth_binding(self):
        self.chain_to_third_hold(); self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        files = interactive.retry_evidence(self.scope, 'interactive-retry-4')
        self.assertIn('interactive/RETRY4_BINDING.json', files); self.assertIn('interactive/retry3-result.json', files); self.assertIn('interactive/retry3-session-exit.json', files)
        self.assertEqual(json.loads(files['interactive/retry3-answer.json'])['action'], 'hold')
        self.assertEqual(json.loads(files['interactive/RETRY4_BINDING.json'])['nonce'], 'interactive-retry-4')
        self.assertNotIn('interactive/retry2-answer.json', files, 'only the hold that the extension follows is added')

    def test_fourth_start_requires_the_explicit_pause_like_every_recovery(self):
        self.chain_to_third_hold(); self.state['control'] = 'active'
        with self.assertRaisesRegex(ValueError, 'Only explicit'): self.run_patched(interactive.prepare_retry, 'x', 'diagnosed')
        self.assertFalse((self.directory / 'interactive-retry-4.json').exists())


if __name__ == '__main__':
    unittest.main()
