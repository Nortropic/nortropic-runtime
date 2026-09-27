"""The web profiles (D034, D035) without a browser or a model: grammar, guard, secret, underlag, schema, commands,
receipts, the start rule and the ending of child processes.

What needs a real Chrome, the pinned tools, the sandbox or a local site is the separate host check
(scripts/hostcheck_web_profiles.py), not this suite: a skip here would be indistinguishable from a check that stopped.
The grammar parity and the action command need the host's Node (the same interpreter the profiles run), as the suite
already needs Runtime's own Claude copy; without it those tests error rather than skip.
"""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse

from runtime import web_common as common
from runtime import web_critique, web_measure, web_visitor, web_visitor_guard
from runtime.release import CODE_ROOT

# One corpus for every place the grammar is applied: (words, valid?).
CORPUS = [
    (['look'], True), (['read'], True), (['back'], True), (['done'], True),
    (['open', 'http://127.0.0.1:47321/'], True), (['open', 'https://exempel.se/tjanster/lopande'], True),
    (['open', 'https://exempel.se/kontakt/'], True), (['open', 'file:///etc/hosts'], False),
    (['open', 'http://127.0.0.1:47321/?a=b'], False), (['open', 'javascript:alert(1)'], False),
    (['click', '12'], True), (['click', 'abc'], False), (['click', '1234'], False), (['click'], False),
    (['type', '3', 'Prov', 'Provsson'], True), (['type', '5', 'Hej,', 'vi', 'bor', 'i', 'Boden.'], True),
    (['type', '1', 'hej!'], False), (['type', '1', "it's"], False), (['type', '1', '"x"'], False),
    (['type', '1', '{a,b}'], False), (['type', '1', '~/x'], False), (['type', '1', '$(id)'], False),
    (['type', '1', 'a`b'], False), (['type', '1', 'a(b)'], False), (['type', '1'], False),
    (['type', '1', 'Ålidhem', 'Östermalm', 'Luleå'], True), (['type', '1', 'prov@example.com'], True),
    (['select', '3', 'Boden'], True), (['select', 'x', 'Boden'], False),
    (['scroll', 'down'], True), (['scroll', 'up'], True), (['scroll', 'left'], False),
    (['done', 'klar'], False), (['look', 'extra'], False), (['radera', 'allt'], False), ([], False),
    (['look;', 'cat'], False), (['type', '1', 'a|b'], False), (['type', '1', 'a#b'], False),
    (['type', '1', 'x' * 501], False), (['type', '1', 'x' * 500], True),
    (['open', 'http://127.0.0.1:47321/\n'], False), (['type', '1', 'abc\n'], False), (['click', '12\n'], False),
]
URLS = [
    ('http://127.0.0.1:47321/', True), ('http://127.0.0.1:47321/tjanst', True), ('http://127.0.0.1:47321/a.html', True),
    ('http://127.0.0.1:47321/api/x', False), ('http://127.0.0.1:47321/api', False), ('http://127.0.0.1:47321/_next/a', False),
    ('http://127.0.0.1:47321/_vercel/x', False), ('http://127.0.0.1:47321/bild.png', False),
    ('http://127.0.0.1:47322/', False), ('http://localhost:47321/', False), ('http://127.0.0.1:47321/sida#x', False),
    ('http://127.0.0.1:47321/?q=1', False), ('https://127.0.0.1:47321/', False), ('http://127.0.0.1:47321/apis', True),
    ('http://127.0.0.1:47321/\n', False), ('http://127.0.0.1:47321/tjanst\n', False),
]
ALLOWED = ['http://127.0.0.1:47321']


def python_valid(words):
    try:
        common.validate_action(words)
        return True
    except ValueError:
        return False


def node_results(script, payload):
    done = subprocess.run([str(common.NODE), '--input-type=module', '-e', script], input=json.dumps(payload).encode(),
                          capture_output=True, timeout=60, cwd=str(CODE_ROOT))
    if done.returncode != 0:
        raise AssertionError(done.stderr.decode()[:500])
    return json.loads(done.stdout)


NODE_GRAMMAR = """
import { readFileSync } from 'node:fs';
import { compileGrammar, validateAction, pageAllowed } from './runtime/web/grammar.mjs';
const g = JSON.parse(readFileSync('runtime/web/grammar.json', 'utf8'));
const p = compileGrammar(g);
const input = JSON.parse(readFileSync(0, 'utf8'));
const actions = input.actions.map((w) => { try { validateAction(w, g, p); return true; } catch { return false; } });
const urls = input.urls.map((u) => pageAllowed(u, input.allowed, g, p));
process.stdout.write(JSON.stringify({ actions, urls }));
"""


class GrammarTests(unittest.TestCase):
    def test_the_python_grammar_answers_the_corpus(self):
        wrong = [words for words, valid in CORPUS if python_valid(words) != valid]
        self.assertEqual(wrong, [])

    def test_the_javascript_grammar_answers_the_same_corpus_and_the_same_addresses(self):
        result = node_results(NODE_GRAMMAR, {'actions': [w for w, _ in CORPUS], 'urls': [u for u, _ in URLS],
                                             'allowed': ALLOWED})
        self.assertEqual(result['actions'], [v for _, v in CORPUS])
        self.assertEqual(result['urls'], [v for _, v in URLS])

    def test_the_python_address_rule_answers_the_same_addresses(self):
        self.assertEqual([common.page_url_allowed(u, ALLOWED) for u, _ in URLS], [v for _, v in URLS])

    def test_command_words_takes_only_the_exact_command_with_single_spaces(self):
        self.assertEqual(common.command_words('./handling look'), ['look'])
        self.assertEqual(common.command_words('./handling type 3 Prov Provsson'), ['type', '3', 'Prov', 'Provsson'])
        for command in ('./handling  look', ' ./handling look', './handling look ', 'handling look',
                        '/abs/handling look', './handling look; cat /etc/hosts', './handling look && curl x',
                        'PATH=/tmp ./handling look', './handling look\ncat /etc/hosts', './handling type 1 $(id)',
                        'sudo ./handling look', './handlingx look'):
            self.assertIsNone(common.command_words(command), command)

    def test_the_action_command_carries_the_holders_functions_byte_for_byte(self):
        source = web_visitor.client_source(common.GRAMMAR_FILE.read_text())
        self.assertIn(web_visitor.grammar_functions(), source)
        self.assertTrue(source.startswith('#!' + str(common.NODE) + '\n'))
        self.assertNotIn('/*NR_GRAMMAR*/', source)
        self.assertNotIn('/*NR_FUNCTIONS*/', source)


