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

from runtime import claude_profile, development_interactive as interactive, model_question, profile
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
# The pinned Codex CLI's own resolution of the startup chain's arguments (config/read, no thread, no turn). Codex exec
# reports no model identity in its event stream, so this measured resolution is the premise the Codex choice rests on.
CODEX_MEASURED = json.loads(Path('evidence/codex-model-binding/config-read-shape.json').read_text())


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

    def test_a_codex_choice_is_returned_for_codex_only(self):
        """D022 refused this while the Codex startup chain still picked its own model. That chain now takes the
        chosen name (D028), so the choice is returned, and choosing Codex never moves Claude."""
        chosen = models(config({'codex': 'gpt-6-other'}))
        self.assertEqual(chosen['codex'], 'gpt-6-other')
        self.assertEqual(chosen['claude'], claude_profile.MODEL)

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
            for executor in EXECUTORS:
                with self.subTest(bad=bad, executor=executor), self.assertRaises(ScopeClosed):
                    models(config({executor: bad}))

    def test_real_model_ids_are_accepted(self):
        """The rule must not be so narrow that the models actually on offer cannot be chosen."""
        for good in ('claude-opus-5', 'claude-opus-5-5', 'claude-sonnet-5', 'claude-fable-5-1',
                     'claude-haiku-4-5-20251001', 'gpt-6-astra'):
            with self.subTest(good=good):
                self.assertEqual(models(config({'claude': good}))['claude'], good)

    def test_the_profile_and_the_selection_apply_the_same_rule(self):
        """A name must not pass one validator and fail the other - for either executor's profile."""
        for name in (' claude-opus-5', 'claude\x00opus', '-x', '', 'x' * 200):
            with self.subTest(name=name):
                with self.assertRaises(ScopeClosed):
                    models(config({'claude': name}))
                with self.assertRaises(ScopeClosed):
                    models(config({'codex': name}))
                with self.assertRaises(ValueError):
                    claude_profile.selected_model(name)
                with self.assertRaises(ValueError):
                    profile.selected_model(name)

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


