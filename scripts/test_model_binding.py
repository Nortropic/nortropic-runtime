"""An explicit model choice must reach the provider, and the provider's own identity must confirm it.

The owner chose claude-opus-5 for the remaining AP-11 chain (2026-09-22) and asked that normal changes become
controlled configuration values rather than repeated edits of hardcoded model names. These tests cover the seam
that makes that true, and the guard that keeps it honest: a run that reports a different model than the one
selected is not a valid terminal. The identity check is not widened to make more models selectable.

The init fixtures below have measured shape. They were captured from the pinned CLI on 2026-09-22 running the
real read-only profile - model, claude_code_version, tools, mcp_servers, plugins, slash_commands, apiKeySource -
so a fixture cannot pass where the real receiver would refuse.

No model runs here. The provider in the wire-through test is a plain Python process.
"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import claude_profile, development_interactive as interactive, profile
from runtime.development_host import RUN_FIELDS
from runtime.development_model import models, EXECUTORS
from runtime.development_scope import ScopeClosed
from runtime.provider_result import parse
from scripts.probe_bridge import worker_command

CHOSEN = 'claude-opus-5'
# The init row an actual run under the selected model produced, reduced to the fields parse() reads.
# Review asked for this: the claim "captured from the pinned CLI" has to be checkable from the repo, and
# the premise that the CLI echoes an explicitly selected --model VERBATIM into system/init.model is the
# one everything else rests on. If it normalised the name, every run under a selection would fail the
# identity check while still spending a call.
MEASURED = json.loads(Path('evidence/claude-model-binding/opus5-review-init-shape.json').read_text())


def config(selection=None):
    development = {'id': 'office-ap11', 'executors': {'implementation': 'claude', 'review': 'claude'}}
    if selection is not None:
        development['models'] = selection
    return {'development': development}


def init_event(model=CHOSEN, version=claude_profile.VERSION, tools=None, session='s-1'):
    """An init row built FROM the measured one, varying only what a test is about.

    Deriving it means a fixture cannot quietly describe a shape the real receiver would refuse - which is
    how the first version of these tests was caught, with the wrong tool inventory for the role.
    """
    row = dict(MEASURED['init'], session_id=session, model=model, claude_code_version=version)
    if tools is not None:
        row['tools'] = list(tools)
    return row


def result_event(session='s-1'):
    return {'type': 'result', 'subtype': 'success', 'is_error': False, 'terminal_reason': 'completed',
            'session_id': session, 'total_cost_usd': 0.0, 'permission_denials': [], 'usage': {}}


class ModelSelectionTests(unittest.TestCase):
    def test_an_absent_selection_is_each_profiles_own_qualified_model(self):
        self.assertEqual(models(config()), {'claude': claude_profile.MODEL, 'codex': profile.MODEL})

    def test_an_explicit_choice_is_returned_for_that_executor_only(self):
        chosen = models(config({'claude': CHOSEN}))
        self.assertEqual(chosen['claude'], CHOSEN)
        self.assertEqual(chosen['codex'], profile.MODEL, 'choosing one executor never moves the other')

    def test_a_codex_model_choice_is_refused_while_its_startup_chain_still_picks_its_own(self):
        """Configured-but-not-run is a silent divergence. Until the Codex chain reads this selection,
        naming a different Codex model refuses instead of being accepted and ignored."""
        with self.assertRaises(ScopeClosed):
            models(config({'codex': 'gpt-6-other'}))

    def test_naming_the_codex_baseline_explicitly_is_allowed(self):
        self.assertEqual(models(config({'claude': CHOSEN, 'codex': profile.MODEL})),
                         {'claude': CHOSEN, 'codex': profile.MODEL})

    def test_an_unknown_executor_key_refuses_instead_of_defaulting(self):
        """A misspelt key must not silently leave the chosen model unapplied."""
        with self.assertRaises(ScopeClosed):
            models(config({'claud': CHOSEN}))

    def test_a_singular_key_at_either_level_refuses(self):
        """Mirrors the executors guard: 'model' is not 'models', and neither is a top-level key."""
        with self.assertRaises(ScopeClosed):
            models({'development': {'model': CHOSEN}})
        with self.assertRaises(ScopeClosed):
            models({'models': {'claude': CHOSEN}, 'development': {}})

    def test_an_unusable_name_refuses(self):
        """Found by review: the first rule only rejected empty/blank/leading-dash, so a padded name reached
        argv and failed only after a call was spent, and an embedded NUL made Popen itself raise where the
        caller's preflight handler could not classify it."""
        for bad in ('', '   ', '-anything', None, 5, ['claude-opus-5'],
                    ' claude-opus-5', 'claude-opus-5 ', 'claude\x00opus',
                    'claude-opus-5\n--restricted', 'claude opus 5', 'x' * 200):
            with self.subTest(bad=bad), self.assertRaises(ScopeClosed):
                models(config({'claude': bad}))

    def test_real_model_ids_are_accepted(self):
        """The rule must not be so narrow that the models actually on offer cannot be chosen."""
        for good in ('claude-opus-5', 'claude-opus-5-5', 'claude-sonnet-5', 'claude-fable-5-1',
                     'claude-haiku-4-5-20251001', 'gpt-6-astra'):
            with self.subTest(good=good):
                self.assertEqual(models(config({'claude': good}))['claude'], good)

    def test_the_profile_and_the_selection_apply_the_same_rule(self):
        """A name must not pass one validator and fail the other."""
        for name in (' claude-opus-5', 'claude\x00opus', '-x', '', 'x' * 200):
            with self.subTest(name=name):
                with self.assertRaises(ScopeClosed):
                    models(config({'claude': name}))
                with self.assertRaises(ValueError):
                    claude_profile.selected_model(name)

    def test_the_selection_covers_exactly_the_two_executors(self):
        self.assertEqual(set(EXECUTORS), {'codex', 'claude'})
        self.assertEqual(set(models(config())), set(EXECUTORS))


