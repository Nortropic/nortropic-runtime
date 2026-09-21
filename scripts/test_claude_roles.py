"""Executor-neutral roles: explicit per-role choice, a genuinely read-only reviewer,
and no path from a missing, interrupted or malformed review to approval.

Terminal rows have the shape measured with the pinned CLI (see
evidence/claude-office-roles/review-terminal-shape.json), not an invented one.
"""
import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from runtime import attempt, claude_profile, release, review, task, targets
from runtime.integration import GateClosed, digest, require_gate
from runtime.provider_result import parse

SHAPE = json.loads(Path('evidence/claude-office-roles/review-terminal-shape.json').read_text())


def events(**changes):
    init, result = copy.deepcopy(SHAPE['init']), copy.deepcopy(SHAPE['result'])
    for key, value in changes.items():
        (init if key in init and key not in ('type', 'subtype', 'session_id') else result)[key] = value
    return [init, result]


CREATED = []


def tearDownModule():
    for name in CREATED:
        try: os.unlink(name)
        except OSError: pass


def written(rows, raw=None):
    handle = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False)
    handle.write(raw if raw is not None else ''.join(json.dumps(row) + '\n' for row in rows)); handle.close()
    CREATED.append(handle.name)
    return handle.name


def both(value, **changes):
    """Measured shape: the terminal carries the object AND its exact JSON repeat."""
    return events(structured_output=value, result=json.dumps(value), **changes)


class ExplicitExecutorChoiceTest(unittest.TestCase):
    def office(self, **extra):
        return {'id': 'office-roles-1', 'target': targets.OFFICE, 'base': 'a' * 40, 'runtime_revision': 'b' * 40,
                'allowed_paths': ['tools/kontor_result.py'], 'attempt_seconds': 60, 'automatic_retries': 0,
                'steps': [{'provider': 'claude', 'prompt': 'bounded'}], 'acceptance_sha256': 'c' * 64, **extra}

    def test_office_accepts_each_qualified_executor_and_nothing_else(self):
        self.assertEqual(task.validate(self.office())['steps'][0]['provider'], 'claude')
        codex = self.office(steps=[{'provider': 'codex', 'prompt': 'bounded'}])
        self.assertEqual(task.validate(codex)['steps'][0]['provider'], 'codex')
        for bad in ('gpt', '', None, 'Claude', 'codex,claude'):
            with self.assertRaisesRegex(ValueError, 'Invalid provider step'):
                task.validate(self.office(steps=[{'provider': bad, 'prompt': 'bounded'}]))
        # The host-owned active entry stays outside every executor's write scope.
        with self.assertRaisesRegex(ValueError, 'host-owned'):
            task.validate(self.office(allowed_paths=['tools/kontor.py']))

    def test_reviewer_is_an_explicit_digest_bound_choice_with_codex_as_absent_default(self):
        plain = self.office()
        self.assertNotIn('review_provider', task.validate(plain))
        chosen = task.validate(self.office(review_provider='claude'))
        self.assertEqual(chosen['review_provider'], 'claude')
        self.assertNotEqual(digest(plain), digest(chosen))
        for bad in ('gpt', '', None, ['claude']):
            with self.assertRaisesRegex(ValueError, 'Invalid review provider'):
                task.validate(self.office(review_provider=bad))