class CodexChoiceTests(unittest.TestCase):
    """The Codex startup chain takes the release's choice as its one model argument (D028).

    Without a choice it must build exactly the command it always built: AP-10's private stage and every
    unbound call use that default, so the default is the part that must not move.
    """
    OTHER = 'gpt-6-other'
    SHAPES = ({'writable': False}, {'writable': True}, {'writable': True, 'allowed_paths': ['tools/a.py']})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def test_no_choice_is_the_recorded_baseline_in_every_shape(self):
        self.assertEqual(worker_command(), worker_command(profile.MODEL))
        self.assertIn('model="gpt-6-astra"', worker_command(), 'the default is the literal baseline, not a lookup')
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                self.assertEqual(profile.command(self.workspace, **shape),
                                 profile.command(self.workspace, **shape, model=profile.MODEL))

    def test_the_choice_is_the_one_model_argument(self):
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                argv = profile.command(self.workspace, **shape, model=self.OTHER)
                self.assertEqual([a for a in argv if a.startswith('model=')], ['model="%s"' % self.OTHER])

    def test_the_choice_changes_the_model_and_nothing_else(self):
        """Not a licence to change the permission profile, the reasoning effort or the subcommand."""
        for shape in self.SHAPES:
            with self.subTest(shape=shape):
                base = profile.command(self.workspace, **shape)
                chosen = profile.command(self.workspace, **shape, model=self.OTHER)
                self.assertEqual(len(base), len(chosen))
                self.assertEqual([(a, b) for a, b in zip(base, chosen) if a != b],
                                 [('model="%s"' % profile.MODEL, 'model="%s"' % self.OTHER)])
                self.assertIn('model_reasoning_effort="%s"' % profile.REASONING_EFFORT, chosen)

    def test_an_unusable_name_never_reaches_the_codex_argument_list(self):
        for bad in ('--restricted', '', '  ', 7, 'gpt\x00astra', 'gpt-6-astra ', 'a b', 'gpt-6-astra"\nsandbox_mode="danger-full-access'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profile.command(self.workspace, writable=False, model=bad)


class CodexResolutionTests(unittest.TestCase):
    """What the pinned Codex CLI itself made of the chain's arguments, measured - and that this code builds them."""

    def test_the_measured_cli_took_the_model_argument_verbatim_from_the_command_line(self):
        for label, case in CODEX_MEASURED['cases'].items():
            with self.subTest(case=label):
                self.assertEqual(case['model_argument'], ['model="%s"' % case['resolved_model']])
                self.assertEqual(case['origin_model'], 'sessionFlags', 'the command line decided, over the owner config')
                self.assertEqual(case['resolved_reasoning_effort'], profile.REASONING_EFFORT,
                                 'and a choice leaves the pinned reasoning effort where it was')
        self.assertEqual(CODEX_MEASURED['cases']['probe_name']['resolved_model'], 'nr-probe.model-1')
        self.assertTrue(CODEX_MEASURED['layer_sets_model']['user'], 'the owner config names a model too: a real override')
        self.assertEqual(set(CODEX_MEASURED['requests']), {'initialize', 'initialized', 'config/read'}, 'no thread, no turn')

    def test_the_measured_arguments_are_the_ones_this_code_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            for label, chosen in (('no_choice', None), ('probe_name', 'nr-probe.model-1')):
                with self.subTest(case=label):
                    argv = profile.command(Path(directory), writable=False, model=chosen)
                    self.assertEqual([a for a in argv if a.startswith('model=')],
                                     CODEX_MEASURED['cases'][label]['model_argument'])

    def test_the_default_was_measured_unchanged_against_the_active_release(self):
        unchanged = CODEX_MEASURED['default_unchanged']
        self.assertTrue(unchanged['worker_command_identical'])
        self.assertEqual(unchanged['identical_per_shape'], dict.fromkeys(('read_only', 'writable', 'allowed', 'interactive'), True))


class PrivateStageBaselineTests(unittest.TestCase):
    """AP-10's private stage is outside the development selection: it launches the recorded baseline."""

    def test_the_private_stage_launches_exactly_the_default_codex_command(self):
        from runtime import private_stage
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / 'stage'; stage.mkdir()
            workspace = Path(directory) / 'workspace'; workspace.mkdir()
            launched = []; real = private_stage.subprocess.Popen

            def popen(argv, *args, **kwargs):
                # Only the provider launch is intercepted; the host's own process reads (ps) still run.
                if argv[0] != profile.command(workspace, writable=False)[0]:
                    return real(argv, *args, **kwargs)
                launched.append(list(argv)); raise OSError('fixture: no provider is started')
            with patch.object(private_stage.subprocess, 'Popen', side_effect=popen), \
                 patch.object(private_stage, 'require_workspace_instructions', return_value={}):
                result = private_stage.model(stage, workspace, 'a prompt', {'type': 'object'}, 5, os.getppid())
            expected = profile.command(workspace, writable=False)
            self.assertEqual(launched, [expected[:-1] + ['--output-schema', str(workspace / 'OUTPUT_SCHEMA.json'), '-']])
            self.assertIn('model="%s"' % profile.MODEL, launched[0])
            self.assertFalse(result['completed'])


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

    def run_codex_attempt(self, selection, bound=True, failure=None):
        """The same real attempt path for a Codex step. The Codex profile is the REAL one; only its launch is a
        plain Python process emitting the measured exec event shape (thread.started, one turn.completed)."""
        from runtime import attempt as attempt_module
        from runtime import release as release_module
        seen = {}

        def spy(workspace, writable=True, allowed_paths=None, model=None):
            seen['model'] = model
            seen['argv'] = profile.command(workspace, writable=writable, allowed_paths=allowed_paths, model=model)
            last = failure or {"type": "turn.completed", "usage": {}}
            body = ('import json,sys\n'
                    'sys.stdin.buffer.read()\n'
                    'print(json.dumps({"type": "thread.started", "thread_id": "t-1"}))\n'
                    'print(json.dumps(%r))\n' % last)
            return [sys.executable, '-c', body]

        task = {'id': 'wire', 'attempt_seconds': 60, 'allowed_paths': ['tools/x.py'],
                'target': 'Nortropic/nortropic-projektkontor', 'steps': [{'provider': 'codex'}]}
        with patch.object(attempt_module, 'load', return_value=task), \
             patch.object(attempt_module, 'task_directory', return_value=self.state), \
             patch.object(attempt_module, 'evidence_directory', return_value=self.evidence), \
             patch.object(attempt_module, 'command', spy), \
             patch.object(attempt_module, 'claude_command', side_effect=AssertionError('a codex step never builds Claude')), \
             patch.object(attempt_module, 'require_subscription', side_effect=AssertionError('no Claude preflight for codex')), \
             patch.object(attempt_module, 'reserve_task_call', return_value=None), \
             patch.object(attempt_module, 'ROOT', self.root), \
             patch.object(profile, 'require_workspace_instructions', return_value=None), \
             patch.object(release_module, 'require_active_code', return_value=config(selection)), \
             patch.object(release_module, 'require_workspace_instructions', return_value=None), \
             patch.object(model_question, 'ROOT', self.root), patch.object(release_module, 'installed', return_value=None), \
             patch.dict(os.environ):
            if bound:
                os.environ['NR_CONFIG_SHA256'] = 'x' * 64
            else:
                os.environ.pop('NR_CONFIG_SHA256', None)
            with contextlib.redirect_stdout(io.StringIO()):
                code = attempt_module.execute('wire', 1, 'a prompt', 30, role='implementation', provider='codex')
        report = json.loads((self.evidence / 'attempt-1' / 'result.json').read_text())
        marker = self.evidence / 'attempt-1' / 'launch.json'
        return code, seen, report, json.loads(marker.read_text()) if marker.is_file() else None

    def test_the_releases_codex_choice_reaches_the_launched_command(self):
        code, seen, report, _ = self.run_codex_attempt({'codex': 'gpt-6-other'})
        self.assertEqual(seen['model'], 'gpt-6-other', 'the release configuration decided the Codex model')
        self.assertEqual([a for a in seen['argv'] if a.startswith('model=')], ['model="gpt-6-other"'],
                         'and the real Codex profile put it in the argument list as its one model')
        self.assertEqual(report['model'], 'gpt-6-other', 'the record says which model was started')
        self.assertTrue(report['provider_completed'])
        self.assertEqual(code, 0)

    def test_a_codex_step_under_a_release_without_a_choice_runs_the_baseline(self):
        _, seen, report, _ = self.run_codex_attempt({'claude': CHOSEN})
        self.assertEqual(seen['model'], profile.MODEL, 'choosing Claude never moves Codex')
        self.assertIn('model="%s"' % profile.MODEL, seen['argv'])
        self.assertEqual(report['model'], profile.MODEL)

    def test_an_unbound_codex_run_keeps_the_baseline(self):
        """No release binding, no lookup: the profile's own recorded model, as before."""
        _, seen, report, _ = self.run_codex_attempt({'codex': 'gpt-6-other'}, bound=False)
        self.assertIsNone(seen['model'])
        self.assertIn('model="%s"' % profile.MODEL, seen['argv'])
        self.assertEqual(report['model'], profile.MODEL)

    def test_an_invalid_codex_selection_is_a_diagnosable_preflight_failure(self):
        code, _, report, launch = self.run_codex_attempt({'codex': '--restricted'})
        self.assertEqual(code, 1)
        self.assertIn('Provider preflight failed', report['reason'])
        self.assertIn('model selection', report['reason'])
        self.assertFalse(report['model_started'])
        self.assertIsNone(launch, 'no launch marker for a run that never launched')

    def test_a_run_without_capacity_asks_the_owner_and_stays_a_failure(self):
        """D030: the provider's own usage-limit words become the owner's question; the run still waits for diagnosis."""
        limit = {'type': 'turn.failed', 'error': {'message': 'You\u2019ve hit your usage limit. try again at Sep 27th, 2026 7:16 PM.'}}
        code, seen, report, _ = self.run_codex_attempt({'codex': 'gpt-6-other'}, failure=limit)
        self.assertEqual(code, 1); self.assertFalse(report['provider_completed'])
        question = json.loads((self.root / report['model_question']).read_text())
        self.assertEqual((question['executor'], question['model']), ('codex', 'gpt-6-other'), 'the model that was started')
        self.assertIn('hit your usage limit', question['provider_said'])
        self.assertEqual(question['where'], {'kind': 'task attempt', 'task': 'wire', 'attempt': 1, 'role': 'implementation'})

    def test_a_failure_that_is_not_capacity_asks_nothing(self):
        code, _, report, _ = self.run_codex_attempt({'codex': 'gpt-6-other'}, failure={'type': 'turn.failed', 'error': {'message': 'stream disconnected'}})
        self.assertEqual(code, 1); self.assertNotIn('model_question', report)
        self.assertFalse(model_question.home().exists())

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