class CodexBaselineTests(unittest.TestCase):
    """The Codex baseline must be the model its startup chain actually specifies, not a presumed default."""

    def test_the_recorded_baseline_is_what_worker_command_really_specifies(self):
        argv = worker_command()
        self.assertIn('model="%s"' % profile.MODEL, argv,
                      'the recorded Codex model is the one the startup chain actually passes')
        self.assertIn('model_reasoning_effort="%s"' % profile.REASONING_EFFORT, argv,
                      'and so is the recorded reasoning effort')

    def test_the_codex_startup_chain_specifies_exactly_one_model(self):
        specified = [a for a in worker_command() if a.startswith('model=')]
        self.assertEqual(len(specified), 1, 'one explicit model, so there is no ambiguity about what runs')


class ClaudeCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / '.scratch').mkdir()

    def model_of(self, argv):
        return argv[argv.index('--model') + 1]

    def test_the_chosen_model_reaches_the_argument_list(self):
        argv = claude_profile.command(self.workspace, (), writable=False, model=CHOSEN)
        self.assertEqual(self.model_of(argv), CHOSEN)

    def test_no_choice_keeps_the_profiles_qualified_model(self):
        self.assertEqual(self.model_of(claude_profile.command(self.workspace, (), writable=False)),
                         claude_profile.MODEL)

    def test_the_interactive_profile_takes_the_same_choice(self):
        argv = claude_profile.interactive_command(
            self.workspace, 'a plain prompt', self.workspace / '.scratch/answer.json',
            '00000000-0000-4000-8000-000000000000', model=CHOSEN)
        self.assertEqual(self.model_of(argv), CHOSEN)

    def test_an_unusable_name_never_reaches_an_argument_list(self):
        for bad in ('--restricted', '', '  ', 7, 'claude\x00opus', 'claude-opus-5 ', 'a b'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                claude_profile.command(self.workspace, (), writable=False, model=bad)

    def test_the_choice_changes_the_model_and_nothing_else(self):
        """A model choice is not a licence to change the permission profile."""
        base = claude_profile.command(self.workspace, (), writable=False)
        chosen = claude_profile.command(self.workspace, (), writable=False, model=CHOSEN)
        self.assertEqual(len(base), len(chosen))
        differences = [(a, b) for a, b in zip(base, chosen) if a != b]
        self.assertEqual(differences, [(claude_profile.MODEL, CHOSEN)])


class ReportedIdentityTests(unittest.TestCase):
    """Requested is not the same as ran: the provider's own reported identity decides."""

    def test_the_measured_run_shows_the_selected_model_echoed_back_verbatim(self):
        """The premise everything rests on, measured rather than assumed."""
        self.assertEqual(MEASURED['init']['model'], CHOSEN, 'the CLI echoed the selected name unchanged')
        self.assertEqual(MEASURED['init']['claude_code_version'], claude_profile.VERSION)
        self.assertEqual(set(MEASURED['init']['tools']), {'Read', 'StructuredOutput'},
                         'and the review role inventory is unchanged under the selected model')
        self.assertEqual(MEASURED['terminal'],
                         {'is_error': False, 'subtype': 'success', 'terminal_reason': 'completed'})

    def test_a_terminal_reporting_the_selected_model_is_valid(self):
        parsed = parse('claude', [init_event(), result_event()], 'structured', model=CHOSEN)
        self.assertTrue(parsed['valid_terminal'])

    def test_a_terminal_reporting_a_different_model_is_not_this_models_result(self):
        """The substitution guard. Without it, a run that quietly ran another model would be credited here."""
        parsed = parse('claude', [init_event(model='claude-fable-5-1'), result_event()], 'structured', model=CHOSEN)
        self.assertFalse(parsed['valid_terminal'])

    def test_the_default_selection_still_requires_the_profiles_own_model(self):
        self.assertFalse(parse('claude', [init_event(model=CHOSEN), result_event()], 'structured')['valid_terminal'],
                         'an unbound call must still report the qualified model, not any model')
        self.assertTrue(parse('claude', [init_event(model=claude_profile.MODEL), result_event()],
                              'structured')['valid_terminal'])

    def test_the_cli_version_check_is_not_relaxed_by_the_model_choice(self):
        parsed = parse('claude', [init_event(version='2.1.280'), result_event()], 'structured', model=CHOSEN)
        self.assertFalse(parsed['valid_terminal'], 'a different CLI version is a separate qualification')

    def test_the_tool_inventory_check_survives(self):
        parsed = parse('claude', [init_event(tools=('Read', 'Edit', 'Write')), result_event()], 'structured',
                       model=CHOSEN)
        self.assertFalse(parsed['valid_terminal'], 'a reviewer that could edit is still not a reviewer')


class InteractiveAgreementTests(unittest.TestCase):
    """The interactive launch and the interactive completion check must measure the SAME model.

    Found by independent review: the first version of this change wired the launch to the release's choice
    and left the completion check comparing against the hardcoded profile default. That is worse than an
    unverified path - it turns a session that did exactly what it was told into a recorded failure, and an
    interactive start is the scarcest resource in the mission (all approved starts are spent, and a further
    one needs a new owner decision AND a code change).

    The rows have the shape measured from a real session, evidence/claude-office-roles/interactive-session-shape.json.
    """

    def rows(self, model):
        rows = copy.deepcopy(json.loads(
            Path('evidence/claude-office-roles/interactive-session-shape.json').read_text())['rows'])
        for row in rows:
            if row.get('type') == 'assistant' and isinstance(row.get('message'), dict):
                row['message']['model'] = model
        return rows

    def test_a_session_that_ran_the_selected_model_is_accepted(self):
        self.assertEqual(interactive.claude_completed(self.rows(CHOSEN), model=CHOSEN), (False, None))

    def test_a_session_that_ran_a_different_model_than_the_selection_is_refused(self):
        quota, reason = interactive.claude_completed(self.rows(claude_profile.MODEL), model=CHOSEN)
        self.assertEqual(reason, 'Interactive session did not use the pinned CLI and model')
        self.assertFalse(quota)

    def test_with_no_selection_the_profiles_own_model_is_still_required(self):
        self.assertEqual(interactive.claude_completed(self.rows(claude_profile.MODEL)), (False, None))
        self.assertEqual(interactive.claude_completed(self.rows(CHOSEN))[1],
                         'Interactive session did not use the pinned CLI and model')

    def test_the_launch_and_the_check_read_one_and_the_same_value(self):
        """Not a proxy: the argv actually built for the session is fed to the actual checker."""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); (workspace / '.scratch').mkdir()
            with patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'), \
                 patch.object(interactive, 'claude_layers', return_value=None):
                argv = interactive.claude_interactive_command(
                    workspace, 'Prepare A.', '00000000-0000-4000-8000-000000000000', model=CHOSEN)
            launched = argv[argv.index('--model') + 1]
            self.assertEqual(interactive.claude_completed(self.rows(launched), model=CHOSEN), (False, None))


