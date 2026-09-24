"""Finite-goal roles with an explicit frozen executor: read-only structured calls and
the genuine interactive session. Fake provider processes and measured row shapes
(evidence/claude-office-roles/*.json); explicitly NOT application evidence.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import pty
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import claude_profile, development_host as host, development_interactive as interactive, development_model as model, profile
from runtime.development_scope import Scope, ScopeClosed, initialize
from scripts.test_development_scope import contract

REVIEW = json.loads(Path('evidence/claude-office-roles/review-terminal-shape.json').read_text())
SESSION = json.loads(Path('evidence/claude-office-roles/interactive-session-shape.json').read_text())
ALL_CLAUDE = {'development': {'executors': {role: 'claude' for role in model.ROLES}}}


class ExecutorSelectionTest(unittest.TestCase):
    def test_absent_is_codex_and_only_known_roles_and_executors_are_accepted(self):
        self.assertEqual(set(model.executors({}).values()), {'codex'})
        self.assertEqual(set(model.executors({'development': {'id': 'office-ap11'}}).values()), {'codex'})
        mixed = model.executors({'development': {'executors': {'interactive': 'claude', 'review': 'claude'}}})
        self.assertEqual((mixed['interactive'], mixed['review'], mixed['driver'], mixed['implementation']),
                         ('claude', 'claude', 'codex', 'codex'))
        self.assertEqual(set(model.executors(ALL_CLAUDE).values()), {'claude'})
        for bad in ({'driver': 'gpt'}, {'driver': None}, {'publisher': 'claude'}, {'driver': ['claude']}, ['claude'], 'claude'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ScopeClosed, 'Invalid explicit executor'):
                model.executors({'development': {'executors': bad}})
        # A misspelt selection never silently becomes the Codex default.
        for misplaced in ({'executors': {'driver': 'claude'}}, {'executor': 'claude'}, {'development': {'executor': 'claude'}},
                          {'development': {'executor': {'driver': 'claude'}, 'executors': {}}}, {'development': ['executors']}):
            with self.subTest(misplaced=misplaced), self.assertRaisesRegex(ScopeClosed, 'Invalid explicit executor'):
                model.executors(misplaced)

    def test_child_task_context_carries_exactly_the_frozen_author_and_reviewer_choice(self):
        """Runs the REAL base_context; only its repository, policy and file reads are substituted."""
        content = b'frozen selected text'; digest_ = hashlib.sha256(content).hexdigest()
        work = {'reconciliation': ['tools/development_result.py', 'tools/test_development_result.py']}
        frozen = {'work': work, 'authority_sha256': digest_, 'acceptance_sha256': digest_}
        state = {'control': 'active', 'tasks': {}, 'integrated': {}}
        scope = SimpleNamespace(inspect=lambda: state, directory=Path('/scope'))
        def read(root, name, limit=None):
            return json.dumps(frozen).encode() if name == 'contract.json' else content
        def git(repo, *args, raw=False):
            return content if raw else 'b'*40
        for selection, expected in (({'implementation': 'claude', 'review': 'claude', 'driver': 'claude'}, {'implementation': 'claude', 'review': 'claude'}),
                                    ({'implementation': 'claude'}, {'implementation': 'claude', 'review': 'codex'}),
                                    (None, {'implementation': 'codex', 'review': 'codex'})):
            config = {'office_revision': 'b'*40, 'runtime_revision': 'c'*40, 'directory': '/release',
                      'development': {'id': 'office-ap11', **({'executors': selection} if selection is not None else {})}}
            with patch.object(host, 'policy', return_value=SimpleNamespace(WORK=work, RECIPES={'reconciliation': 'acceptance/recipe.py'})), \
                 patch.object(host, 'repository', return_value=Path('/office')), patch.object(host, 'git', side_effect=git), \
                 patch.object(host, 'read_regular', side_effect=read):
                context, files = host.base_context(scope, config, 'reconciliation', 'step-1')
            self.assertEqual(context['executors'], expected)
            self.assertEqual(json.loads(json.dumps(context))['executors'], expected)  # survives the delivered CONTEXT.json
        with patch.object(host, 'policy', return_value=SimpleNamespace(WORK=work, RECIPES={'reconciliation': 'acceptance/recipe.py'})), \
             patch.object(host, 'repository', return_value=Path('/office')), patch.object(host, 'git', side_effect=git), \
             patch.object(host, 'read_regular', side_effect=read):
            with self.assertRaisesRegex(ScopeClosed, 'Invalid explicit executor'):
                host.base_context(scope, {**config, 'development': {'executors': {'review': 'gpt'}}}, 'reconciliation', 'step-1')


class StructuredCallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.scope = Scope(self.root/'scope', initialize(self.root/'scope', contract()))
        self.nonce = 'fixture-call'; self.stage = self.scope.directory/'calls'/self.nonce
        self.workspace = self.stage/'workspace'; self.workspace.mkdir(parents=True); (self.workspace/'.scratch').mkdir()
        self.schema = {'type': 'object'}
        files = {'CONTEXT.json': b'{"synthetic":true}', 'OUTPUT_SCHEMA.json': json.dumps(self.schema).encode()}
        for name, value in files.items(): (self.workspace/name).write_bytes(value)
        data = {'prompt': 'Synthetic no-model process fixture', 'schema': self.schema, 'work': 'goal', 'role': 'driver',
                'seconds': 5, 'workspace_sha256': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}
        raw = json.dumps(data).encode(); (self.stage/'input.json').write_bytes(raw)
        self.request = {'contract_sha256': self.scope.expected, 'nonce': self.nonce, 'input_sha256': hashlib.sha256(raw).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def rows(self, answer={'action': 'hold'}, **result):
        init = copy.deepcopy(REVIEW['init']); terminal = copy.deepcopy(REVIEW['result'])
        terminal.update(structured_output=answer, result=json.dumps(answer)); terminal.update(result.pop('terminal', {}))
        init.update(result)
        return [init, terminal]

    def run_fixture(self, events, config=ALL_CLAUDE, code=0):
        source = ('import json,sys\nopen("../seen-argv.json","w").write(json.dumps(sys.argv[1:]))\n'
                  'for e in '+repr(events)+': print(json.dumps(e),flush=True)\nsys.exit('+str(code)+')')
        order = []
        def claude(workspace, allowed, writable=True, model=None):
            # The double carries the real signature, including the release's explicit model choice: a
            # stub that silently accepted anything would hide a selection that never reached the profile.
            order.append(('command', tuple(allowed), writable, model)); return [sys.executable, '-u', '-c', source]
        with patch.object(model, 'active_scope', return_value=(self.scope, config)), \
             patch.object(model, 'claude_command', side_effect=claude), \
             patch.object(model, 'command', side_effect=AssertionError('Codex profile must not be built for a claude role')), \
             patch.object(model, 'require_subscription', side_effect=lambda: order.append('subscription')), \
             patch.object(model, 'require_workspace_instructions', side_effect=lambda w: order.append('guard')), \
             patch.object(model, 'environment', return_value={}):
            return model.execute(self.request), order

    def test_measured_terminal_completes_read_only_with_the_host_schema(self):
        result, order = self.run_fixture(self.rows())
        self.assertTrue(result['completed'], result); self.assertEqual(result['answer'], {'action': 'hold'})
        self.assertEqual(order[:3], ['subscription', 'guard', ('command', (), False, claude_profile.MODEL)])
        # The delivered role schema itself, not a file name or the review schema, constrains the answer.
        self.assertEqual(json.loads((self.stage/'seen-argv.json').read_text()), ['--json-schema', json.dumps(self.schema)])
        self.assertEqual(json.loads((self.workspace/'OUTPUT_SCHEMA.json').read_text()), self.schema)
        launch = json.loads((self.stage/'launch.json').read_text()); self.assertEqual(launch['provider'], 'claude')
        self.assertEqual(len(self.scope.inspect()['calls']), 1)
        self.assertEqual(host.call_result(self.scope, self.nonce, 'driver'), result)

    def test_no_answer_without_exactly_one_valid_read_only_terminal(self):
        cases = {'author inventory': self.rows(tools=['Read', 'Edit', 'Write']),
                 'extra write tool': self.rows(tools=['Read', 'StructuredOutput', 'Write']),
                 'interrupted: no terminal': self.rows()[:1],
                 'error terminal': self.rows(terminal={'is_error': True}),
                 'text contradicts object': self.rows(terminal={'result': '{"action":"finish"}'}),
                 'prose instead of repeat': self.rows(terminal={'result': 'hold, I think'})}
        for name, events in cases.items():
            with self.subTest(case=name):
                self.tearDown(); self.setUp(); result, _ = self.run_fixture(events)
                self.assertFalse(result['completed'], name)
        self.tearDown(); self.setUp(); result, _ = self.run_fixture(self.rows(), code=3)
        self.assertFalse(result['completed'])

    def test_quota_wording_persists_as_quota_and_never_switches_executor(self):
        events = self.rows(terminal={'is_error': True, 'subtype': 'success', 'result': "You've hit your session limit · resets 19:16",
                                     'structured_output': None})
        result, _ = self.run_fixture(events, code=1)
        self.assertFalse(result['completed']); self.assertEqual(self.scope.inspect()['control'], 'quota')

    def test_access_status_is_quota_but_quota_words_outside_the_error_text_are_not(self):
        measured = {'is_error': True, 'subtype': 'success', 'terminal_reason': 'api_error', 'api_error_status': 403, 'structured_output': None,
                    'result': 'Your organization has disabled Claude subscription access for Claude Code'}
        result, _ = self.run_fixture(self.rows(terminal=measured), code=1)
        self.assertFalse(result['completed']); self.assertEqual(self.scope.inspect()['control'], 'quota')
        self.tearDown(); self.setUp()
        elsewhere = {'is_error': True, 'result': 'overloaded', 'structured_output': None, 'api_error_status': 529,
                     'usage': {'rate_limit_tier': 'quota'}, 'permission_denials': [{'tool_input': {'file_path': '/authentication/unauthorized'}}]}
        result, _ = self.run_fixture(self.rows(terminal=elsewhere), code=1)
        self.assertFalse(result['completed']); self.assertEqual(self.scope.inspect()['control'], 'active')
        self.tearDown(); self.setUp()
        # A completed answer that merely talks about quota is agent text, never a control change.
        result, _ = self.run_fixture(self.rows(answer={'action': 'hold', 'reason': 'usage limit and quota are discussed here'}))
        self.assertTrue(result['completed'], result); self.assertEqual(self.scope.inspect()['control'], 'active')

    def test_an_event_row_that_is_not_an_object_is_a_preserved_failure(self):
        result, _ = self.run_fixture([self.rows()[0], ['not', 'an', 'object'], self.rows()[1]])
        self.assertFalse(result['completed']); self.assertIn('not an object', result['reason']); self.assertIsNone(result['answer'])
        self.assertEqual(json.loads((self.stage/'result.json').read_text()), result)

    def test_codex_selection_keeps_the_original_route(self):
        events = [{'type': 'thread.started', 'thread_id': 'synthetic'},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"action":"hold"}'}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 1}}]
        source = 'import json\nfor e in '+repr(events)+': print(json.dumps(e),flush=True)'
        with patch.object(model, 'active_scope', return_value=(self.scope, {'development': {'executors': {'review': 'claude'}}})), \
             patch.object(model, 'command', return_value=[sys.executable, '-u', '-c', source, '-']), \
             patch.object(model, 'claude_command', side_effect=AssertionError('driver was not selected as claude')), \
             patch.object(model, 'require_subscription', side_effect=AssertionError('no Claude preflight for a codex role')), \
             patch.object(model, 'require_workspace_instructions', return_value={}), patch.object(model, 'environment', return_value={}):
            result = model.execute(self.request)
        self.assertTrue(result['completed'], result)
        self.assertEqual(json.loads((self.stage/'launch.json').read_text())['provider'], 'codex')

    def test_a_codex_role_is_launched_as_the_releases_codex_model(self):
        """The goal-call route hands the release's Codex choice to the profile (D028), as it does for Claude;
        without one it hands over the recorded baseline by name."""
        events = [{'type': 'thread.started', 'thread_id': 'synthetic'},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"action":"hold"}'}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 1}}]
        source = 'import json\nfor e in '+repr(events)+': print(json.dumps(e),flush=True)'
        for selection, expected in (({'codex': 'gpt-6-other'}, 'gpt-6-other'), (None, profile.MODEL)):
            with self.subTest(selection=selection):
                self.tearDown(); self.setUp(); seen = []
                def codex(workspace, writable=True, allowed_paths=None, model=None):
                    # The real signature: a double that accepted anything would hide a choice that never arrived.
                    seen.append((writable, allowed_paths, model)); return [sys.executable, '-u', '-c', source, '-']
                development = {'executors': {'review': 'claude'}, **({'models': selection} if selection else {})}
                with patch.object(model, 'active_scope', return_value=(self.scope, {'development': development})), \
                     patch.object(model, 'command', side_effect=codex), \
                     patch.object(model, 'claude_command', side_effect=AssertionError('driver was not selected as claude')), \
                     patch.object(model, 'require_subscription', side_effect=AssertionError('no Claude preflight for a codex role')), \
                     patch.object(model, 'require_workspace_instructions', return_value={}), patch.object(model, 'environment', return_value={}):
                    result = model.execute(self.request)
                self.assertTrue(result['completed'], result)
                self.assertEqual(seen, [(False, None, expected)])


SESSION_ID = '0f1e2d3c-4b5a-4978-8695-a4b3c2d1e0f9'

# Stands in for the pinned TUI: raw terminal, one scratch answer, the native record named
# by the host-chosen session id, exit 0 after two Ctrl-C. `mode` selects one deviation.
FAKE_TUI = r"""
import json, os, re, signal, sys, tty
from pathlib import Path
signal.alarm(25)
args = sys.argv[1:]; home = Path(os.environ['HOME']); mode = (home/'mode').read_text(); cwd = os.getcwd()
session = args[args.index('--session-id')+1]
(home/'argv.json').write_text(json.dumps(args)); tty.setraw(0)
rows = [{**r, **({'cwd': cwd} if 'cwd' in r else {}), **({'sessionId': session} if 'sessionId' in r else {})}
        for r in json.loads((home/'rows.json').read_text())]
