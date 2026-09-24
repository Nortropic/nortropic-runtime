"""The model-choice question to the owner when the selected model lacks capacity (D030).

The provider wordings are the measured ones: Codex's usage-limit line as its own interactive terminal printed it on
2026-09-21 (preserved in the AP-11 scope, interactive-retry-2/terminal.raw), and Claude's failed terminals in the shapes
scripts/test_claude_driver.py records. No model runs here and nothing outside a temporary directory is written.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import model_question as mq, profile, claude_profile

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
CODEX_LIMIT = ('You’ve hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or '
               'try again at Sep 27th, 2026 7:16 PM.')
CLAUDE_LIMIT = {'type': 'result', 'is_error': True, 'subtype': 'success', 'result': "You've hit your session limit · resets 19:16",
                'session_id': 's'}
CLAUDE_ACCESS = {'type': 'result', 'is_error': True, 'subtype': 'success', 'terminal_reason': 'api_error', 'api_error_status': 403,
                 'result': 'Your organization has disabled Claude subscription access for Claude Code', 'session_id': 's'}


class WordsTests(unittest.TestCase):
    def test_claude_words_are_its_failed_terminal_text_and_status(self):
        self.assertEqual(mq.provider_words('claude', [CLAUDE_LIMIT]), "You've hit your session limit · resets 19:16")
        self.assertEqual(mq.provider_words('claude', [CLAUDE_ACCESS]),
                         'Your organization has disabled Claude subscription access for Claude Code | HTTP 403')

    def test_codex_words_are_its_error_rows_messages(self):
        rows = [{'type': 'error', 'message': CODEX_LIMIT}, {'type': 'turn.failed', 'error': {'message': CODEX_LIMIT}}]
        self.assertEqual(mq.provider_words('codex', rows), CODEX_LIMIT + ' | ' + CODEX_LIMIT)

    def test_agent_text_and_success_terminals_are_never_read(self):
        agent = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'usage limit, quota, session limit'}}
        self.assertIsNone(mq.provider_words('codex', [agent, {'type': 'turn.completed', 'usage': {}}]))
        self.assertIsNone(mq.provider_words('claude', [{'type': 'result', 'is_error': False, 'result': 'usage limit'}]))

    def test_words_are_bounded(self):
        self.assertEqual(len(mq.provider_words('codex', [{'type': 'error', 'message': 'x' * 5000}])), mq.WORDS_BOUND)


class QuestionTests(unittest.TestCase):
    ACTIVE = {'directory': '/h/.runtime/ap10/releases/r', 'files': {mq.TOOL: 'a' * 64}}

    def test_the_question_names_executor_model_and_the_provider_words_and_switches_nothing(self):
        record = mq.question('codex', 'gpt-6-astra', CODEX_LIMIT, {'kind': 'task attempt'}, self.ACTIVE, NOW)
        self.assertIs(record['automatic_switch'], False)
        self.assertIn('gpt-6-astra', record['question']); self.assertIn('codex', record['question'])
        self.assertIn(CODEX_LIMIT, record['question'])
        self.assertEqual([c['choice'] for c in record['choices']], ['vänta', 'byt modell'])

    def test_buying_credits_is_never_offered_even_when_the_provider_suggests_it(self):
        record = mq.question('codex', 'gpt-6-astra', CODEX_LIMIT, {}, self.ACTIVE, NOW)
        self.assertIn('Köp av krediter', record['not_a_choice'])
        self.assertNotIn('purchase', json.dumps(record['choices']))

    def test_the_change_is_the_active_release_tool_for_that_executor(self):
        change = mq.question('claude', 'claude-opus-5', 'limit', {}, self.ACTIVE, NOW)['choices'][1]
        tool = '/h/.runtime/ap10/releases/r/' + mq.TOOL
        self.assertEqual(change['commands']['stage'], '%s -B %s stage --claude <modell>' % (mq.ROOT / '.runtime/temporal-venv/bin/python', tool))
        self.assertEqual(change['commands']['activate'], '%s -B %s activate' % (mq.ROOT / '.runtime/temporal-venv/bin/python', tool))
        self.assertEqual(change['qualified_alternatives'], {'claude-fable-5-1': 'D019'}, 'the refused model is not offered back')

    def test_without_the_tool_in_the_active_release_the_question_says_a_code_transition_is_needed(self):
        change = mq.question('claude', 'claude-opus-5', 'limit', {}, {'directory': '/h/r', 'files': {}}, NOW)['choices'][1]
        self.assertIn('kontrollerad kodövergång', change['commands'])

    def test_codex_has_no_other_qualified_model_and_says_so(self):
        change = mq.question('codex', 'gpt-6-astra', 'limit', {}, self.ACTIVE, NOW)['choices'][1]
        self.assertEqual(change['qualified_alternatives'], {})

    def test_the_qualified_table_names_each_profile_baseline(self):
        self.assertIn(profile.MODEL, mq.QUALIFIED['codex'])
        self.assertIn(claude_profile.MODEL, mq.QUALIFIED['claude'])
        self.assertEqual(set(mq.QUALIFIED), {'claude', 'codex'})


class AskTests(unittest.TestCase):
    def test_one_record_per_event_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(mq, 'home', return_value=Path(directory) / 'q'), \
                patch.object(mq, 'ROOT', Path(directory)), patch('runtime.release.installed', return_value=None):
            first = mq.ask('codex', 'gpt-6-astra', CODEX_LIMIT, {'kind': 'task attempt'}, now=NOW)
            record = json.loads((Path(directory) / first).read_text())
            self.assertEqual((record['executor'], record['model'], record['provider_said']), ('codex', 'gpt-6-astra', CODEX_LIMIT))
            with self.assertRaises(FileExistsError):
                mq.ask('codex', 'gpt-6-astra', CODEX_LIMIT, {}, now=NOW)


if __name__ == '__main__':
    unittest.main()