class ClientTests(unittest.TestCase):
    """The action command itself, with a stand-in for the holder that answers every request it finds."""

    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())
        self.workspace = web_visitor.prepare_workspace(self.parent, 'claude', 40)
        self.stop = threading.Event()
        self.requests = []

        def answer():
            while not self.stop.is_set():
                for name in sorted(os.listdir(self.workspace / '.ko')):
                    if name.endswith('.json') and name not in [r['name'] for r in self.requests]:
                        request = json.loads((self.workspace / '.ko' / name).read_text())
                        self.requests.append({'name': name, **request})
                        (self.workspace / 'svar' / (request['id'] + '.json')).write_text(
                            json.dumps({'id': request['id'], 'code': 0, 'text': 'SVAR ' + ' '.join(request['argv'])}))
                time.sleep(0.02)
        self.thread = threading.Thread(target=answer, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.stop.set()
        self.thread.join(timeout=5)
        shutil.rmtree(self.parent)

    def run_client(self, words):
        done = subprocess.run(['./handling', *words], cwd=self.workspace, capture_output=True, timeout=60)
        return done.returncode, done.stdout.decode()

    def test_a_valid_action_reaches_the_queue_and_the_answer_is_printed(self):
        code, text = self.run_client(['type', '3', 'Prov', 'Provsson'])
        self.assertEqual((code, text.strip()), (0, 'SVAR type 3 Prov Provsson'))
        self.assertEqual([r['argv'] for r in self.requests], [['type', '3', 'Prov', 'Provsson']])

    def test_an_invalid_action_is_refused_before_anything_is_queued(self):
        for words in (['done', 'klar'], ['type', '1', 'hej!'], ['radera'], ['open', 'file:///etc/hosts']):
            code, text = self.run_client(words)
            self.assertEqual(code, 2, words)
            self.assertTrue(text.startswith('FEL: '), text)
        self.assertEqual(self.requests, [])


class WorkspaceAndCommandTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.parent)

    def test_the_visitor_workspace_holds_exactly_the_contracted_entries(self):
        for executor, line in (('claude', 'Read'), ('codex', 'view_image')):
            workspace = web_visitor.prepare_workspace(self.parent, executor, 17)
            self.assertEqual(sorted(p.name for p in workspace.iterdir()),
                             ['.ko', '.scratch', 'AGENTS.md', 'handling', 'spar', 'svar'])
            agents = (workspace / 'AGENTS.md').read_text()
            self.assertIn(line, agents)
            self.assertIn('Högst 17 handlingar', agents)
            self.assertTrue(os.stat(workspace / 'handling').st_mode & stat.S_IXUSR)
            self.assertEqual(workspace, workspace.resolve())

    def test_the_claude_visitor_runs_read_and_bash_behind_the_guard_and_no_bash_rule(self):
        workspace = web_visitor.prepare_workspace(self.parent, 'claude', 40)
        argv = web_visitor.claude_command(workspace, 'claude-opus-5')
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Bash')
        self.assertEqual(argv[argv.index('--setting-sources') + 1], 'local')
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'dontAsk')
        self.assertNotIn('--restricted', argv)
        rules = argv[argv.index('--allowedTools') + 1:argv.index('--permission-mode')]
        # '//' is Claude Code's syntax for an absolute path; both spellings of a /private/var workspace are listed.
        self.assertEqual(rules, ['Read(/' + form + '/**)' for form in web_visitor.workspace_spellings(workspace)])
        self.assertTrue(all(r.startswith('Read(//') for r in rules))
        if str(workspace).startswith('/private/var/'):
            self.assertEqual(len(rules), 2)
        settings = json.loads(argv[argv.index('--settings') + 1])
        hook = settings['hooks']['PreToolUse'][0]
        self.assertEqual(hook['matcher'], '.*')
        self.assertIn('web_visitor_guard.py', hook['hooks'][0]['command'])
        self.assertEqual(settings['permissions']['allow'], rules)
        self.assertEqual(argv[argv.index('--append-system-prompt-file') + 1], str(workspace / 'AGENTS.md'))
        for flag in ('--no-chrome', '--disable-slash-commands', '--no-session-persistence', '--strict-mcp-config'):
            self.assertIn(flag, argv)

    def test_the_codex_visitor_writes_only_queue_and_scratch_without_network(self):
        workspace = web_visitor.prepare_workspace(self.parent, 'codex', 40)
        table = web_visitor.codex_table(workspace)
        self.assertEqual({k for k, v in table.items() if v == 'write'}, {str(workspace / '.ko'), str(workspace / '.scratch')})
        argv = web_visitor.codex_command(workspace, 'gpt-6-astra')
        self.assertIn('permissions.nr.network.enabled=false', argv)
        self.assertIn('web_search="disabled"', argv)
        tail = argv[argv.index('exec'):]
        self.assertEqual(tail, ['exec', '--json', '--ephemeral', '--skip-git-repo-check', '-C', str(workspace), '-'])
        for feature in ('browser_use', 'computer_use', 'in_app_browser', 'plugins', 'multi_agent'):
            self.assertEqual(argv[argv.index(feature) - 1], '--disable')
        sandbox = web_visitor.codex_sandbox_command(workspace, ['./handling', 'look'])
        self.assertEqual(sandbox[sandbox.index('sandbox') + 1:sandbox.index('-P')],
                         web_visitor.codex_permission_arguments(workspace))

    def test_the_critique_reader_is_read_only_for_both_executors(self):
        workspace = self.parent / 'ws'
        workspace.mkdir()
        (workspace / 'AGENTS.md').write_text('x')
        claude = web_critique.claude_command(workspace, 'claude-opus-5', '{"type":"object"}')
        self.assertEqual(claude[claude.index('--tools') + 1], 'Read')
        self.assertEqual(claude[-2:], ['--json-schema', '{"type":"object"}'])
        self.assertIn('--restricted', claude)
        codex = web_critique.codex_command(workspace, 'gpt-6-astra', self.parent / 's.json', self.parent / 'm.txt',
                                           ['BILDER/a.png', 'b.png'])
        encoded = next(a for a in codex if a.startswith('permissions.nr.filesystem='))
        self.assertIn(json.dumps(str(workspace)) + '="read"', encoded)
        self.assertEqual(encoded.count('"write"'), 1)
        self.assertIn(json.dumps(str(workspace / '.scratch')) + '="write"', encoded)
        self.assertIn('permissions.nr.network.enabled=false', codex)
        dash = codex.index('-')
        self.assertEqual(codex[dash + 1:], ['--image=' + str(workspace / 'BILDER/a.png'), '--image=' + str(workspace / 'b.png')])
        self.assertEqual(codex[codex.index('--output-schema') + 1], str(self.parent / 's.json'))


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()
        self.workspace = self.parent / 'arbetsyta'
        (self.workspace / 'spar').mkdir(parents=True)
        (self.workspace / 'spar' / '001-look.png').write_bytes(b'x')
        (self.parent / 'hemlig.txt').write_text('x')
        os.symlink(self.parent / 'hemlig.txt', self.workspace / 'lank.txt')
        self.grammar = common.load_grammar()

    def tearDown(self):
        shutil.rmtree(self.parent)

    def decide(self, tool, value):
        key = 'command' if tool == 'Bash' else 'file_path'
        return web_visitor_guard.decide({'tool_name': tool, 'tool_input': {key: value}}, str(self.workspace), self.grammar)[0]

    def test_the_guard_allows_exactly_the_grammar_and_reads_in_the_workspace(self):
        for words, valid in CORPUS:
            if words:
                self.assertEqual(self.decide('Bash', './handling ' + ' '.join(words)), 'allow' if valid else 'deny', words)
        self.assertEqual(self.decide('Read', str(self.workspace / 'spar' / '001-look.png')), 'allow')
        for denied in ('/etc/hosts', str(self.parent / 'hemlig.txt'), str(self.workspace / 'lank.txt'),
                       str(self.workspace / '..' / 'hemlig.txt'), ''):
            self.assertEqual(self.decide('Read', denied), 'deny', denied)
        for tool in ('Write', 'Edit', 'WebFetch', 'Glob', 'Grep', 'Task', None):
            self.assertEqual(web_visitor_guard.decide({'tool_name': tool, 'tool_input': {}}, str(self.workspace),
                                                      self.grammar)[0], 'deny')

    def test_the_guard_as_a_hook_answers_in_the_hook_format_and_logs_outside(self):
        log = self.parent / 'vakt.jsonl'
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'ls /'}}).encode()
        done = subprocess.run(['/bin/sh', '-c', web_visitor.guard_command()], input=payload, capture_output=True,
                              timeout=60, env={'NR_VISITOR_WORKSPACE': str(self.workspace), 'NR_VISITOR_GUARD_LOG': str(log),
                                               'PATH': '/usr/bin:/bin'})
        answer = json.loads(done.stdout)['hookSpecificOutput']
        self.assertEqual((answer['hookEventName'], answer['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertEqual(json.loads(log.read_text())['decision'], 'deny')
        garbage = subprocess.run(['/bin/sh', '-c', web_visitor.guard_command()], input=b'not json', capture_output=True,
                                 timeout=60, env={'PATH': '/usr/bin:/bin'})
        self.assertEqual(json.loads(garbage.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')


class SecretTests(unittest.TestCase):
    def setUp(self):
        # Not under /tmp or /var/folders: those are refused by design.
        self.directory = CODE_ROOT / '.runtime' / ('test-hemlighet-%d' % os.getpid())
        self.directory.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def secret_file(self, content=b'falsk-hemlighet-123456\n', mode=0o600, name='undantag'):
        path = self.directory / name
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def test_a_private_single_line_file_is_read(self):
        self.assertEqual(common.read_secret(str(self.secret_file())), 'falsk-hemlighet-123456')

    def test_mode_other_than_0600_and_short_values_are_refused(self):
        with self.assertRaises(ValueError):
            common.read_secret(str(self.secret_file(name='h', mode=0o700)))
        with self.assertRaises(ValueError):
            common.read_secret(str(self.secret_file(name='k', content=b'kort-15-tecken!\n')))
        self.assertEqual(common.read_secret(str(self.secret_file(name='m', content=b'exakt-16-tecken!\n'))), 'exakt-16-tecken!')

    def test_everything_else_is_refused(self):
        for kwargs in ({'mode': 0o644}, {'mode': 0o640}, {'content': b''}, {'content': b'a\nb\n'},
                       {'content': b'x' * 5000}, {'content': 'åäö'.encode()}):
            with self.assertRaises(ValueError, msg=kwargs):
                common.read_secret(str(self.secret_file(name='f', **kwargs)))
        link = self.directory / 'lank'
        os.symlink(self.secret_file(), link)
        for path in (str(link), 'relativ/sokvag', '/tmp/x', '/private/etc/hosts'):
            with self.assertRaises((ValueError, OSError), msg=path):
                common.read_secret(path)
        with self.assertRaises(ValueError):
            common.read_secret(str(self.secret_file(name='g')), forbidden_root=self.directory)

    def test_every_written_form_is_found_and_removed(self):
        secret = 'falsk-hemlighet-abcdef'
        for index, data in enumerate((secret.encode(), urllib.parse.quote(secret).encode(),
                                      base64.b64encode(secret.encode()), b'no secret here')):
            (self.directory / ('f%d' % index)).write_bytes(b'prefix ' + data + b' suffix')
        hits = common.secret_hits(self.directory, secret)
        self.assertEqual(sorted(h[0] for h in hits), ['f0', 'f1', 'f2'])
        removed = common.remove_contaminated(self.directory, hits)
        self.assertEqual(len(removed), 3)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ['f3'])

    def test_child_environments_carry_no_credentials(self):
        os.environ['NR_TEST_SECRET_X'], os.environ['GH_TOKEN_X'] = 'a', 'b'
        try:
            env = common.filtered_environment({'NR_UNDANTAG': 'c'})
        finally:
            del os.environ['NR_TEST_SECRET_X'], os.environ['GH_TOKEN_X']
        self.assertNotIn('NR_TEST_SECRET_X', env)
        self.assertNotIn('GH_TOKEN_X', env)
        self.assertEqual(env['NR_UNDANTAG'], 'c')
        self.assertTrue(set(env) <= {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR', 'NR_UNDANTAG'})


class UnderlagTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()
        (self.parent / 'a.png').write_bytes(b'\x89PNG bild')
        (self.parent / 'b.md').write_text('text')

    def tearDown(self):
        shutil.rmtree(self.parent)

    def manifest(self, files):
        path = self.parent / 'manifest.json'
        path.write_text(json.dumps({'filer': files}))
        return path

    def test_the_workspace_is_the_listed_copy_with_files_md(self):
        files = web_critique.load_manifest(self.manifest([
            {'kalla': str(self.parent / 'a.png'), 'plats': 'BILDER/a.png', 'vad': 'en bild'},
            {'kalla': str(self.parent / 'b.md'), 'plats': 'b.md', 'vad': 'en text'}]))
        workspace, rows = web_critique.build_workspace(files, 'claude', self.parent)
        self.assertEqual(sorted(str(p.relative_to(workspace)) for p in workspace.rglob('*') if p.is_file()),
                         ['AGENTS.md', 'BILDER/a.png', 'FILES.md', 'b.md'])
        listing = (workspace / 'FILES.md').read_text()
        for row in rows:
            self.assertIn('`%s` | `%s` | %d |' % (row['place'], row['sha256'], row['bytes']), listing)
            self.assertEqual(row['source_sha256'], row['copy_sha256'])
        self.assertIn('Read', (workspace / 'AGENTS.md').read_text())

    def test_bad_manifests_and_sources_are_refused(self):
        good = {'kalla': str(self.parent / 'b.md'), 'plats': 'b.md', 'vad': 'x'}
        for files in ([], [dict(good, plats='../b.md')], [dict(good, plats='/b.md')], [dict(good, plats='FILES.md')],
                      [dict(good, plats='.scratch/b.md')], [dict(good, plats='a/.dold')],
                      [good, good], [dict(good, extra=1)], [dict(good, vad='')], [good] * 201):
            with self.assertRaises(ValueError, msg=str(files)[:80]):
                web_critique.load_manifest(self.manifest(files))
        link_directory = self.parent / 'lank'
        os.symlink(self.parent, link_directory)
        for source in (str(link_directory / 'b.md'), str(self.parent / 'saknas'), str(self.parent)):
            files = [dict(good, kalla=source)]
            with self.assertRaises((ValueError, OSError), msg=source):
                web_critique.build_workspace(web_critique.load_manifest(self.manifest(files)), 'claude', self.parent)

    def test_a_copy_is_bounded_and_verified(self):
        target = self.parent / 'kopia' / 'b.md'
        source, copy, size = common.copy_regular(str(self.parent / 'b.md'), target, 100)
        self.assertEqual((source, copy, size), (common.sha256_file(self.parent / 'b.md'),) * 2 + (4,))
        with self.assertRaises(ValueError):
            common.copy_regular(str(self.parent / 'a.png'), self.parent / 'kopia' / 'a.png', 3)


class SchemaTests(unittest.TestCase):
    SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['omdome', 'brister', 'poang'],
              'properties': {'omdome': {'type': 'string', 'maxLength': 200},
                             'brister': {'type': 'array', 'maxItems': 3, 'items': {
                                 'type': 'object', 'additionalProperties': False, 'required': ['vad', 'vikt'],
                                 'properties': {'vad': {'type': 'string'}, 'vikt': {'type': 'string', 'enum': ['hög', 'låg']}}}},
                             'poang': {'type': 'integer', 'minimum': 0, 'maximum': 4}}}

    def test_the_dialect_is_accepted_and_a_valid_answer_passes(self):
        web_critique.check_schema(self.SCHEMA)
        web_critique.validate({'omdome': 'bra', 'brister': [{'vad': 'x', 'vikt': 'låg'}], 'poang': 3}, self.SCHEMA)

    def test_schemas_outside_the_dialect_are_refused(self):
        def variant(**change):
            value = json.loads(json.dumps(self.SCHEMA))
            value.update(change)
            return value
        for schema in (variant(additionalProperties=True), variant(required=['omdome']), variant(type='array'),
                       variant(pattern='x'), {'type': 'object', 'properties': {}, 'additionalProperties': False},
                       variant(properties={**self.SCHEMA['properties'], 'lista': {'type': 'array'}},
                               required=self.SCHEMA['required'] + ['lista'])):
            with self.assertRaises(ValueError, msg=str(schema)[:80]):
                web_critique.check_schema(schema)

    def test_answers_outside_the_schema_are_refused(self):
        for answer in ({'omdome': 'bra', 'brister': [], 'poang': 5}, {'omdome': 'bra', 'brister': [], 'poang': True},
                       {'omdome': 'bra', 'brister': [], 'poang': 1, 'extra': 1}, {'omdome': 'x' * 201, 'brister': [], 'poang': 1},
                       {'omdome': 'bra', 'brister': [{'vad': 'x', 'vikt': 'mellan'}], 'poang': 1},
                       {'omdome': 'bra', 'brister': [{'vad': 'x', 'vikt': 'låg'}] * 4, 'poang': 1}, []):
            with self.assertRaises(ValueError, msg=str(answer)[:80]):
                web_critique.validate(answer, self.SCHEMA)

    def test_duplicate_keys_never_pass_silently(self):
        with self.assertRaises(ValueError):
            json.loads('{"a": 1, "a": 2}', object_pairs_hook=web_critique.strict)


def claude_stream(tools=('Bash', 'Read'), model='claude-opus-5', error=False, text='rapport'):
    init = {'type': 'system', 'subtype': 'init', 'session_id': 's', 'claude_code_version': '2.1.257', 'model': model,
            'tools': list(tools), 'mcp_servers': [], 'plugins': [], 'slash_commands': [], 'apiKeySource': 'none'}
    result = {'type': 'result', 'subtype': 'error_during_execution' if error else 'success', 'is_error': error,
              'terminal_reason': 'completed', 'session_id': 's', 'result': text, 'num_turns': 3,
              'permission_denials': [{'tool_name': 'Bash'}], 'usage': {'output_tokens': 5}}
    return [init, result]


class ClassificationTests(unittest.TestCase):
    def test_a_claude_visitor_session_counts_only_with_the_measured_profile(self):
        good = web_visitor.classify_claude(claude_stream(), 'claude-opus-5')
        self.assertTrue(good['profile_as_measured'] and good['terminal'])
        self.assertEqual((good['final_text'], good['permission_denials']), ('rapport', 1))
        for stream in (claude_stream(tools=('Bash', 'Read', 'Write')), claude_stream(model='claude-other'),
                       claude_stream()[:1], claude_stream() + claude_stream()[1:]):
            verdict = web_visitor.classify_claude(stream, 'claude-opus-5')
            self.assertFalse(verdict['profile_as_measured'] and verdict['terminal'])
        refused = web_visitor.classify_claude(claude_stream(error=True, text="You've hit your limit"), 'claude-opus-5')
        self.assertFalse(refused['terminal'])
        self.assertEqual(refused['provider_words'], ["You've hit your limit"])

    def test_a_codex_session_keeps_the_providers_words(self):
        limit = 'You have hit your usage limit.'
        rows = [{'type': 'thread.started', 'thread_id': 't'}, {'type': 'turn.started'},
                {'type': 'error', 'message': limit}, {'type': 'turn.failed', 'error': {'message': limit}}]
        verdict = web_visitor.classify_codex(rows)
        self.assertFalse(verdict['terminal'])
        self.assertEqual(verdict['provider_words'], [limit])
        rows = [{'type': 'thread.started', 'thread_id': 't'},
                {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 0}},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'slut'}},
                {'type': 'turn.completed', 'usage': {}}]
        verdict = web_visitor.classify_codex(rows)
        self.assertTrue(verdict['terminal'])
        self.assertEqual((verdict['final_text'], verdict['commands']), ('slut', 1))

    def test_codex_commands_are_kept_for_the_trace_and_attachments_are_read_back(self):
        rows = [{'type': 'item.started', 'item': {'type': 'command_execution', 'command': 'ls'}},
                {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'ls', 'exit_code': 0,
                                                    'status': 'completed'}},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'x'}}]
        self.assertEqual(web_visitor.codex_commands(rows), [{'command': 'ls', 'exit_code': 0, 'status': 'completed'}])
        argv = ['codex', 'exec', '-', '--image=/ws/BILDER/a.png']
        self.assertEqual(web_critique.attached_images(argv, '/ws', ['BILDER/a.png', 'BILDER/b.png']), ['BILDER/a.png'])
        parent = Path(tempfile.mkdtemp())
        try:
            (parent / 'binar').write_bytes(b'bin')
            identity = web_critique.executor_identity('codex', [str(parent / 'binar'), 'exec'])
            self.assertEqual(identity['sha256'], common.sha256_bytes(b'bin'))
        finally:
            shutil.rmtree(parent)

    def test_a_critique_answer_is_only_the_single_terminals_structured_output(self):
        parent = Path(tempfile.mkdtemp()).resolve()
        try:
            stream = claude_stream(tools=('Read', 'StructuredOutput'), text='{"a": 1}')
            stream[1]['structured_output'] = {'a': 1}
            stream.insert(1, {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': str(parent / 'BILDER' / 'x.png')}}]}})
            answer, parsed, words, opened = web_critique.claude_answer(stream, 'claude-opus-5', parent)
            self.assertEqual((answer, opened), ({'a': 1}, {'BILDER/x.png'}))
            stream[-1]['result'] = '{"a": 2}'
            self.assertIsNone(web_critique.claude_answer(stream, 'claude-opus-5', parent)[0])
        finally:
            shutil.rmtree(parent)


class ParameterTests(unittest.TestCase):
    def test_measurement_parameters_are_checked_before_anything_runs(self):
        good = ['--mal', 'https://exempel.se/', '--etikett', 'prov']
        self.assertEqual(web_measure.parse(good).parts, list(web_measure.PARTS))
        self.assertEqual(web_measure.parse(good + ['--delar', 'axe']).parts, ['skarm', 'axe'])
        for bad in (['--mal', 'http://exempel.se/', '--etikett', 'prov'], ['--mal', 'https://a:b@exempel.se/', '--etikett', 'prov'],
                    good + ['--sektioner', '5'], good + ['--delar', 'axe,okand'], good + ['--delar', 'axe,axe'],
                    ['--fil', 'relativ.html', '--etikett', 'prov'], ['--fil', '/etc/hosts', '--etikett', 'prov'],
                    ['--mal', 'https://exempel.se/', '--etikett', 'Stor_Bokstav'], good + ['--handling-selektor', 'a{}'],
                    good + ['--handling-text', 'x' * 81], good + ['--undantag-fil', '/x', '--undantag-sort', 'okand']):
            with self.assertRaises((ValueError, SystemExit), msg=bad), contextlib.redirect_stderr(io.StringIO()):
                web_measure.parse(bad)

    def test_visitor_parameters_are_checked_before_anything_runs(self):
        parent = Path(tempfile.mkdtemp())
        try:
            task = parent / 'UPPGIFT.md'
            task.write_text('Hitta kontaktsidan.')
            base = ['--uppgift', str(task), '--vy', 'mobil', '--utforare', 'claude', '--modell', 'claude-opus-5',
                    '--etikett', 'prov']
            good = ['--start', 'http://127.0.0.1:47321/', '--tillatna', 'http://127.0.0.1:47321'] + base
            self.assertEqual(web_visitor.parse(good).allowed, ['http://127.0.0.1:47321'])
            for bad in (['--start', 'http://127.0.0.1:47322/', '--tillatna', 'http://127.0.0.1:47321'] + base,
                        ['--start', 'http://exempel.se/', '--tillatna', 'http://exempel.se'] + base,
                        ['--start', 'http://127.0.0.1:47321/api/x', '--tillatna', 'http://127.0.0.1:47321'] + base,
                        good + ['--max-handlingar', '81'], good + ['--tid', '59'], good + ['--bindning', 'Commit=abc'],
                        good + ['--bindning', 'commit=a', '--bindning', 'commit=b'], good[:-2] + ['--etikett', 'x y'],
                        ['--start', 'https://a.se/', '--tillatna', ','.join('https://%s.se' % c for c in 'abcde')] + base,
                        good[:good.index('--modell') + 1] + ['--x'] + good[good.index('--modell') + 2:]):
                with self.assertRaises((ValueError, SystemExit), msg=bad), contextlib.redirect_stderr(io.StringIO()):
                    web_visitor.parse(bad)
            task.write_text('x' * 16385)
            with self.assertRaises(ValueError):
                web_visitor.parse(good)
        finally:
            shutil.rmtree(parent)


class StartTests(unittest.TestCase):
    ALLOWED = ['http://127.0.0.1:47321', 'https://exempel.se']

    def test_a_model_may_start_only_on_a_start_page_that_opened_inside_the_allowlist(self):
        good = {'ready': True, 'start': 'http://127.0.0.1:47321/', 'start_status': 200, 'start_error': None}
        self.assertIsNone(web_visitor.start_problem(good, self.ALLOWED))
        self.assertIsNone(web_visitor.start_problem({**good, 'start': 'https://exempel.se/om', 'start_status': 304},
                                                    self.ALLOWED))
        for change in ({'start_error': 'net::ERR_PROXY_CONNECTION_FAILED'}, {'start_status': None},
                       {'start_status': 401}, {'start_status': 500}, {'start_status': True}, {'start_status': '200'},
                       {'start_status': 99}, {'start': 'chrome-error://chromewebdata/'}, {'start': 'about:blank'},
                       {'start': 'http://127.0.0.1:47322/'}, {'start': 'https://exempel.se.annan.se/'},
                       {'start': 'http://localhost:47321/'}, {'start': None}):
            self.assertIsInstance(web_visitor.start_problem({**good, **change}, self.ALLOWED), str, msg=change)

    def test_no_model_starts_when_the_start_page_did_not_open(self):
        parent = Path(tempfile.mkdtemp())
        try:
            task = parent / 'UPPGIFT.md'
            task.write_text('Hitta kontaktsidan.')
            run_directory = parent / 'korning'
            run_directory.mkdir()
            ready = {'ready': True, 'primed': None, 'start': 'chrome-error://chromewebdata/', 'start_status': None,
                     'start_error': 'net::ERR_PROXY_CONNECTION_FAILED at http://127.0.0.1:47321/'}

            def holder(run, workspace, *arguments):
                (run / 'hallare-stopp.json').write_text('{"stopped": true}\n')
                return 'hallare', ready

            never = mock.Mock(side_effect=AssertionError('a model would start'))
            with mock.patch.object(web_visitor, 'preflight', return_value={'stub': True}), \
                    mock.patch.object(common, 'tool_identity', return_value={}), \
                    mock.patch.object(common, 'new_run_directory', return_value=run_directory), \
                    mock.patch.object(web_visitor, 'start_holder', side_effect=holder), \
                    mock.patch.object(web_visitor, 'stop_holder') as stopped, \
                    mock.patch.object(web_visitor, 'claude_command', never), \
                    mock.patch.object(web_visitor, 'codex_command', never), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = web_visitor.run(['--start', 'http://127.0.0.1:47321/', '--tillatna', 'http://127.0.0.1:47321',
                                        '--uppgift', str(task), '--vy', 'mobil', '--utforare', 'claude', '--modell',
                                        'claude-opus-5', '--etikett', 'prov'])
            self.assertEqual(code, 1)
            never.assert_not_called()
            stopped.assert_called_with('hallare')   # before the receipt, and again by run() on the way out
            receipt = json.loads((run_directory / 'KVITTO.json').read_text())
            self.assertEqual(receipt['outcome'], 'start_misslyckades')
            self.assertIsNone(receipt['session'])
            self.assertIn('ERR_PROXY_CONNECTION_FAILED', receipt['start_problem'])
            self.assertEqual(receipt['holder_stopped'], {'stopped': True})
            for absent in ('start.json', 'session.jsonl', 'slutrapport.txt', 'KONTROLL.md'):
                self.assertFalse((run_directory / absent).exists(), absent)
        finally:
            shutil.rmtree(parent)


# A stand-in model CLI: it starts a grandchild in its own process group, names both, reads its prompt and waits.
FAKE_CLI = """
import subprocess, sys, time
child = subprocess.Popen(['/bin/sleep', '300'])
open(sys.argv[1], 'w').write('%d %d' % (__import__('os').getpid(), child.pid))
sys.stdin.read()
time.sleep(float(sys.argv[2]))
"""


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def gone(pids, seconds=5):
    deadline = time.monotonic() + seconds
    while any(alive(p) for p in pids) and time.monotonic() < deadline:
        time.sleep(0.1)
    return not any(alive(p) for p in pids)


class ChildProcessTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.parent)

    def session(self, pause, limit, wait=None):
        names = self.parent / 'pids'
        argv = [sys.executable, '-c', FAKE_CLI, str(names), str(pause)]
        with (self.parent / 'strom').open('wb') as stream:
            if wait is None:
                result = common.run_session(argv, self.parent, dict(os.environ), 'fråga', stream, limit)
            else:
                with mock.patch.object(subprocess.Popen, 'wait', wait):
                    result = common.run_session(argv, self.parent, dict(os.environ), 'fråga', stream, limit)
        return result, [int(p) for p in names.read_text().split()]

    def test_a_session_that_ends_by_itself_reports_its_exit(self):
        (code, end), pids = self.session(0, 60)
        self.assertEqual((code, end), (0, 'exit'))
        os.kill(pids[1], signal.SIGKILL)   # the stand-in's own grandchild, left behind on a normal exit

    def test_a_session_over_its_time_limit_is_ended_with_its_whole_group(self):
        (code, end), pids = self.session(300, 2)
        self.assertEqual(end, 'tidsgrans')
        self.assertTrue(gone(pids), pids)

    def test_an_interrupt_while_a_session_runs_ends_its_whole_group_and_goes_on(self):
        real_wait, calls = subprocess.Popen.wait, []

        def wait(process, timeout=None):
            calls.append(timeout)
            if len(calls) == 1:
                deadline = time.monotonic() + 10   # let the stand-in name its processes first
                while not (self.parent / 'pids').exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                raise KeyboardInterrupt
            return real_wait(process, timeout)
        with self.assertRaises(KeyboardInterrupt):
            self.session(300, 60, wait)
        self.assertTrue(gone([int(p) for p in (self.parent / 'pids').read_text().split()]))

    def test_the_first_stop_signal_raises_stopped_and_turns_all_three_off_until_the_command_ends(self):
        self.assertEqual(common.STOP_SIGNALS, (signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
        before = {s: signal.getsignal(s) for s in common.STOP_SIGNALS}
        for number in common.STOP_SIGNALS:
            with common.stop_signals():
                with self.assertRaises(common.Stopped):
                    signal.getsignal(number)(number, None)
                # A second signal during the cleanup is ignored rather than cutting it short.
                self.assertEqual({signal.getsignal(s) for s in common.STOP_SIGNALS}, {signal.SIG_IGN})
            self.assertEqual({s: signal.getsignal(s) for s in common.STOP_SIGNALS}, before)

    def test_only_the_processes_of_the_named_chrome_profile_are_ended(self):
        profile = self.parent / 'kör ning' / '.chrome-profil'
        other = self.parent / 'kör ning' / '.chrome-profil-2'
        started = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)', '--user-data-dir=' + str(p)],
                                    start_new_session=True) for p in (profile, other)]
        try:
            self.assertEqual(common.chrome_processes(profile), [started[0].pid])
            self.assertEqual(common.end_chrome(profile, grace=0.2), 1)
            self.assertIsNotNone(started[0].wait(timeout=10))
            self.assertIsNone(started[1].poll())
            self.assertEqual(common.end_chrome(profile, grace=0.2), 0)
        finally:
            for process in started:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_cleanup_is_shielded_from_the_stop_signals_which_come_back_afterwards(self):
        before = {s: signal.getsignal(s) for s in common.STOP_SIGNALS}
        with common.stop_signals():
            armed = {s: signal.getsignal(s) for s in common.STOP_SIGNALS}
            with common.shielded():
                self.assertEqual({signal.getsignal(s) for s in common.STOP_SIGNALS}, {signal.SIG_IGN})
            self.assertEqual({s: signal.getsignal(s) for s in common.STOP_SIGNALS}, armed)
        self.assertEqual({s: signal.getsignal(s) for s in common.STOP_SIGNALS}, before)

    def test_the_chrome_sweep_never_raises_over_the_exception_a_cleanup_runs_under(self):
        with mock.patch.object(common.subprocess, 'run', side_effect=OSError('ps saknas')):
            self.assertIsNone(common.end_chrome(self.parent / '.chrome-profil', grace=0))
        with mock.patch.object(common.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ps', 20)):
            self.assertIsNone(common.end_chrome(self.parent / '.chrome-profil', grace=0))

    def test_a_holder_interrupted_while_it_starts_ends_at_once_with_its_profile(self):
        # A stand-in holder that never becomes ready; the interrupt comes while start_holder waits for it.
        stand_in = self.parent / 'web' / 'holder.mjs'
        stand_in.parent.mkdir()
        stand_in.write_text('import sys, time\ntime.sleep(300)\n')
        run, workspace = self.parent / 'korning', self.parent / 'arbetsyta'
        run.mkdir()
        (workspace / '.ko').mkdir(parents=True)
        real_sleep, calls, started = time.sleep, [], []
        real_popen = subprocess.Popen

        def popen(*arguments, **options):
            process = real_popen(*arguments, **options)
            started.append(process)
            return process

        def sleep(seconds):
            calls.append(seconds)
            if len(calls) == 3:
                raise KeyboardInterrupt
            real_sleep(seconds)
        with mock.patch.object(common, 'NODE', Path(sys.executable)), mock.patch.object(common, 'WEB', stand_in.parent), \
                mock.patch.object(web_visitor.subprocess, 'Popen', side_effect=popen), \
                mock.patch.object(web_visitor.time, 'sleep', side_effect=sleep), \
                mock.patch.object(common, 'end_chrome', return_value=0) as ended, self.assertRaises(KeyboardInterrupt):
            web_visitor.start_holder(run, workspace, 'http://127.0.0.1:47321/', ['http://127.0.0.1:47321'], 'mobil', 10)
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].poll(), 'the stand-in holder was left running')
        ended.assert_called_once_with(run / '.chrome-profil')
        self.assertFalse((run / '.chrome-profil').exists())

    def test_the_visitor_stops_its_holder_and_chrome_whatever_happens_after_the_start(self):
        task = self.parent / 'UPPGIFT.md'
        task.write_text('Hitta kontaktsidan.')
        run_directory = self.parent / 'korning'
        run_directory.mkdir()
        (run_directory / '.chrome-profil').mkdir()
        (run_directory / '.chrome-profil' / 'Cookies').write_text('kaka')   # as if priming had run
        ready = {'ready': True, 'primed': None, 'start': 'http://127.0.0.1:47321/', 'start_status': 200,
                 'start_error': None}
        shielded = []
        with mock.patch.object(web_visitor, 'preflight', return_value={'stub': True}), \
                mock.patch.object(common, 'tool_identity', return_value={}), \
                mock.patch.object(common, 'new_run_directory', return_value=run_directory), \
                mock.patch.object(web_visitor, 'start_holder', return_value=('hallare', ready)), \
                mock.patch.object(web_visitor, 'stop_holder',
                                  side_effect=lambda h: shielded.append(signal.getsignal(signal.SIGTERM))) as stopped, \
                mock.patch.object(common, 'end_chrome', return_value=0) as ended, \
                mock.patch('runtime.claude_profile.require_subscription', side_effect=ValueError('provfel')):
            with self.assertRaises(ValueError):
                web_visitor.run(['--start', 'http://127.0.0.1:47321/', '--tillatna', 'http://127.0.0.1:47321',
                                 '--uppgift', str(task), '--vy', 'mobil', '--utforare', 'claude', '--modell',
                                 'claude-opus-5', '--etikett', 'prov'])
        stopped.assert_called_with('hallare')
        ended.assert_called_with(run_directory / '.chrome-profil')
        self.assertFalse((run_directory / 'KVITTO.json').exists())
        self.assertFalse((run_directory / '.chrome-profil').exists())
        self.assertEqual(shielded, [signal.SIG_IGN], 'the final cleanup ran unshielded')

    def test_the_measurement_cleans_up_shielded_and_removes_the_profile_even_when_node_never_started(self):
        page = self.parent / 'sida' / 'index.html'
        page.parent.mkdir()
        page.write_text('<!doctype html><title>Prov</title><h1>Prov</h1>')
        run_directory = self.parent / 'matning'
        run_directory.mkdir()
        shielded = []

        def sweep(profile, *arguments):
            shielded.append(signal.getsignal(signal.SIGTERM))
            return 0
        with mock.patch.object(common, 'tool_identity', return_value={}), \
                mock.patch.object(common, 'new_run_directory', return_value=run_directory), \
                mock.patch.object(web_measure.subprocess, 'Popen', side_effect=KeyboardInterrupt), \
                mock.patch.object(common, 'end_chrome', side_effect=sweep), self.assertRaises(KeyboardInterrupt):
            web_measure.run(['--fil', str(page), '--etikett', 'prov'])
        self.assertEqual(shielded, [signal.SIG_IGN], 'the final cleanup ran unshielded')
        self.assertFalse((run_directory / '.chrome-profil').exists())
        self.assertFalse((run_directory / 'KVITTO.json').exists())