final = [r for r in rows if r.get('type') == 'assistant'][-1]
if mode == 'interrupted': final['message']['stop_reason'] = 'tool_use'
if mode == 'limit': rows.append({'type': 'assistant', 'isApiErrorMessage': True, 'sessionId': session,
                                 'message': {'content': [{'type': 'text', 'text': "You've hit your session limit"}]}})
if mode == 'other-cwd': rows = [{**r, **({'cwd': cwd+'-elsewhere'} if 'cwd' in r else {})} for r in rows]
if mode == 'not-an-object': rows.insert(3, ['not', 'an', 'object'])
folder = home/'.claude/projects'/re.sub(r'[^A-Za-z0-9]', '-', cwd); folder.mkdir(parents=True, exist_ok=True)
name = '11111111-2222-4333-8444-555555555555' if mode == 'other-session' else session
if mode != 'no-record': (folder/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
Path('.scratch/answer.json').write_text(json.dumps({'action': 'task', 'by': 'fake'}))
if mode == 'grant':
    state = json.loads((home/'.claude.json').read_text()); state['projects'][cwd] = {'hasTrustDialogAccepted': True}
    (home/'.claude.json').write_text(json.dumps(state))
if mode == 'bookkeeping':
    state = json.loads((home/'.claude.json').read_text()); state['numStartups'] = 99
    state['projects'][cwd] = {'hasTrustDialogAccepted': False, 'allowedTools': [], 'mcpServers': {}, 'lastSessionId': session}
    state['projects']['/operator/session'] = {'hasTrustDialogAccepted': True, 'allowedTools': ['Bash']}
    (home/'.claude.json').write_text(json.dumps(state))
os.write(1, b'READY\r\n'); seen = 0
while seen < 2:
    key = os.read(0, 1)
    if not key: break
    seen += key == b'\x03'
sys.exit(3 if mode == 'exit-3' else 0)
"""


class InteractiveClaudeTest(unittest.TestCase):
    def rows(self):
        return copy.deepcopy(SESSION['rows'])

    def test_measured_profile_prompt_first_single_scratch_grant_and_host_session_id(self):
        with patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'):
            argv = claude_profile.interactive_command('/ws', 'Prepare A.', '/ws/.scratch/answer.json', SESSION_ID)
            for prompt, answer, session in (('-p', '/ws/.scratch/answer.json', SESSION_ID), ('  ', '/ws/.scratch/answer.json', SESSION_ID),
                                            ('ok', '/ws/tools/a.py', SESSION_ID), ('ok', '/ws/.scratch/deep/answer.json', SESSION_ID),
                                            ('ok', '/other/.scratch/answer.json', SESSION_ID), ('ok', '/ws/.scratch/answer.json', None),
                                            ('ok', '/ws/.scratch/answer.json', SESSION_ID.upper()), ('ok', '/ws/.scratch/answer.json', '--resume'),
                                            ('ok', '/ws/.scratch/answer.json', SESSION_ID.replace('-', ''))):
                with self.subTest(prompt=prompt, answer=answer, session=session), self.assertRaises(ValueError):
                    claude_profile.interactive_command('/ws', prompt, answer, session)
        self.assertEqual(argv[:4], ['/pinned/claude', 'Prepare A.', '--session-id', SESSION_ID])
        self.assertEqual(argv[argv.index('--model')+1], claude_profile.MODEL)
        self.assertEqual(argv[argv.index('--tools')+1], 'Read,Write')
        self.assertEqual(argv[argv.index('--allowedTools')+1:argv.index('--permission-mode')], ['Read', 'Edit(//ws/.scratch/answer.json)'])
        self.assertEqual(argv[argv.index('--mcp-config')+1], '{"mcpServers":{}}')
        self.assertEqual(json.loads(argv[argv.index('--settings')+1]), claude_profile.SETTINGS)
        self.assertEqual(claude_profile.SETTINGS['permissions'], {'defaultMode': 'dontAsk', 'blockReadsOutsideWorkingDirectories': True})
        self.assertEqual(argv[argv.index('--append-system-prompt-file')+1], '/ws/AGENTS.md')
        for flag in ('--restricted', '--strict-mcp-config', '--disable-slash-commands', '--no-chrome'): self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index('--permission-mode')+1], 'dontAsk')
        for printonly in ('-p', '--output-format', '--no-session-persistence', '--json-schema'): self.assertNotIn(printonly, argv)

    def test_untrusted_chain_and_project_local_layers_are_refused_by_the_command_builder(self):
        workspace = Path('/runtime/.runtime/ap11/application/calls/interactive-retry-3/workspace')
        untrusted = {'projects': {'/runtime': {'hasTrustDialogAccepted': False}, '/other': {'hasTrustDialogAccepted': True}}}
        with patch.object(interactive, 'claude_state', return_value=untrusted):
            with self.assertRaisesRegex(ValueError, 'never answered'): interactive.claude_interactive_command(workspace, 'p', SESSION_ID)
        trusted = {'projects': {'/runtime': {'hasTrustDialogAccepted': True}}}
        with patch.object(interactive, 'claude_state', return_value=trusted), \
             patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'):
            argv = interactive.claude_interactive_command(workspace, 'p', SESSION_ID)
        self.assertEqual(argv[1], 'p'); self.assertIn('Edit(/'+str(workspace/'.scratch/answer.json')+')', argv)
        self.assertEqual(SESSION['untrusted_ancestor_run'], {'trust_dialog_default': 'No, exit', 'returncode': 1, 'model_call': False,
                                                             'session_record': False, 'global_state_changed_keys': 0})
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve(); real = home/'runtime/calls/x/workspace'; real.mkdir(parents=True)
            state = {'projects': {str(home/'runtime'): {'hasTrustDialogAccepted': True}}}
            with patch.object(interactive, 'claude_state', return_value=state), patch.object(interactive.Path, 'home', return_value=home), \
                 patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'):
                interactive.claude_interactive_command(real, 'p', SESSION_ID)
                for layer in ('runtime/.mcp.json', 'runtime/calls/.claude'):
                    (home/layer).mkdir()
                    with self.subTest(layer=layer), self.assertRaisesRegex(ValueError, 'Project-local Claude layers'):
                        interactive.claude_interactive_command(real, 'p', SESSION_ID)
                    (home/layer).rmdir()

    def test_authority_compares_only_global_keys_and_the_delivered_ancestor_chain(self):
        workspace = Path('/runtime/calls/x/workspace')
        state = {'numStartups': 7, 'tipsHistory': {'x': 1}, 'mcpServers': {},
                 'projects': {'/runtime': {'hasTrustDialogAccepted': True, 'allowedTools': [], 'lastCost': 1.0, 'lastSessionId': 'a'},
                              '/operator/session': {'hasTrustDialogAccepted': True, 'allowedTools': []}}}
        before = interactive.claude_authority(state, workspace)
        honest = copy.deepcopy(state); honest.update(numStartups=8, tipsHistory={'x': 2}, cachedGrowthBookFeatures={'f': 1})
        honest['projects']['/runtime'].update(lastCost=2.0, lastSessionId='b')
        # An honest start may add a default entry for its own cwd; the operator's own session keeps writing its entry.
        honest['projects'][str(workspace)] = {'hasTrustDialogAccepted': False, 'allowedTools': [], 'mcpServers': {}, 'mcpContextUris': []}
        honest['projects']['/operator/session'].update(allowedTools=['Bash(git status)'], hasTrustDialogAccepted=False)
        honest['projects']['/unrelated/new'] = {'hasTrustDialogAccepted': True}
        self.assertEqual(interactive.claude_authority(honest, workspace), before)
        self.assertEqual(len(interactive.CLAUDE_AUTHORITY_KEYS), 7)
        grants = {'hasTrustDialogAccepted': True, 'allowedTools': ['Bash'], 'mcpServers': {'m': {}}, 'enabledMcpjsonServers': ['m'],
                  'disabledMcpjsonServers': ['m'], 'hasClaudeMdExternalIncludesApproved': True, 'mcpContextUris': ['u']}
        self.assertEqual(set(grants), set(interactive.CLAUDE_AUTHORITY_KEYS))
        for key, value in grants.items():
            for place in (str(workspace), '/runtime/calls', '/runtime', '/'):
                changed = copy.deepcopy(state); changed['projects'].setdefault(place, {})
                if changed['projects'][place].get(key) == value: changed['projects'][place][key] = None   # a revoked trust is a change too
                else: changed['projects'][place][key] = value
                with self.subTest(key=key, place=place):
                    self.assertNotEqual(interactive.claude_authority(changed, workspace), before)
        for key, value in (('mcpServers', {'m': {}}), ('bypassPermissionsModeAccepted', True), ('customApiKeyResponses', {'approved': ['k']})):
            with self.subTest(key=key):
                self.assertNotEqual(interactive.claude_authority({**copy.deepcopy(state), key: value}, workspace), before)

    def test_measured_session_is_a_completed_turn_and_every_deviation_is_not(self):
        self.assertEqual(interactive.claude_completed(self.rows()), (False, None))
        def last(rows): return [r for r in rows if r.get('type') == 'assistant'][-1]
        def cut(rows): last(rows)['message']['stop_reason'] = 'tool_use'
        def model_(rows): last(rows)['message']['model'] = '<synthetic>'
        def version(rows): rows[[i for i, r in enumerate(rows) if r.get('version')][0]]['version'] = '9.9.9'
        def tool(rows): last(rows)['message']['content'].append({'type': 'tool_use', 'name': 'Bash'})
        for name, change, expected in (('interrupted before end_turn', cut, 'no actual completed turn'),
                                       ('other model', model_, 'pinned CLI and model'), ('other version', version, 'pinned CLI and model'),
                                       ('unqualified tool', tool, 'Unqualified interactive tool use')):
            rows = self.rows(); change(rows)
            quota, reason = interactive.claude_completed(rows)
            self.assertFalse(quota); self.assertIn(expected, reason, name)
        self.assertEqual(interactive.claude_completed([r for r in self.rows() if r.get('type') != 'assistant'])[1],
                         'Interactive session has no actual completed turn')

    def test_assumed_provider_error_row_is_classified_only_by_its_own_wording(self):
        """The provider-error row shape is ASSUMED, not measured: an honest session has no such row."""
        def failed(text, **extra):
            return self.rows() + [{'type': 'assistant', 'isApiErrorMessage': True, 'message': {'model': '<synthetic>',
                                   'content': [{'type': 'text', 'text': text}]}, **extra}]
        self.assertEqual(interactive.claude_completed(failed("You've hit your session limit")), (True, 'Interactive provider error'))
        self.assertEqual(interactive.claude_completed(failed('overloaded')), (False, 'Interactive provider error'))
        # Quota words elsewhere in the same row (paths, usage fields) are not the provider's error wording.
        self.assertEqual(interactive.claude_completed(failed('overloaded', cwd='/quota/authentication', usage={'rate_limit': 1})),
                         (False, 'Interactive provider error'))
        self.assertEqual(interactive.claude_completed(self.rows() + [{'type': 'error', 'error': 'Rate limit reached'}]),
                         (True, 'Interactive provider error'))
        text = self.rows() + [{'type': 'assistant', 'isApiErrorMessage': True, 'message': {'content': 'usage limit reached'}}]
        self.assertEqual(interactive.claude_completed(text), (True, 'Interactive provider error'))

    def test_native_record_is_the_one_named_by_the_host_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve(); workspace = home/'runtime/.runtime/ap11/application/calls/x/workspace'
            folder = home/'.claude/projects/any-directory-name'; folder.mkdir(parents=True)
            def record(target, cwd, session, extra=()):
                rows = [{**r, **({'cwd': cwd} if 'cwd' in r else {}), **({'sessionId': session} if 'sessionId' in r else {})} for r in self.rows()]
                target.write_text(''.join(json.dumps(r)+'\n' for r in [*rows, *extra]))
            with patch.object(interactive.Path, 'home', return_value=home):
                with self.assertRaisesRegex(ValueError, 'Exactly one'): interactive.claude_session(workspace, SESSION_ID)
                record(folder/'unrelated-session.jsonl', str(workspace), 'unrelated-session')     # never opened: another name
                with self.assertRaisesRegex(ValueError, 'Exactly one'): interactive.claude_session(workspace, SESSION_ID)
                record(folder/(SESSION_ID+'.jsonl'), str(workspace), SESSION_ID)
                identity, raw, source = interactive.claude_session(workspace, SESSION_ID)
                self.assertEqual((identity, source), (SESSION_ID, 'claude-interactive'))
                self.assertEqual(raw, (folder/(SESSION_ID+'.jsonl')).read_bytes())
                for name, cwd, session, extra in (('other cwd', str(workspace)+'-elsewhere', SESSION_ID, ()),
                                                  ('other identity inside', str(workspace), 'another', ()),
                                                  ('two identities', str(workspace), SESSION_ID, ({'sessionId': 'another', 'type': 'mode'},))):
                    record(folder/(SESSION_ID+'.jsonl'), cwd, session, extra)
                    with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'identity unavailable'):
                        interactive.claude_session(workspace, SESSION_ID)
                record(folder/(SESSION_ID+'.jsonl'), str(workspace), SESSION_ID, (['not', 'an', 'object'],))
                with self.assertRaisesRegex(ValueError, 'not an object'): interactive.claude_session(workspace, SESSION_ID)
                record(folder/(SESSION_ID+'.jsonl'), str(workspace), SESSION_ID)
                second = home/'.claude/projects/second'; second.mkdir(); record(second/(SESSION_ID+'.jsonl'), str(workspace), SESSION_ID)
                with self.assertRaisesRegex(ValueError, 'Exactly one'): interactive.claude_session(workspace, SESSION_ID)
                (second/(SESSION_ID+'.jsonl')).unlink(); (folder/(SESSION_ID+'.jsonl')).rename(second/'kept.jsonl')
                (folder/(SESSION_ID+'.jsonl')).symlink_to(second/'kept.jsonl')
                with self.assertRaisesRegex(ValueError, 'Exactly one'): interactive.claude_session(workspace, SESSION_ID)


class InteractiveExecuteTest(unittest.TestCase):
    """The REAL execute() through two real PTYs; only the provider binary, its checks and the release lookup are substituted."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve(); self.home = self.root/'home'
        self.scope = Scope(self.root/'runtime/scope', self.make_scope())
        self.stage = self.scope.directory/'calls'/interactive.NONCE; self.workspace = self.stage/'workspace'
        (self.workspace/'.scratch').mkdir(parents=True)
        files = {'CONTEXT.json': b'{"synthetic":true}', 'OUTPUT_SCHEMA.json': b'{"type":"object"}', 'AGENTS.md': b'# synthetic\n'}
        for name, value in files.items(): (self.workspace/name).write_bytes(value)
        data = {'prompt': 'Synthetic no-model interactive fixture.', 'schema': {'type': 'object'}, 'work': 'reconciliation', 'role': 'driver',
                'seconds': 5, 'workspace_sha256': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}
        raw = json.dumps(data).encode(); (self.stage/'input.json').write_bytes(raw)
        self.request = {'contract_sha256': self.scope.expected, 'nonce': interactive.NONCE, 'input_sha256': hashlib.sha256(raw).hexdigest()}
        (self.home/'.claude/projects').mkdir(parents=True)
        (self.home/'rows.json').write_text(json.dumps(SESSION['rows'])); (self.home/'fake_tui.py').write_text(FAKE_TUI)
        self.trust(True)

    def make_scope(self):
        (self.root/'runtime').mkdir(parents=True)
        return initialize(self.root/'runtime/scope', contract())

    def tearDown(self):
        self.temp.cleanup()

    def trust(self, accepted):
        (self.home/'.claude.json').write_text(json.dumps({'numStartups': 1, 'projects': {str(self.root/'runtime'): {'hasTrustDialogAccepted': accepted}}}))

    def run_session(self, mode, config=ALL_CLAUDE, keys=True, subscription=None):
        (self.home/'mode').write_text(mode); order = []; launched = []; real = subprocess.Popen
        def popen(argv, *args, **kwargs):
            if argv[0] != '/pinned/claude': return real(argv, *args, **kwargs)
            order.append('launch'); launched.append(list(argv))
            return real([sys.executable, '-B', str(self.home/'fake_tui.py'), *argv[1:]], *args, **kwargs)
        keyboard, terminal = pty.openpty(); done = threading.Event()
        def operator():     # the operator's single closing action: Ctrl-C until the session has gone
            while not (self.stage/'terminal.raw').exists() or b'READY' not in (self.stage/'terminal.raw').read_bytes():
                if done.wait(.05): return
            while not done.wait(.3): os.write(keyboard, b'\x03')
        thread = threading.Thread(target=operator, daemon=True)
        with open(terminal, 'rb', buffering=0, closefd=False) as stdin, open(os.devnull, 'w') as quiet, \
             patch.object(interactive, 'active_scope', return_value=(self.scope, config)), \
             patch.object(interactive.Path, 'home', return_value=self.home), \
             patch.object(interactive, 'require_workspace_instructions', side_effect=lambda w: order.append('guard')), \
             patch.object(claude_profile, 'require_subscription', side_effect=subscription or (lambda: order.append('subscription'))), \
             patch.object(claude_profile, 'qualified_binary', return_value='/pinned/claude'), \
             patch.object(interactive, 'interactive_command', side_effect=AssertionError('Codex TUI must not be built for a claude selection')), \
             patch.object(interactive, 'environment', return_value={'HOME': str(self.home), 'PATH': os.environ.get('PATH', '')}), \
             patch.object(interactive.subprocess, 'Popen', side_effect=popen), \
             patch.object(sys, 'stdin', stdin), patch.object(sys, 'stdout', quiet):
            if keys: thread.start()
            try: return interactive.execute(self.request), order, launched
            finally:
                done.set(); thread.join(5) if keys else None
                os.close(keyboard); os.close(terminal)

    def test_genuine_session_end_hands_off_the_answer_under_the_host_session_id(self):
        result, order, launched = self.run_session('honest')
        self.assertTrue(result['completed'], result); self.assertEqual(result['answer'], {'action': 'task', 'by': 'fake'})
        self.assertEqual(order, ['guard', 'subscription', 'launch', 'guard'])
        delivered = json.loads((self.stage/'interactive-input.json').read_text()); session = delivered['session_id']
        self.assertEqual(delivered['provider'], 'claude')
        self.assertEqual(result['provider'], {'thread_id': session, 'valid_terminal': True, 'interactive': True})
        argv = json.loads((self.home/'argv.json').read_text())
        self.assertEqual(argv[1:3], ['--session-id', session]); self.assertEqual(argv, launched[0][1:])
        self.assertIn('(two Ctrl-C)', argv[0]); self.assertEqual(argv[0], delivered['prompt'])
        # The handover names the only way a reader without directory listing finds the delivered files (retry-3 hold, 2026-09-22).
        self.assertIn('cannot list directories', delivered['prompt']); self.assertIn('CONTEXT.json delivered_files', delivered['prompt'])
        self.assertIn('VERIFICATION_RECIPE.py', delivered['prompt']); self.assertIn('never guess names', delivered['prompt'])
        ended = json.loads((self.stage/'session-exit.json').read_text())
        self.assertEqual((ended['exit_code'], ended['process_absent'], ended['process_group_removed'], ended['session_source']),
                         (0, True, True, 'claude-interactive'))
        self.assertIn(b'\x03', (self.stage/'operator-input.raw').read_bytes())
        self.assertEqual((self.stage/'native-interactive-session.jsonl').read_bytes(),
                         next((self.home/'.claude/projects').glob('*/'+session+'.jsonl')).read_bytes())
        self.assertEqual(host.call_result(self.scope, interactive.NONCE, 'driver'), result)
        self.assertEqual([c['nonce'] for c in self.scope.inspect()['calls']], [interactive.NONCE])

    def test_a_session_started_on_the_releases_chosen_model_is_accepted_as_completed(self):
        """The launch and the completion check must read ONE value, through the real execute().

        Independent review found the first version of the model binding launching the TUI with the
        release's choice while claude_completed still compared against the hardcoded default - a session
        that did exactly what it was told would have been recorded as a failure and burned an interactive
        start, the scarcest resource in the mission. Testing claude_completed alone does not catch a call
        site that stops passing the model, so this drives the whole path.
        """
        chosen = 'claude-opus-5'
        rows = copy.deepcopy(SESSION['rows'])
        for row in rows:
            if row.get('type') == 'assistant' and isinstance(row.get('message'), dict):
                row['message']['model'] = chosen
        (self.home / 'rows.json').write_text(json.dumps(rows))
        selected = copy.deepcopy(ALL_CLAUDE); selected['development']['models'] = {'claude': chosen}
        result, _, launched = self.run_session('honest', config=selected)
        self.assertTrue(result['completed'], result)
        self.assertEqual(launched[0][launched[0].index('--model') + 1], chosen,
                         'the session was started as the chosen model')
        self.assertEqual(result['provider']['valid_terminal'], True)

    def test_a_session_that_ran_a_different_model_than_the_release_chose_is_not_completed(self):
        """The other direction: the agreement must not be achieved by checking nothing."""
        selected = copy.deepcopy(ALL_CLAUDE); selected['development']['models'] = {'claude': 'claude-opus-5'}
        result, _, _ = self.run_session('honest', config=selected)   # rows still report the default model
        self.assertFalse(result['completed'])
        self.assertIn('pinned CLI and model', result['reason'])

    def test_honest_bookkeeping_and_another_sessions_entry_do_not_fail_the_handoff(self):
        result, _, _ = self.run_session('bookkeeping')
        self.assertTrue(result['completed'], result)

    def test_no_deviation_becomes_a_completed_handoff(self):
        cases = {'interrupted': 'no actual completed turn', 'grant': 'authority state changed', 'other-session': 'Exactly one',
                 'no-record': 'Exactly one', 'other-cwd': 'identity unavailable', 'not-an-object': 'not an object', 'exit-3': 'exit/cleanup'}
        for mode, expected in cases.items():
            with self.subTest(mode=mode):
                self.tearDown(); self.setUp(); result, _, _ = self.run_session(mode)
                self.assertFalse(result['completed'], mode); self.assertIsNone(result['answer']); self.assertIn(expected, result['reason'])
                self.assertEqual(self.scope.inspect()['control'], 'paused')
                self.assertEqual(json.loads((self.stage/'result.json').read_text()), result)
                with self.assertRaises(ValueError): host.call_result(self.scope, interactive.NONCE, 'driver')
                self.assertEqual(len(self.scope.inspect()['calls']), 1)     # consumed once, never refunded

    def test_provider_limit_persists_as_quota_and_selects_no_other_executor(self):
        result, order, launched = self.run_session('limit')
        self.assertFalse(result['completed']); self.assertIn('quota/access', result['reason'])
        self.assertEqual(self.scope.inspect()['control'], 'quota'); self.assertEqual(len(launched), 1)

    def test_every_refusal_precedes_consumption_so_the_slot_stays_deliverable(self):
        self.trust(False)
        with self.assertRaisesRegex(ValueError, 'never answered'): self.run_session('honest', keys=False)
        (self.workspace.parent/'.mcp.json').write_text('{}'); self.trust(True)
        with self.assertRaisesRegex(ValueError, 'Project-local Claude layers'): self.run_session('honest', keys=False)
        (self.workspace.parent/'.mcp.json').unlink()
        def lost(): raise ValueError('Previously qualified subscription path is not active; no API fallback')
        with self.assertRaisesRegex(ValueError, 'no API fallback'): self.run_session('honest', keys=False, subscription=lost)
        self.assertFalse((self.stage/'consumed.json').exists()); self.assertEqual(self.scope.inspect()['calls'], [])
        self.assertFalse((self.home/'argv.json').exists())
        result, _, _ = self.run_session('honest')
        self.assertTrue(result['completed'], result)
        with self.assertRaises(FileExistsError): self.run_session('honest', keys=False)     # a consumed call is never replayed
        self.assertEqual(len(self.scope.inspect()['calls']), 1)

    def test_codex_selection_never_builds_the_claude_session(self):
        (self.home/'mode').write_text('honest')
        with patch.object(interactive, 'active_scope', return_value=(self.scope, {'development': {'executors': {'driver': 'claude'}}})), \
             patch.object(interactive, 'require_workspace_instructions', return_value={}), \
             patch.object(interactive, 'claude_interactive_command', side_effect=AssertionError('interactive was not selected as claude')), \
             patch.object(claude_profile, 'require_subscription', side_effect=AssertionError('no Claude preflight for a codex selection')), \
             patch.object(interactive, 'interactive_command', side_effect=ValueError('codex route reached')), \
             patch.object(interactive.os, 'isatty', return_value=True):
            with self.assertRaisesRegex(ValueError, 'codex route reached'): interactive.execute(self.request)
        self.assertFalse((self.stage/'consumed.json').exists())

    def test_the_codex_interactive_route_is_given_the_releases_codex_model(self):
        """One value per session for either executor (D028): the Codex launch takes the release's choice, and
        it is resolved before anything is consumed."""
        (self.home/'mode').write_text('honest'); seen = []
        def codex(workspace, prompt, model=None):
            seen.append(model); raise ValueError('codex route reached')
        for selection in ({'codex': 'gpt-6-other'}, None):
            development = {'executors': {'driver': 'claude'}, **({'models': selection} if selection else {})}
            with patch.object(interactive, 'active_scope', return_value=(self.scope, {'development': development})), \
                 patch.object(interactive, 'require_workspace_instructions', return_value={}), \
                 patch.object(interactive, 'claude_interactive_command', side_effect=AssertionError('interactive was not selected as claude')), \
                 patch.object(claude_profile, 'require_subscription', side_effect=AssertionError('no Claude preflight for a codex selection')), \
                 patch.object(interactive, 'interactive_command', side_effect=codex), \
                 patch.object(interactive.os, 'isatty', return_value=True):
                with self.assertRaisesRegex(ValueError, 'codex route reached'): interactive.execute(self.request)
        self.assertEqual(seen, ['gpt-6-other', profile.MODEL])
        self.assertFalse((self.stage/'consumed.json').exists())


class PreflightAndPendingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.directory = self.root/'runtime/scope'; (self.directory/'calls').mkdir(parents=True)
        self.scope = SimpleNamespace(directory=self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_preflight_refuses_before_anything_is_bound(self):
        state = {'projects': {str(self.root/'runtime'): {'hasTrustDialogAccepted': True}}}; order = []
        def run(config=ALL_CLAUDE, tty=True, state=state, subscription=None):
            with patch.object(interactive, 'active_scope', return_value=(self.scope, config)), patch.object(interactive.os, 'isatty', return_value=tty), \
                 patch.object(interactive, 'claude_state', return_value=state), patch.object(interactive.Path, 'home', return_value=self.root), \
                 patch.object(claude_profile, 'require_subscription', side_effect=subscription or (lambda: order.append('subscription'))):
                return interactive.preflight('expected')
        self.assertEqual(run(), 'claude'); self.assertEqual(order, ['subscription'])
        with self.assertRaisesRegex(ValueError, 'real interactive terminal'): run(tty=False)
        with self.assertRaisesRegex(ValueError, 'never answered'): run(state={'projects': {}})
        def lost(): raise ValueError('Previously qualified subscription path is not active; no API fallback')
        with self.assertRaisesRegex(ValueError, 'no API fallback'): run(subscription=lost)
        with self.assertRaisesRegex(ScopeClosed, 'Invalid explicit executor'): run(config={'development': {'executors': {'interactive': 'gpt'}}})
        (self.directory/'.claude').mkdir()
        with self.assertRaisesRegex(ValueError, 'Project-local Claude layers'): run()
        order.clear(); self.assertEqual(run(config={}, state={'projects': {}}), 'codex'); self.assertEqual(order, [])
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ['.claude', 'calls'])    # a preflight writes nothing

    def test_control_runs_the_preflight_before_status_binding_resume_or_signal(self):
        from runtime import development_control as control
        order = []
        async def operate(action, reason=None):
            order.append(action); return {'native': {'phase': 'waiting_control', 'children': []}}
        def refuse(expected): order.append('preflight'); raise ValueError('No already trusted ancestor')
        for action in ('interactive-retry', 'interactive-start'):
            order.clear()
            with patch.object(control, 'delegate', return_value=None), patch.object(control, 'require_active_code', return_value={'development': {'contract_sha256': 'x'}}), \
                 patch.object(control, 'operate', side_effect=operate), patch.object(interactive, 'preflight', side_effect=refuse), \
                 patch.object(interactive, 'prepare_retry', side_effect=AssertionError('bound after a refusal')), \
                 patch.object(interactive, 'prepare', side_effect=AssertionError('prepared after a refusal')), \
                 patch.object(interactive, 'pending', side_effect=AssertionError('selected after a refusal')), \
                 patch.object(sys, 'argv', ['control', action, '--reason', 'diagnosed']):
                with self.assertRaisesRegex(ValueError, 'trusted ancestor'): control.main()
            self.assertEqual(order, ['preflight'])

    def test_control_delivers_a_bound_unconsumed_slot_again_instead_of_binding_another(self):
        from runtime import development_control as control
        order = []; request = {'contract_sha256': 'x', 'nonce': 'interactive-retry-3', 'input_sha256': 'i'}
        async def operate(action, reason=None):
            order.append(action); return {'native': {'phase': 'waiting_control', 'children': []}}
        with patch.object(control, 'delegate', return_value=None), patch.object(control, 'require_active_code', return_value={'development': {'contract_sha256': 'x'}}), \
             patch.object(control, 'operate', side_effect=operate), patch.object(interactive, 'preflight', side_effect=lambda e: order.append('preflight')), \
             patch.object(interactive, 'pending', side_effect=lambda e: order.append('pending') or request), \
             patch.object(interactive, 'prepare_retry', side_effect=AssertionError('the last slot must not be bound twice')), \
             patch.object(interactive, 'execute', side_effect=lambda r: order.append(('execute', r['nonce'])) or {'completed': True}), \
             patch.object(sys, 'argv', ['control', 'interactive-retry', '--reason', 'diagnosed']), patch('builtins.print'):
            self.assertEqual(control.main(), 0)
        self.assertEqual(order, ['preflight', 'status', 'pending', 'resume', ('execute', 'interactive-retry-3')])

    def chain(self, last):
        """Real bindings for start -> ... -> last, every earlier attempt actually ended as failed."""
        names = (interactive.NONCE, *interactive.RETRIES); previous = None
        for nonce in names[:names.index(last)+1]:
            stage = self.directory/'calls'/nonce; stage.mkdir(parents=True); (stage/'input.json').write_text(json.dumps({'nonce': nonce}))
            if previous:
                (self.directory/interactive.binding_name(nonce)).write_text(json.dumps({'previous': previous, 'nonce': nonce, 'diagnosis': 'diagnosed '+nonce,
                    'previous_result_sha256': hashlib.sha256((self.directory/'calls'/previous/'result.json').read_bytes()).hexdigest(),
                    'input_sha256': hashlib.sha256((stage/'input.json').read_bytes()).hexdigest()}))
            if nonce != last:
                (stage/'consumed.json').write_text('{}'); (stage/'result.json').write_text(json.dumps({'completed': False, 'nonce': nonce}))
                (stage/'session-exit.json').write_text(json.dumps({'ended': nonce}))
            previous = nonce

    def test_pending_is_only_the_selected_retry_that_never_reached_consumption(self):
        with patch.object(interactive, 'active_scope', return_value=(self.scope, {})):
            (self.directory/'calls'/interactive.NONCE).mkdir(); (self.directory/'calls'/interactive.NONCE/'input.json').write_text('{}')
            self.assertIsNone(interactive.pending('x'))                       # the first call is never re-delivered by a retry
            (self.directory/'calls'/interactive.NONCE/'input.json').unlink(); (self.directory/'calls'/interactive.NONCE).rmdir()
            self.chain('interactive-retry-3'); stage = self.directory/'calls/interactive-retry-3'
            self.assertEqual(interactive.pending('x'), {'contract_sha256': 'x', 'nonce': 'interactive-retry-3',
                             'input_sha256': hashlib.sha256((stage/'input.json').read_bytes()).hexdigest()})
            (stage/'consumed.json').write_text('{}'); self.assertIsNone(interactive.pending('x'))
            (stage/'consumed.json').unlink(); (stage/'result.json').write_text('{}'); self.assertIsNone(interactive.pending('x'))
            (stage/'result.json').unlink(); (stage/'input.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'retry evidence changed'): interactive.pending('x')

    def test_whole_goal_evidence_carries_every_binding_and_every_earlier_end(self):
        self.chain('interactive-retry-3')
        files = interactive.retry_evidence(self.scope, 'interactive-retry-3')
        self.assertEqual(sorted(files), sorted(['interactive/RETRY_BINDING.json', 'interactive/RETRY2_BINDING.json', 'interactive/RETRY3_BINDING.json',
            *('interactive/'+prefix+name for prefix in ('previous-', 'retry1-', 'retry2-') for name in ('session-exit.json', 'result.json'))]))
        self.assertEqual(json.loads(files['interactive/RETRY3_BINDING.json'])['nonce'], 'interactive-retry-3')
        self.assertEqual(json.loads(files['interactive/RETRY_BINDING.json'])['nonce'], 'interactive-retry-1')
        self.assertEqual(json.loads(files['interactive/previous-result.json'])['nonce'], interactive.NONCE)
        self.assertEqual(json.loads(files['interactive/retry2-session-exit.json']), {'ended': 'interactive-retry-2'})
        self.assertEqual(sorted(interactive.retry_evidence(self.scope, 'interactive-retry-2')), sorted(['interactive/RETRY_BINDING.json',
            'interactive/RETRY2_BINDING.json', *('interactive/'+prefix+name for prefix in ('previous-', 'retry1-') for name in ('session-exit.json', 'result.json'))]))
        self.assertEqual(interactive.retry_evidence(self.scope, interactive.NONCE), {})

    def test_the_real_whole_goal_preparation_delivers_the_complete_retry_chain(self):
        """Runs the REAL development_final.prepare(); only remote/native reads and the final call writer are substituted."""
        from runtime import development_final as final
        self.chain('interactive-retry-3'); stage = self.directory/'calls/interactive-retry-3'
        for name in ('interactive-input.json', 'session-exit.json', 'result.json'): (stage/name).write_text(json.dumps({'last': name}))
        (stage/'operator-input.raw').write_bytes(b'\x03\x03'); (self.directory/'journal.jsonl').write_text(json.dumps({'event': {'kind': 'control', 'reason': 'fixture', 'value': 'active'}, 'previous': 'd'*64, 'sequence': 1, 'sha256': 'e'*64})+'\n')
        # Every real scope has its head record beside the journal; the delivery binds the journal to it.
        (self.directory/'head.json').write_text(json.dumps({'sequence': 1, 'sha256': 'e'*64}))
        evidence = self.directory/'qualification'; evidence.mkdir(); (evidence/'g2.md').write_text('interval')
        (evidence/'index.json').write_text(json.dumps({'observed_at': 'now', 'scope': 'G1-G10',
                                                       'files': {'g2.md': hashlib.sha256(b'interval').hexdigest()}}))
        release = self.root/'release'; (release/'development-context').mkdir(parents=True); (release/'office').mkdir()
        for name in ('development-context/authority.md', 'development-context/goal.md', 'office/AGENTS.md'): (release/name).write_text(name)
        # The preparation now reads the release's own Office copy for the artefacts the first whole-goal review
        # named as missing: the frozen acceptance recipes that produced the acceptance, and the reader the
        # candidates reuse. The fixture has to carry the shape the REAL POLICY has, or it proves nothing: bare
        # names here once matched a reader that doubled the directory, and the real second assessment refused.
        # Measured in the Office policy the releases carry (tools/development_policy.py at df5ed5dc): RECIPES maps
        # each work to a path relative to the Office root, 'acceptance/ap11_reconciliation.py'.
        (release/'office/tools').mkdir(); (release/'office/acceptance').mkdir()
        (release/'office/tools/development_policy.py').write_text(
            'WORK = {"reconciliation": [], "handoff": []}\n'
            'RECIPES = {"reconciliation": "acceptance/recipe_a.py", "handoff": "acceptance/recipe_b.py"}\n')
        (release/'office/tools/kontor_result.py').write_text('def render(goal):\n    return goal\n')
        (release/'office/tools/agarbild.py').write_text('def owner_view(result):\n    return result\n')
        (release/'office/acceptance/recipe_a.py').write_text('# frozen acceptance for A\n')
        (release/'office/acceptance/recipe_b.py').write_text('# frozen acceptance for B\n')
        (self.directory/'drafts').mkdir(exist_ok=True)
        for work in ('step-5', 'step-28'):
            (self.directory/'drafts'/work).mkdir(); (self.directory/'drafts'/work/'frozen.json').write_text(
                json.dumps({'task': work}))
        goal = hashlib.sha256(b'development-context/goal.md').hexdigest(); (self.directory/'contract.json').write_text(json.dumps({'acceptance_sha256': goal}))
        (release/'development-context/amendment-a.md').write_text('amendment'); amended = hashlib.sha256(b'amendment').hexdigest()
        (release/'development-context/amendment-a-review.json').write_text(json.dumps({'reviewer': 'separate context', 'verdict': 'approved',
                                                                                         'sha256': amended, 'amends_sha256': goal}))
        bound = [{'file': 'amendment-a.md', 'sha256': amended, 'review': 'amendment-a-review.json',
                  'review_sha256': hashlib.sha256((release/'development-context/amendment-a-review.json').read_bytes()).hexdigest()}]
        receipt = {'url': 'https://example.invalid/pull/1', 'candidate': 'c'*40, 'tree': 't'*40,
                   'merge_commit': 'm'*40}
        state = {'integrated': {work: {'task': work, 'receipt': receipt} for work in ('reconciliation', 'handoff')},
                 'calls': [{'nonce': 'step-4', 'role': 'preparation-review', 'work': 'reconciliation'}]}
        scope = SimpleNamespace(directory=self.directory, expected='x', inspect=lambda: state)
        report = {'verified_delivery': True, 'integration': receipt, 'state': {'results': [{'workspace_name': 'w'}]}}
        # The real signature: histories, the watch status, and which of them were read live versus from a
        # verified archive. A double that returned the old pair would hide a caller that stopped saying so.
        async def native(applications, task_ids): return {}, {}, {}
        delivered = {}; examined = {}
        def call(expected, key, role, work, context, files): delivered.update(files); examined.update(context); return {'nonce': key}
        with patch.object(final, 'load', side_effect=lambda name: {'id': name, 'base': 'b'*40,
                 'allowed_paths': ['tools/%s.py' % name, 'tools/test_%s.py' % name]}), \
             patch.object(final, 'git', side_effect=lambda *a, **k: b'# candidate\n'), \
             patch.object(final, 'repository', side_effect=lambda target: target), patch.object(final, 'inspect', return_value=report), \
             patch.object(final, 'task_directory', return_value=self.root), patch.object(final, 'native_evidence', side_effect=native), \
             patch.object(final, 'Publisher', return_value=SimpleNamespace(api=lambda path: {}, reconcile=lambda *a: receipt)), \
             patch.object(final.host, 'prepare_call', side_effect=call):
            final.prepare(scope, {'directory': str(release), 'runtime_revision': 'r', 'office_revision': 'o', 'config_sha256': 'c',
                                  'development': {'amendments': bound}}, 'step-9')
        # The whole-goal examiner judges against the goal AS AMENDED, with the review record beside it.
        self.assertEqual(delivered['GOAL_AMENDMENT_1.md'], b'amendment'); self.assertIn('GOAL_AMENDMENT_1_REVIEW.json', delivered)
        self.assertEqual([(n['path'], n['sha256']) for n in examined['goal_amendments']], [('GOAL_AMENDMENT_1.md', amended)])
        expected = interactive.retry_evidence(scope, 'interactive-retry-3')
        self.assertEqual(len(expected), 9); self.assertEqual({name: delivered.get(name) for name in expected}, expected)
        self.assertEqual(json.loads(delivered['interactive/result.json']), {'last': 'result.json'})
        self.assertEqual(json.loads(delivered['interactive/OPERATOR_INPUT.json']), {'bytes_hex': '0303'})
        # The recipes arrive under the policy's own relative path, with the bytes the release carries.
        self.assertEqual(delivered['acceptance/recipe_a.py'], b'# frozen acceptance for A\n')
        self.assertEqual(delivered['acceptance/recipe_b.py'], b'# frozen acceptance for B\n')
        self.assertFalse([name for name in delivered if name.startswith('acceptance/acceptance/')])
        # Both reused readers arrive with the bytes the release's own Office copy carries; D027 adds the owner view,
        # under the name the reviewer's instructions give it.
        self.assertEqual(delivered['office/kontor_result.py'], b'def render(goal):\n    return goal\n')
        self.assertEqual(delivered['tools/agarbild.py'], b'def owner_view(result):\n    return result\n')


class FreezeExecutorsTest(unittest.TestCase):
    def freeze(self, selection, steps, review_provider=None):
        """Runs the REAL freeze() up to the first read after the executor cross-check."""
        task = {'id': 't', 'steps': [{'provider': p} for p in steps], 'acceptance': 'acceptance/recipe.py', 'allowed_paths': ['tools/a.py'],
                **({'review_provider': review_provider} if review_provider else {})}
        packet = {'driver_run': 'driver', 'work': 'reconciliation', 'task': task, 'context': {'base': 'b'*40}, 'brief': 'x'}
        raw = json.dumps(packet).encode()
        scope = SimpleNamespace(directory=Path('/scope'), inspect=lambda: {'control': 'active'})
        config = {'directory': '/release', 'development': {'executors': selection} if selection is not None else {}}
        def read(root, name, limit=None):
            if name in ('draft.json', 'DRAFT.json'): return raw
            raise LookupError('passed the executor cross-check')
        active = SimpleNamespace(review=lambda answer: True, RECIPES={'reconciliation': 'acceptance/recipe.py'}, WORK={'reconciliation': ['tools/a.py']})
        with patch.object(host, 'active_scope', return_value=(scope, config)), patch.object(host, 'read_regular', side_effect=read), \
             patch.object(host, 'call_result', return_value={'provider': {'thread_id': 'reviewer'}, 'answer': {}}), \
             patch.object(host, 'policy', return_value=active), patch.object(host, 'repository', return_value=Path('/office')), \
             patch.object(host, 'git', side_effect=lambda repo, *args, **kw: 'b'*40 if args[0] == 'rev-parse' else ''), \
             patch('runtime.task.validate', return_value=None):
            host.freeze('x', {'draft': 'd', 'sha256': hashlib.sha256(raw).hexdigest()}, 'review-1')

    def test_a_frozen_task_carries_exactly_the_releases_author_and_reviewer(self):
        for selection, steps, reviewer in ((None, ['codex'], None), ({'implementation': 'claude'}, ['claude', 'claude'], None),
                                           ({'implementation': 'claude', 'review': 'claude'}, ['claude'], 'claude'),
                                           ({'review': 'claude', 'driver': 'claude'}, ['codex'], 'claude')):
            with self.subTest(ok=(selection, steps, reviewer)), self.assertRaisesRegex(LookupError, 'passed the executor cross-check'):
                self.freeze(selection, steps, reviewer)
        for selection, steps, reviewer in ((None, ['claude'], None), (None, ['codex'], 'claude'), ({'implementation': 'claude'}, ['codex'], None),
                                           ({'implementation': 'claude'}, ['claude', 'codex'], None), ({'review': 'claude'}, ['codex'], None),
                                           ({'implementation': 'claude', 'review': 'claude'}, ['claude'], 'codex'),
                                           ({'implementation': 'claude'}, ['claude'], 'claude')):
            with self.subTest(refused=(selection, steps, reviewer)), self.assertRaisesRegex(ValueError, 'Task executors differ'):
                self.freeze(selection, steps, reviewer)


if __name__ == '__main__':
    unittest.main()