class ReadOnlyReviewerTest(unittest.TestCase):
    def test_review_profile_has_no_edit_tool_or_file_grant(self):
        with mock.patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'):
            argv = claude_profile.command('/ws', ['tools/a.py'], writable=False)
            author = claude_profile.command('/ws', ['tools/a.py'], writable=True)
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read')
        grants = argv[argv.index('--allowedTools') + 1:argv.index('--permission-mode')]
        self.assertEqual(grants, ['Read'])
        self.assertFalse([part for part in argv if 'Edit' in part or 'Write' in part])
        self.assertIn('--restricted', argv); self.assertIn('--strict-mcp-config', argv)
        self.assertEqual(author[author.index('--tools') + 1], 'Read,Edit,Write')

    def test_measured_review_terminal_is_valid_only_for_the_review_role(self):
        self.assertTrue(parse('claude', events(), 'review')['valid_terminal'])
        # The same rows are NOT a valid author terminal, and an author inventory is not a reviewer.
        self.assertFalse(parse('claude', events(), 'implementation')['valid_terminal'])
        self.assertFalse(parse('claude', events(tools=['Read', 'Edit', 'Write']), 'review')['valid_terminal'])
        for tools in (['Read', 'StructuredOutput', 'Edit'], ['Read', 'StructuredOutput', 'Write'],
                      ['Read', 'StructuredOutput', 'Bash'], ['Read'], ['StructuredOutput'],
                      ['Read', 'Read', 'StructuredOutput'], 'Read,StructuredOutput', None):
            self.assertFalse(parse('claude', events(tools=tools), 'review')['valid_terminal'], tools)
        with self.assertRaisesRegex(ValueError, 'Unsupported provider role'):
            parse('claude', events(), 'publisher')

    def test_every_non_terminal_or_failed_outcome_is_invalid(self):
        init, result = events()
        for field, value in [('is_error', True), ('is_error', None), ('subtype', 'error_during_execution'),
                             ('terminal_reason', 'interrupted'), ('session_id', 'other')]:
            changed = copy.deepcopy(result); changed[field] = value
            self.assertFalse(parse('claude', [init, changed], 'review')['valid_terminal'], field)
        # Measured interrupted run: init but no result row. Measured bad schema: no rows at all.
        self.assertFalse(parse('claude', [init], 'review')['valid_terminal'])
        self.assertFalse(parse('claude', [], 'review')['valid_terminal'])
        self.assertFalse(parse('claude', [init, result, result], 'review')['valid_terminal'])
        for field, value in [('mcp_servers', [{'name': 'x'}]), ('plugins', ['p']), ('slash_commands', ['exit']),
                             ('apiKeySource', 'ANTHROPIC_API_KEY'), ('model', 'other'), ('claude_code_version', '0')]:
            self.assertFalse(parse('claude', events(**{field: value}), 'review')['valid_terminal'], field)


