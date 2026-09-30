"""The effort is an explicit release choice per executor (D040), with the same guards as the model choice.

Before D040 every Claude command carried `--effort medium` and the Codex startup chain `model_reasoning_effort="high"`,
written into the profiles. A release without a choice must still build exactly those commands, because every unbound
call and every release made before D040 depend on it. A choice changes the effort argument and nothing else, and a
level that is not a plain word is refused before it can reach an argument list.

No model runs here.
"""
import tempfile
import unittest
from pathlib import Path

from runtime import claude_profile, profile
from runtime.development_model import efforts, EXECUTORS
from runtime.development_scope import ScopeClosed
from scripts.probe_bridge import worker_command

LEVELS = ('low', 'medium', 'high', 'xhigh', 'max', 'ultra')
UNUSABLE = ('--max', '', ' ', 7, 'HIGH', 'high ', 'a b', 'x' * 17, 'max\n', 'hög', 'high"\nsandbox_mode="x')


class EffortSelectionTests(unittest.TestCase):
    def test_an_absent_selection_is_each_profiles_pinned_level(self):
        self.assertEqual(efforts({'development': {}}), {'claude': 'medium', 'codex': 'high'})
        self.assertEqual(efforts({}), {'claude': claude_profile.EFFORT, 'codex': profile.REASONING_EFFORT})

    def test_an_explicit_choice_is_returned_for_that_executor_only(self):
        self.assertEqual(efforts({'development': {'efforts': {'claude': 'max'}}}), {'claude': 'max', 'codex': 'high'})
        self.assertEqual(efforts({'development': {'efforts': {'codex': 'ultra'}}}), {'claude': 'medium', 'codex': 'ultra'})

    def test_an_unknown_executor_key_refuses_instead_of_defaulting(self):
        for chosen in ({'gemini': 'high'}, {'claude': 'high', 'Codex': 'low'}, 'high', ['high'], None):
            with self.subTest(chosen=chosen), self.assertRaises(ScopeClosed):
                efforts({'development': {'efforts': chosen}})

    def test_a_singular_or_misplaced_key_refuses(self):
        for config in ({'development': {'effort': 'high'}}, {'effort': 'high', 'development': {}},
                       {'efforts': {'claude': 'high'}, 'development': {}}, {'development': 'high'}):
            with self.subTest(config=config), self.assertRaises(ScopeClosed):
                efforts(config)

    def test_an_unusable_level_refuses(self):
        for bad in UNUSABLE:
            with self.subTest(bad=bad), self.assertRaises(ScopeClosed):
                efforts({'development': {'efforts': {'claude': bad}}})

    def test_the_real_levels_are_accepted(self):
        for level in LEVELS:
            with self.subTest(level=level):
                self.assertEqual(efforts({'development': {'efforts': {'claude': level, 'codex': level}}}),
                                 {'claude': level, 'codex': level})

    def test_the_selection_covers_exactly_the_two_executors(self):
        self.assertEqual(set(efforts({})), set(EXECUTORS))

    def test_the_profiles_and_the_selection_apply_the_same_rule(self):
        """A level cannot pass the release's check and then fail the profile's, or the other way round."""
        for level in LEVELS + tuple(b for b in UNUSABLE if isinstance(b, str)):
            try:
                efforts({'development': {'efforts': {'claude': level, 'codex': level}}}); selection = True
            except ScopeClosed:
                selection = False
            for check in (claude_profile.selected_effort, profile.selected_effort):
                try:
                    check(level); accepted = True
                except ValueError:
                    accepted = False
                self.assertEqual(accepted, selection, (check.__module__, level))


class ClaudeEffortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name); (self.workspace / '.scratch').mkdir()

    def effort_of(self, argv):
        return argv[argv.index('--effort') + 1]

    def test_no_choice_is_the_pinned_level_in_every_shape(self):
        for writable in (False, True):
            with self.subTest(writable=writable):
                base = claude_profile.command(self.workspace, ('tools/a.py',), writable=writable)
                self.assertEqual(self.effort_of(base), 'medium')
                self.assertEqual(base, claude_profile.command(self.workspace, ('tools/a.py',), writable=writable, effort='medium'))
                self.assertEqual(base.count('--effort'), 1)

    def test_the_choice_changes_the_effort_and_nothing_else(self):
        base = claude_profile.command(self.workspace, (), writable=False)
        chosen = claude_profile.command(self.workspace, (), writable=False, effort='max')
        self.assertEqual(len(base), len(chosen))
        self.assertEqual([(a, b) for a, b in zip(base, chosen) if a != b], [('medium', 'max')])

    def test_the_interactive_profile_takes_the_same_choice(self):
        argv = claude_profile.interactive_command(
            self.workspace, 'a plain prompt', self.workspace / '.scratch/answer.json',
            '00000000-0000-4000-8000-000000000000', effort='xhigh')
        self.assertEqual(self.effort_of(argv), 'xhigh')
        base = claude_profile.interactive_command(
            self.workspace, 'a plain prompt', self.workspace / '.scratch/answer.json', '00000000-0000-4000-8000-000000000000')
        self.assertEqual(self.effort_of(base), 'medium')

    def test_an_unusable_level_never_reaches_an_argument_list(self):
        for bad in UNUSABLE:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                claude_profile.command(self.workspace, (), writable=False, effort=bad)


class CodexEffortTests(unittest.TestCase):
    SHAPES = ({'writable': False}, {'writable': True}, {'writable': True, 'allowed_paths': ['tools/a.py']})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def test_no_choice_is_the_literal_baseline_in_every_shape(self):
        self.assertIn('model_reasoning_effort="high"', worker_command(), 'the default is the literal baseline')
        self.assertEqual(worker_command(), worker_command(profile.MODEL, profile.REASONING_EFFORT))
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                self.assertEqual(profile.command(self.workspace, **shape),
                                 profile.command(self.workspace, **shape, effort=profile.REASONING_EFFORT))

    def test_the_choice_changes_the_effort_and_nothing_else(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                base = profile.command(self.workspace, **shape)
                chosen = profile.command(self.workspace, **shape, effort='ultra')
                self.assertEqual(len(base), len(chosen))
                self.assertEqual([(a, b) for a, b in zip(base, chosen) if a != b],
                                 [('model_reasoning_effort="high"', 'model_reasoning_effort="ultra"')])

    def test_a_model_and_an_effort_choice_together_change_exactly_those_two(self):
        base = profile.command(self.workspace, writable=False)
        chosen = profile.command(self.workspace, writable=False, model='gpt-6-sol', effort='low')
        self.assertEqual([(a, b) for a, b in zip(base, chosen) if a != b],
                         [('model="gpt-6-astra"', 'model="gpt-6-sol"'),
                          ('model_reasoning_effort="high"', 'model_reasoning_effort="low"')])

    def test_an_unusable_level_never_reaches_the_codex_argument_list(self):
        for bad in UNUSABLE:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profile.command(self.workspace, writable=False, effort=bad)


if __name__ == '__main__':
    unittest.main()