class AttemptWireThroughTests(unittest.TestCase):
    """The real attempt path must carry the release's choice all the way to the launched command.

    The provider is a plain Python process that reports the model it was told to be, so the whole chain -
    release config, profile, launch record and the reported-identity check - is measured without a model call.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'task'; (self.state / 'candidate').mkdir(parents=True)
        (self.state / 'candidate' / 'AGENTS.md').write_text('# workspace\n')
        self.evidence = self.root / 'evidence'; self.evidence.mkdir()

    def run_attempt(self, selection, expect_failure=False):
        from runtime import attempt as attempt_module
        from runtime import release as release_module
        seen = {}

        def spy(workspace, allowed_paths, writable=True, model=None):
            seen['model'] = model
            real = claude_profile.command(workspace, allowed_paths, writable=writable, model=model)
            body = ('import json,sys\n'
                    'sys.stdin.buffer.read()\n'
                    'print(json.dumps(%r))\n'
                    'print(json.dumps(%r))\n' % (init_event(model=seen['model'], tools=('Read', 'Edit', 'Write')),
                                                 result_event()))
            seen['argv'] = real
            return [sys.executable, '-c', body]

        task = {'id': 'wire', 'attempt_seconds': 60, 'allowed_paths': ['tools/x.py'],
                'target': 'Nortropic/nortropic-projektkontor', 'steps': [{'provider': 'claude'}]}
        with patch.object(attempt_module, 'load', return_value=task), \
             patch.object(attempt_module, 'task_directory', return_value=self.state), \
             patch.object(attempt_module, 'evidence_directory', return_value=self.evidence), \
             patch.object(attempt_module, 'claude_command', spy), \
             patch.object(attempt_module, 'require_subscription', return_value={'subscriptionType': 'max'}), \
             patch.object(attempt_module, 'reserve_task_call', return_value=None), \
             patch.object(attempt_module, 'ROOT', self.root), \
             patch.object(release_module, 'require_active_code', return_value=config(selection)), \
             patch.object(release_module, 'require_workspace_instructions', return_value=None), \
             patch.dict(os.environ, {'NR_CONFIG_SHA256': 'x' * 64}):
            # execute() prints its own report; the publication wrapper requires the suite's last line to be OK.
            with contextlib.redirect_stdout(io.StringIO()):
                code = attempt_module.execute('wire', 1, 'a prompt', 30, role='implementation', provider='claude')
        report = json.loads((self.evidence / 'attempt-1' / 'result.json').read_text())
        marker = self.evidence / 'attempt-1' / 'launch.json'
        return code, seen, report, json.loads(marker.read_text()) if marker.is_file() else None

    def test_the_releases_choice_reaches_the_launched_command_and_is_confirmed(self):
        code, seen, report, launch = self.run_attempt({'claude': CHOSEN})
        self.assertEqual(seen['model'], CHOSEN, 'the release configuration decided the model')
        self.assertEqual(seen['argv'][seen['argv'].index('--model') + 1], CHOSEN,
                         'and the real profile put it in the argument list')
        self.assertTrue(report['provider_completed'], 'the reported identity confirmed the selected model')
        self.assertEqual(code, 0)

    def test_an_unbound_release_resolves_to_the_profiles_qualified_model_explicitly(self):
        """An absent selection still yields a named model, so what ran is never left implicit."""
        _, seen, report, _ = self.run_attempt(None)
        self.assertEqual(seen['model'], claude_profile.MODEL)
        self.assertTrue(report['provider_completed'])

    def test_an_invalid_selection_is_a_diagnosable_preflight_failure_not_a_crash(self):
        """Found by review: resolving the selection outside the preflight handler turned a release
        transition or a drifted selection into an uncaught crash with no result.json at all, so the
        diagnosis role received a host-shaped failure with the real cause destroyed."""
        code, _, report, launch = self.run_attempt({'claude': '--restricted'}, expect_failure=True)
        self.assertEqual(code, 1)
        self.assertFalse(report['provider_completed'])
        self.assertIn('Provider preflight failed', report['reason'])
        self.assertIn('model selection', report['reason'])
        self.assertFalse(report['model_started'], 'and no model was started')
        self.assertIsNone(launch, 'no launch marker for a run that never launched')

    def test_the_record_says_which_model_ran_and_which_one_the_provider_reported(self):
        """A release that changes only the selection keeps the same runtime_revision, so the revision no
        longer implies the model. The record has to say it, and the diagnosis has to be able to read it."""
        _, _, report, _ = self.run_attempt({'claude': CHOSEN})
        self.assertEqual(report['model'], CHOSEN)
        self.assertEqual(report['reported_model'], CHOSEN)
        self.assertIn('model', RUN_FIELDS)
        self.assertIn('reported_model', RUN_FIELDS)


if __name__ == '__main__':
    unittest.main()