class VerdictNeverFromMissingEvidenceTest(unittest.TestCase):
    def test_measured_rejection_and_strict_approval(self):
        measured = review.verdict(written(events()), 'claude')
        self.assertEqual(measured['verdict'], 'rejected'); self.assertTrue(measured['blocking_findings'])
        good = {'verdict': 'approved', 'blocking_findings': [], 'summary': 'Whole brief implemented.'}
        self.assertEqual(review.verdict(written(both(good)), 'claude'), good)

    def test_missing_interrupted_malformed_or_conflicting_is_never_a_verdict(self):
        init, result = events()
        good = {'verdict': 'approved', 'blocking_findings': [], 'summary': 'ok'}
        cases = {
            'interrupted: no terminal': ([init], 'Missing review response'),
            'no rows': ([], 'Missing review response'),
            'two terminals': ([init, result, result], 'Missing review response'),
            'error terminal carrying an approval': (both(good, is_error=True), 'Missing review response'),
            'max-turns terminal carrying an approval': (both(good, subtype='error_max_turns'), 'Missing review response'),
            'interrupted terminal carrying an approval': (both(good, terminal_reason='interrupted'), 'Missing review response'),
            'no structured output': (events(structured_output=None), 'Missing review response'),
            'prose only': (events(structured_output=None, result='approved, looks fine'), 'Missing review response'),
            'approved object but prose text': (events(structured_output=good, result='I reject this candidate.'), 'Expecting value'),
            'approved object but fenced text': (events(structured_output=good, result='```json\n{"verdict":"rejected"}\n```'), 'Expecting value'),
            'approved object but no text': (events(structured_output=good, result=None), 'Conflicting structured'),
            'text contradicts object': (events(structured_output=good, result=json.dumps({**good, 'verdict': 'rejected'})), 'Conflicting structured'),
            'duplicate key in repeated text': (events(structured_output=good,
                result='{"verdict":"rejected","verdict":"approved","blocking_findings":[],"summary":"ok"}'), 'Duplicate review JSON key'),
            'approval with findings': (both({**good, 'blocking_findings': ['x']}), 'Conflicting approval'),
            'extra key': (both({**good, 'approved': True}), 'Invalid or unjudgeable'),
            'unknown verdict': (both({**good, 'verdict': 'APPROVED'}), 'Invalid or unjudgeable'),
            'blank summary': (both({**good, 'summary': '  '}), 'Invalid or unjudgeable'),
            'blank finding': (both({'verdict': 'rejected', 'blocking_findings': [' '], 'summary': 's'}), 'Invalid or unjudgeable'),
        }
        for name, (rows, reason) in cases.items():
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, reason):
                review.verdict(written(rows), 'claude')
        # A raw terminal line whose earlier verdict object is hidden by a later duplicate key.
        line = json.dumps(both(good)[1]).replace('"structured_output":', '"structured_output": {"verdict": "rejected"}, "structured_output":', 1)
        with self.assertRaisesRegex(ValueError, 'Duplicate review JSON key'):
            review.verdict(written(None, raw=json.dumps(init) + '\n' + line + '\n'), 'claude')
        with self.assertRaisesRegex(ValueError, 'Unsupported review provider'):
            review.verdict(written(events()), 'gpt')
        # An approving sentence inside assistant prose is not a terminal at all.
        prose = {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': json.dumps(good)}]}}
        with self.assertRaisesRegex(ValueError, 'Missing review response'):
            review.verdict(written([init, prose]), 'claude')

    def test_codex_review_reading_is_unchanged(self):
        good = {'verdict': 'approved', 'blocking_findings': [], 'summary': 'ok'}
        row = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(good)}}
        self.assertEqual(review.verdict(written([row])), good)
        self.assertEqual(review.verdict(written([row]), 'codex'), good)
        with self.assertRaisesRegex(ValueError, 'Missing review response'):
            review.verdict(written([]))

    def test_same_run_can_never_review_itself_whatever_the_executor(self):
        accepted = {'id': 't', 'target': targets.RUNTIME, 'base': 'a' * 40, 'allowed_paths': ['tools/a.py'],
                    'steps': [{'provider': 'claude', 'prompt': 'p'}], 'acceptance_sha256': 'c' * 64,
                    'review_provider': 'claude'}
        subject = {'task_id': 't', 'task_sha256': digest(accepted), 'base': 'a' * 40, 'candidate': 'd' * 40,
                   'completed_steps': [0], 'acceptance_sha256': 'c' * 64, 'implementation_runs': ['session-1']}
        bound = {k: subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
        tests = {**bound, 'scope': 'whole_task', 'terminal_status': 'completed', 'passed': True}
        approval = {**bound, 'scope': 'whole_task', 'terminal_status': 'completed', 'verdict': 'approved',
                    'blocking_findings': [], 'reviewer_provider': 'claude'}
        self.assertTrue(require_gate(accepted, subject, tests, {**approval, 'reviewer_run': 'session-2'}))
        with self.assertRaisesRegex(GateClosed, 'Independent review run missing'):
            require_gate(accepted, subject, tests, {**approval, 'reviewer_run': 'session-1'})
        with self.assertRaises(GateClosed):
            require_gate(accepted, subject, tests, {'terminal_status': 'incomplete', 'reason': 'interrupted'})
        with self.assertRaisesRegex(GateClosed, 'unfinished'):
            require_gate(accepted, subject, tests, {**approval, 'reviewer_run': 'session-2', 'terminal_status': 'incomplete'})


class AttemptRoleBindingTest(unittest.TestCase):
    """attempt.execute itself: the accepted task names the executor for each role."""
    class Reached(Exception):
        pass

    def guard(self, accepted, role, provider):
        with mock.patch.object(attempt, 'load', return_value=accepted), \
             mock.patch.object(attempt, 'task_directory', side_effect=self.Reached):
            attempt.execute(accepted['id'], 1, 'p', 10, role=role, provider=provider,
                            workspace_name='commit-1' if role == 'review' else None)

    def test_only_the_named_executor_passes_the_role_guard(self):
        def accepted(steps, **extra):
            return {'id': 't', 'attempt_seconds': 60, 'steps': [{'provider': s, 'prompt': 'p'} for s in steps], **extra}
        allowed = [(accepted(['codex']), 'implementation', 'codex'), (accepted(['claude']), 'implementation', 'claude'),
                   (accepted(['codex', 'claude']), 'implementation', 'claude'), (accepted(['claude']), 'review', 'codex'),
                   (accepted(['codex'], review_provider='claude'), 'review', 'claude'),
                   (accepted(['claude'], review_provider='codex'), 'review', 'codex')]
        for value, role, provider in allowed:
            with self.subTest(role=role, provider=provider), self.assertRaises(self.Reached):
                self.guard(value, role, provider)
        refused = [(accepted(['codex']), 'implementation', 'claude'), (accepted(['claude']), 'implementation', 'codex'),
                   (accepted(['claude']), 'review', 'claude'), (accepted(['codex'], review_provider='claude'), 'review', 'codex'),
                   (accepted(['codex'], review_provider='codex'), 'review', 'claude'), (accepted(['codex']), 'implementation', 'gpt'),
                   (accepted(['codex'], review_provider='gpt'), 'review', 'gpt')]
        for value, role, provider in refused:
            with self.subTest(role=role, provider=provider), self.assertRaisesRegex(ValueError, 'Unqualified provider/role'):
                self.guard(value, role, provider)

    def launch(self, provider, active=False):
        """Run attempt.execute up to the launch record; the provider process itself is refused."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = root / 'state'; ws = state / 'commit-1'; ws.mkdir(parents=True)
            (ws / 'REVIEW_SCHEMA.json').write_text(json.dumps(review.SCHEMA, indent=2) + '\n')
            evidence = root / 'evidence'; evidence.mkdir()
            accepted = {'id': 't', 'target': targets.OFFICE, 'attempt_seconds': 60, 'allowed_paths': ['tools/a.py'],
                        'steps': [{'provider': 'codex', 'prompt': 'p'}], 'review_provider': provider}
            calls = {}
            def claude(workspace, allowed, writable=True):
                calls['claude'] = {'allowed': list(allowed), 'writable': writable}; return ['pinned-claude', '--tools', 'Read']
            def codex(workspace, writable=True, allowed_paths=None):
                calls['codex'] = {'writable': writable}; return ['codex', 'exec', '-']
            order = []
            env = {'NR_CONFIG_SHA256': 'x'} if active else {}
            with mock.patch.object(attempt, 'ROOT', root), mock.patch.object(attempt, 'load', return_value=accepted), \
                 mock.patch.object(attempt, 'task_directory', return_value=state), \
                 mock.patch.object(attempt, 'evidence_directory', return_value=evidence), \
                 mock.patch.object(attempt, 'claude_command', side_effect=lambda *a, **k: (order.append('command'), claude(*a, **k))[1]), \
                 mock.patch.object(attempt, 'command', side_effect=codex), \
                 mock.patch.object(attempt, 'require_subscription', return_value={'subscriptionType': 'max'}), \
                 mock.patch('runtime.release.require_workspace_instructions', side_effect=lambda w: order.append('guard')), \
                 mock.patch.object(attempt, 'environment', return_value={}), \
                 mock.patch.object(attempt, 'reserve_task_call', return_value=None), \
                 mock.patch.object(attempt.subprocess, 'Popen', side_effect=OSError('provider launch refused in this test')), \
                 mock.patch.dict('os.environ', env, clear=True), redirect_stdout(io.StringIO()):
                code = attempt.execute('t', 1, 'p', 10, role='review', workspace_name='commit-1', provider=provider)
            record = json.loads((evidence / 'review-1/launch.json').read_text())
            report = json.loads((evidence / 'review-1/result.json').read_text())
            return code, record, report, calls, order

    def test_claude_review_launch_is_read_only_with_the_host_schema(self):
        code, record, report, calls, order = self.launch('claude', active=True)
        self.assertEqual(calls, {'claude': {'allowed': ['tools/a.py'], 'writable': False}})
        self.assertEqual(record['command'][:3], ['pinned-claude', '--tools', 'Read'])
        self.assertEqual(record['command'][-2], '--json-schema')
        self.assertEqual(json.loads(record['command'][-1]), review.SCHEMA)
        self.assertEqual(record['role'], 'review'); self.assertEqual(record['provider'], 'claude')
        # Bound instruction inputs are checked BEFORE the command is built and any model could start.
        self.assertEqual(order[:2], ['guard', 'command'])
        # A refused launch is an incomplete review, never a completed one.
        self.assertEqual(code, 1); self.assertFalse(report['provider_completed'])

    def test_codex_review_launch_is_unchanged(self):
        code, record, report, calls, order = self.launch('codex')
        self.assertEqual(calls, {'codex': {'writable': False}})
        self.assertEqual(record['command'][-3], '--output-schema'); self.assertEqual(record['command'][-1], '-')
        self.assertTrue(record['command'][-2].endswith('REVIEW_SCHEMA.json'))
        self.assertNotIn('--json-schema', record['command']); self.assertEqual(order, [])
        self.assertEqual(code, 1); self.assertFalse(report['provider_completed'])


class ManagedSettingsBindingTest(unittest.TestCase):
    def test_managed_claude_inputs_are_part_of_the_instruction_binding(self):
        guards = release.instruction_guards()
        for name in ('managed-settings.json', 'managed-mcp.json', 'CLAUDE.md'):
            self.assertIn('/Library/Application Support/ClaudeCode/' + name, guards)
        # Original Codex bindings are all still present.
        self.assertIn(str(Path.home() / '.codex/config.toml'), guards)


if __name__ == '__main__':
    unittest.main()