class ReceiptTests(unittest.TestCase):
    def test_the_receipt_hashes_every_other_file_and_is_never_rewritten(self):
        parent = Path(tempfile.mkdtemp())
        try:
            (parent / 'skarm').mkdir()
            (parent / 'skarm' / 'a.png').write_bytes(b'bild')
            (parent / 'b.json').write_text('{}')
            receipt = common.write_receipt(parent, {'outcome': 'klar'})
            self.assertEqual(set(receipt['outputs']), {'skarm/a.png', 'b.json'})
            self.assertEqual(receipt['outputs']['skarm/a.png']['sha256'], common.sha256_bytes(b'bild'))
            written = (parent / 'KVITTO.json').read_bytes()
            self.assertEqual((parent / 'KVITTO.sha256').read_text().split()[0], common.sha256_bytes(written))
            with self.assertRaises(FileExistsError):
                common.write_receipt(parent, {'outcome': 'klar'})
        finally:
            shutil.rmtree(parent)

    def test_labels_are_plain(self):
        for bad in ('', 'A', 'a b', 'a/b', '-a', 'x' * 41, None):
            with self.assertRaises(ValueError):
                common.label(bad)
        self.assertEqual(common.label('prov-1'), 'prov-1')


class ToolLockTests(unittest.TestCase):
    def test_the_closure_resolves_nested_optional_and_peer_dependencies_like_node(self):
        sys.path.insert(0, str(CODE_ROOT / 'scripts'))
        import install_web_tools
        lock = {'node_modules/puppeteer-core': {'dependencies': {'ws': '1'}},
                'node_modules/ws': {'optionalDependencies': {'bufferutil': '1'}},
                'node_modules/axe-core': {},
                'node_modules/lighthouse': {'dependencies': {'ws': '2', 'yargs': '1'},
                                            'peerDependencies': {'typescript': '1', 'zod': '1'},
                                            'peerDependenciesMeta': {'typescript': {'optional': True}}},
                'node_modules/lighthouse/node_modules/ws': {}, 'node_modules/yargs': {}, 'node_modules/zod': {},
                'node_modules/chrome-launcher': {'dependencies': {'yargs': '1'}}}
        self.assertEqual(install_web_tools.closure(lock), sorted([
            'node_modules/puppeteer-core', 'node_modules/ws', 'node_modules/axe-core', 'node_modules/lighthouse',
            'node_modules/lighthouse/node_modules/ws', 'node_modules/yargs', 'node_modules/zod',
            'node_modules/chrome-launcher']))

    def test_the_lock_is_consistent(self):
        lock = json.loads(common.TOOLS_LOCK.read_text())
        sys.path.insert(0, str(CODE_ROOT / 'scripts'))
        import install_web_tools
        self.assertEqual(install_web_tools.overall(lock['packages']), lock['tree_sha256'])
        self.assertEqual(lock['roots'], ['puppeteer-core', 'axe-core', 'lighthouse', 'chrome-launcher'])
        for key in ('node_modules/puppeteer-core', 'node_modules/axe-core', 'node_modules/lighthouse'):
            self.assertIn(key, lock['packages'])


if __name__ == '__main__':
    unittest.main()
