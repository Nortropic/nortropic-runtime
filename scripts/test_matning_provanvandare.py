"""The fixed credential-free measurement script and its one sudoers rule (D042), on synthetic homes and a tiny repository.

The real test user does not exist here, so its identity and, where a real keychain or ssh agent would answer for the
owner running these tests, the probe's command and socket attempts are doubles; everything else runs for real: request
validation, the clone from a bundle, the suite, the result files and the boundary cases of the probe on real files.
"""
import hashlib
import errno
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

from scripts import matning_provanvandare as fast
from scripts import measurement_queue as queue

ME = pwd.getpwuid(os.getuid()).pw_name
SCRIPT = Path(fast.__file__)
SUDOERS = SCRIPT.parents[1] / 'config/nortropic-matning.sudoers'


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class Place(unittest.TestCase):
    """A temporary owner home, inbox and test-user home; the owner and the test user are both the account running this."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        os.umask(0o022)
        (root / 'Shared').mkdir(); (root / 'provhem').mkdir(); (root / 'hem').mkdir()
        self.plats = fast.Plats(agarhem=root / 'hem', runtime=root / 'hem/runtime', inkorg=root / 'Shared/nortropic-matning/in',
                                provhem=root / 'provhem', prov=ME, agare=ME, keychain=root / 'hem/Library/Keychains/login.keychain-db',
                                skript=SCRIPT)
        self.root = root
        for target, value in ((fast, 'identitet'),):
            patcher = patch.object(target, value, lambda plats: {'user': ME, 'uid': os.getuid(), 'test': True})
            patcher.start(); self.addCleanup(patcher.stop)

    def repository(self, test_body='self.assertTrue(True)'):
        repo = self.root / 'repo'; (repo / 'tools').mkdir(parents=True)
        (repo / 'tools/test_one.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        %s\n' % test_body)
        (repo / 'tools/test_two.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_b(self):\n        pass\n')
        git(self.root, 'init', '-q', '-b', 'main', str(repo))
        git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A')
        git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'one')
        return repo


class RequestTests(Place):
    def queued(self):
        return queue.begar('kontoret', self.repository(), 'refs/heads/main', 2, plats=self.plats)

    def test_default_service_home_is_d042_fixed_work_home_not_login_home(self):
        import pwd
        me=pwd.getpwuid(os.getuid()).pw_name
        p=fast.Plats(agare=me,agarhem=Path('/synthetic-owner'))
        self.assertEqual(p.provhem,Path('/Users')/fast.PROV)


    def test_a_queued_request_is_accepted_with_its_bundle(self):
        ident = self.queued()
        value, bundle = fast.las_begaran(self.plats, ident)
        self.assertEqual((value['repo'], value['expected_test_count'], bundle.name), ('kontoret', 2, 'kandidat.bundle'))

    def test_an_id_outside_the_pattern_never_touches_a_file(self):
        for ident in ('../x', 'A', '', 'x' * 81, 'a/b'):
            with self.assertRaises(fast.Vagrar):
                fast.las_begaran(self.plats, ident)

    def test_a_directory_others_can_write_is_refused(self):
        ident = self.queued()
        (self.plats.inkorg / ident).chmod(0o777)
        with self.assertRaisesRegex(fast.Vagrar, 'only the owner can write'):
            fast.las_begaran(self.plats, ident)

    def test_a_request_or_bundle_that_is_a_link_is_refused(self):
        ident = self.queued(); request = self.plats.inkorg / ident / 'begaran.json'
        moved = self.root / 'elsewhere.json'; request.rename(moved); request.symlink_to(moved)
        with self.assertRaisesRegex(fast.Vagrar, 'bounded regular file'):
            fast.las_begaran(self.plats, ident)

    def test_a_request_of_another_owner_is_refused(self):
        ident = self.queued()
        with self.assertRaisesRegex(fast.Vagrar, 'only the owner can write'):
            fast.las_begaran(fast.Plats(inkorg=self.plats.inkorg, provhem=self.plats.provhem, prov=ME, agare='root'), ident)

    def test_every_field_is_checked(self):
        ident = self.queued(); path = self.plats.inkorg / ident / 'begaran.json'; good = json.loads(path.read_text())
        for change in ({'repo': 'other'}, {'candidate': 'z' * 40}, {'tree': 'short'}, {'ref': 'refs/tags/x'},
                       {'ref': 'refs/heads/../x'}, {'expected_test_count': 0}, {'expected_test_count': True},
                       {'schema': 'other/1'}, {'id': 'other'}, {'extra': 1}):
            path.write_text(json.dumps({**good, **change}))
            with self.assertRaisesRegex(fast.Vagrar, 'recorded shape', msg=change):
                fast.las_begaran(self.plats, ident)


class IdentityTests(unittest.TestCase):
    def test_only_the_named_test_user_and_never_root_or_admin(self):
        with self.assertRaisesRegex(fast.Vagrar, 'does not exist'):
            fast.identitet(fast.Plats(prov='_nortropicprov_saknas'))
        with patch.object(fast.os, 'getgroups', lambda: [20]), patch.object(fast.os, 'getgid', lambda: 20):
            self.assertEqual(fast.identitet(fast.Plats(prov=ME))['user'], ME)
        with patch.object(fast.os, 'getgroups', lambda: [20, 80]):
            with self.assertRaisesRegex(fast.Vagrar, 'admin'):
                fast.identitet(fast.Plats(prov=ME))
        with self.assertRaisesRegex(fast.Vagrar, 'runs only as root'):
            fast.identitet(fast.Plats(prov='root'))


class ProbeTests(Place):
    def setUp(self):
        super().setUp()
        for name, value in (('forsok_kommando', lambda argv, env: 'nekad (double)'), ('agentuttag', lambda: [])):
            patcher = patch.object(fast, name, value); patcher.start(); self.addCleanup(patcher.stop)

    def keys(self, mode):
        home = self.plats.agarhem
        for path in ('runtime/.runtime/ap11/check-issuer/app.pem', '.codex/auth.json', '.config/gh/hosts.yml',
                     '.ssh/id_ed25519', 'Library/Keychains/login.keychain-db', '.nortropic-hemligheter/kundstart/k.secret',
                     '.claude/.credentials.json'):
            file = home / path; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('secret-value\n')
        for directory in ('runtime/.runtime/ap11/check-issuer', '.config', '.ssh', 'Library', '.nortropic-hemligheter', '.claude'):
            (home / directory).chmod(mode)
        (home / '.codex/auth.json').chmod(0o600 if mode == 0o700 else 0o644)

    def test_readable_keys_are_named_and_the_run_is_not_credential_free(self):
        self.keys(0o755)
        value = fast.gransprob(self.plats, svep_sekunder=5)
        self.assertFalse(value['kredentialfri'])
        groups = {row['grupp'] for row in value['nycklar_lasbara']}
        self.assertTrue({'App-nyckeln', 'Codex-inloggningen', 'GitHub', 'SSH', 'Nyckelringen', '~/.nortropic-hemligheter',
                         'Claude-inloggningen'} <= groups, groups)
        self.assertNotIn('secret-value', json.dumps(value))            # a path is reported, never what it holds
        self.assertTrue(any(p.endswith('auth.json') for p in value['svep']['lasbara_med_nyckelnamn']))

    def test_the_probe_reports_the_readable_file_outside_the_list_without_failing_on_it(self):
        self.keys(0o755)
        (self.plats.agarhem / '.claude.json').write_text('{}')
        value = fast.gransprob(self.plats, svep_sekunder=5)
        self.assertEqual(value['utanfor_listan'][0]['resultat'], 'LÄSBAR')

    @unittest.skipIf(os.getuid() == 0, 'root reads everything')
    def test_unreadable_keys_make_it_credential_free(self):
        self.keys(0o700)
        try:
            for directory in ('runtime/.runtime/ap11/check-issuer', '.config', '.ssh', 'Library', '.nortropic-hemligheter', '.claude'):
                (self.plats.agarhem / directory).chmod(0o000)
            (self.plats.agarhem / '.codex/auth.json').chmod(0o000)
            value = fast.gransprob(self.plats, svep_sekunder=5)
            self.assertTrue(value['kredentialfri'], value['nycklar_lasbara'])
            self.assertTrue(all(row['resultat'].startswith(('nekad', 'finns inte')) for row in value['fall']))
        finally:
            for directory in ('runtime/.runtime/ap11/check-issuer', '.config', '.ssh', 'Library', '.nortropic-hemligheter', '.claude'):
                (self.plats.agarhem / directory).chmod(0o700)

    def test_a_command_that_prints_is_readable_and_its_output_is_never_kept(self):
        self.assertEqual(REAL_COMMAND(['/bin/echo', 'secret'], {'PATH': '/bin'}), 'LÄSBAR')
        self.assertTrue(REAL_COMMAND(['/usr/bin/false'], {'PATH': '/bin'}).startswith('okant (kommandokod 1'))
        self.assertTrue(REAL_COMMAND(['/nonexistent/x'], {}).startswith('okant'))


REAL_COMMAND = fast.forsok_kommando


class ProbeProducerTests(Place):
    def test_missing_or_denied_command_is_unknown_for_the_whole_probe(self):
        for error in (FileNotFoundError(errno.ENOENT,'synthetic tool missing'),
                      PermissionError(errno.EACCES,'synthetic tool denied'),
                      PermissionError(errno.EPERM,'synthetic tool forbidden')):
            with self.subTest(error=error),patch.object(fast.subprocess,'run',side_effect=error),patch.object(fast,'agentuttag',return_value=[]):
                self.assertTrue(fast.forsok_kommando(['/usr/bin/security','show-keychain-info'],{}).startswith('okant'))
                report=fast.gransprob(self.plats,svep_sekunder=5)
                self.assertFalse(report['kredentialfri']);self.assertTrue(report['undersokningsfel'])

    def test_io_errors_are_unknown_but_actual_denial_and_absence_are_distinct(self):
        for error,prefix in ((OSError(errno.EIO,'synthetic'),'okant'),
                             (PermissionError(errno.EACCES,'synthetic'),'nekad'),
                             (FileNotFoundError(errno.ENOENT,'synthetic'),'finns inte')):
            with self.subTest(kind=type(error).__name__),patch.object(fast.os,'open',side_effect=error):
                self.assertTrue(fast.forsok_las(self.root/'synthetic').startswith(prefix))
            with self.subTest(listing=type(error).__name__),patch.object(fast.os,'listdir',side_effect=error):
                self.assertTrue(fast.forsok_lista(self.root).startswith(prefix))
                self.assertTrue(fast.agentuttag()[0][1].startswith(prefix))

    def test_timeout_and_unknown_command_failure_never_count_as_denial(self):
        command=['/opt/homebrew/bin/gh','auth','token']
        for error in (subprocess.TimeoutExpired(command,20),OSError(errno.EIO,'synthetic')):
            with self.subTest(error=type(error).__name__),patch.object(fast.subprocess,'run',side_effect=error):
                self.assertTrue(fast.forsok_kommando(command,{}).startswith('okant'))
        for code,message,expected in ((1,b'no oauth token found for github.com','finns inte'),
                                      (1,b'synthetic I/O error','okant'),(0,b'','LÄSBAR')):
            with self.subTest(code=code,message=message),patch.object(fast.subprocess,'run',return_value=Mock(returncode=code,stdout=b'',stderr=message)):
                self.assertTrue(fast.forsok_kommando(command,{}).startswith(expected))
        with patch.object(fast.subprocess,'run',return_value=Mock(returncode=44,stdout=b'',stderr=b'security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.')):
            self.assertTrue(fast.forsok_kommando(['/usr/bin/security','find-generic-password'],{}).startswith('nekad'))
            self.assertTrue(fast.forsok_kommando(command,{}).startswith('okant'))

    def test_socket_timeout_is_unknown_and_os_refusal_is_distinct(self):
        for error,prefix in ((TimeoutError('synthetic'),'okant'),
                             (OSError(errno.ECONNREFUSED,'synthetic'),'nekad'),
                             (OSError(errno.EIO,'synthetic'),'okant')):
            client=Mock();client.connect.side_effect=error
            with self.subTest(error=error),patch.object(fast.socket,'socket',return_value=client):
                self.assertTrue(fast.forsok_ansluta(self.root/'socket').startswith(prefix));client.close.assert_called_once()

    def test_sweep_listing_and_entry_stat_errors_cannot_be_clean(self):
        for error,unknown in ((OSError(errno.EIO,'synthetic'),True),
                              (PermissionError(errno.EACCES,'synthetic'),False)):
            with self.subTest(error=error),patch.object(fast.os,'scandir',side_effect=error):
                value=fast.svep(self.plats);self.assertEqual(value['avbrutet'] is not None,unknown)
        entry=Mock();entry.stat.side_effect=OSError(errno.EIO,'synthetic entry stat')
        class Scan:
            def __enter__(self):return iter([entry])
            def __exit__(self,*args):return False
        with patch.object(fast.os,'scandir',return_value=Scan()):
            self.assertIsNotNone(fast.svep(self.plats)['avbrutet'])

    def test_readable_file_and_directory_links_are_examined_and_cycles_end(self):
        outside=self.root/'outside';outside.mkdir();secret=outside/'tokens.json';secret.write_text('synthetic-only')
        home=self.plats.agarhem;(home/'.git-credentials').symlink_to(secret)
        (home/'linked-directory').symlink_to(outside);(outside/'cycle').symlink_to(home)
        value=fast.svep(self.plats,sekunder=5)
        self.assertIsNone(value['avbrutet']);self.assertEqual(value['antal'],2)
        self.assertTrue(any(p.endswith('.git-credentials') for p in value['lasbara_med_nyckelnamn']))
        self.assertTrue(any(p.endswith('linked-directory/tokens.json') for p in value['lasbara_med_nyckelnamn']))
        self.assertNotIn('synthetic-only',json.dumps(value))

    def test_special_credential_file_does_not_block_or_pass(self):
        path=self.plats.agarhem/'tokens';os.mkfifo(path)
        self.assertTrue(fast.forsok_las(path).startswith('okant'))
        self.assertIsNotNone(fast.svep(self.plats,sekunder=5)['avbrutet'])

    def test_unknown_observation_or_sweep_hit_makes_whole_probe_noncredentialfree(self):
        with patch.object(fast,'forsok_kommando',return_value='nekad (fixture)'),patch.object(fast,'agentuttag',return_value=[]):
            baseline=fast.gransprob(self.plats,svep_sekunder=5);self.assertTrue(baseline['kredentialfri'])
            with patch.object(fast,'forsok_las',return_value='okant (synthetic)'):
                report=fast.gransprob(self.plats,svep_sekunder=5)
                self.assertFalse(report['kredentialfri']);self.assertTrue(report['undersokningsfel'])
            (self.plats.agarhem/'.git-credentials').write_text('synthetic-only')
            report=fast.gransprob(self.plats,svep_sekunder=5)
            self.assertFalse(report['kredentialfri']);self.assertEqual(report['svep']['antal'],1)


class MeasureTests(Place):
    def setUp(self):
        super().setUp()
        patcher = patch.object(fast, 'gransprob', lambda plats, svep_sekunder=90: {
            'schema': fast.PROB, 'identitet': fast.identitet(plats), 'skript_sha256': fast.sha_fil(plats.skript),
            'nycklar_lasbara': [], 'kredentialfri': True})
        patcher.start(); self.addCleanup(patcher.stop)

    def test_the_whole_suite_of_exactly_the_candidate_in_the_issuers_form(self):
        repo = self.repository()
        ident = queue.begar('kontoret', repo, 'refs/heads/main', 2, plats=self.plats)
        klar = fast.mat(self.plats, ident)
        suite = json.loads((self.plats.ut / ident / 'suite.json').read_text())
        self.assertEqual(suite['command'], ['python', '-B', '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py', '-v'])
        self.assertEqual((suite['returncode'], suite['test_count'], suite['last_line'], suite['credential_free_execution']),
                         (0, 2, 'OK', True))
        self.assertEqual((suite['candidate'], suite['tree']), (git(repo, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD^{tree}')))
        self.assertEqual(suite['schema'], 'nortropic-measured-suite/1')
        self.assertEqual(hashlib.sha256((self.plats.ut / ident / 'suite.log').read_bytes()).hexdigest(), suite['log_sha256'])
        self.assertTrue(suite['scratch_preserved_empty'])
        self.assertEqual(klar['returncode'], 0)
        self.assertFalse((self.plats.arbete / ident).exists())             # the work area is removed
        self.assertEqual(suite['environment']['HOME'].split('/')[-1], 'hem')
        with self.assertRaises(FileExistsError):                              # an id is measured once
            fast.mat(self.plats, ident)

    def test_a_failing_suite_is_recorded_as_it_ran(self):
        repo = self.repository('self.assertTrue(False)')
        klar = fast.mat(self.plats, queue.begar('kontoret', repo, 'refs/heads/main', None, plats=self.plats))
        self.assertEqual(klar['returncode'], 1); self.assertTrue(klar['last_line'].startswith('FAILED'))

    def test_a_bundle_that_does_not_carry_the_request_is_refused(self):
        repo = self.repository(); ident = queue.begar('kontoret', repo, 'refs/heads/main', 2, plats=self.plats)
        path = self.plats.inkorg / ident / 'begaran.json'; value = json.loads(path.read_text())
        path.write_text(json.dumps({**value, 'tree': 'f' * 40}))
        klar = fast.mat(self.plats, ident)
        self.assertIn('does not carry exactly', klar['refused']); self.assertFalse((self.plats.ut / ident / 'suite.json').exists())

    def test_a_probe_that_finds_a_key_stops_the_measurement_before_any_code_runs(self):
        repo = self.repository(); ident = queue.begar('kontoret', repo, 'refs/heads/main', 2, plats=self.plats)
        with patch.object(fast, 'gransprob', lambda plats, s=90: {'skript_sha256': 'x', 'kredentialfri': False,
                                                                  'nycklar_lasbara': [{'grupp': 'SSH', 'vad': 'x'}]}):
            klar = fast.mat(self.plats, ident)
        self.assertFalse(klar['credential_free_execution']); self.assertIn('can read a key', klar['refused'])
        self.assertFalse((self.plats.ut / ident / 'suite.log').exists())

    def test_each_repository_gets_its_own_environment_and_an_empty_codex_configuration(self):
        profile = fast.PROFILER['runtime']
        self.assertEqual((profile['katalog'], profile['vard'], profile['lankar']), ('scripts', True, ('bin', 'temporal-venv', 'web-tools')))
        for name in ('runtime', 'kontoret', 'digitala'):
            (self.root / name).mkdir()
        runtime = fast.miljo(self.plats, profile, self.root / 'runtime', self.root / 'runtime/repo')
        self.assertEqual(runtime['NR_HOST_ROOT'], str(self.root / 'runtime/repo'))
        self.assertEqual((self.root / 'runtime/hem/.codex/config.toml').read_text(), '')
        self.assertNotIn('NR_HOST_ROOT', fast.miljo(self.plats, fast.PROFILER['kontoret'], self.root / 'kontoret', self.root / 'k'))
        with self.assertRaisesRegex(fast.Vagrar, 'no view of the active Runtime release'):
            fast.miljo(self.plats, fast.PROFILER['digitala'], self.root / 'digitala', self.root / 'd')
        (self.root / 'begaran/runtime-vy').mkdir(parents=True); (self.root / 'digitala2').mkdir()
        digitala = fast.miljo(self.plats, fast.PROFILER['digitala'], self.root / 'digitala2', self.root / 'd', self.root / 'begaran')
        self.assertEqual((digitala['NR_HOST_ROOT'], digitala['NR_KONTOR_ROOT'].split('/')[-1]),
                         (str(self.root / 'begaran/runtime-vy'), 'nortropic-projektkontor'))
        for env in (runtime, digitala):
            self.assertFalse(set(env) & {'SSH_AUTH_SOCK', 'GH_TOKEN', 'GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'})


class ParseTests(unittest.TestCase):
    def test_exactly_one_count_and_the_last_line(self):
        self.assertEqual(fast.tolka('x\nRan 3 tests in 0.1s\n\nOK\n'), (3, 'OK'))
        self.assertEqual(fast.tolka('Ran 3 tests in 1s\nRan 4 tests in 1s\nOK'), (None, 'OK'))
        self.assertEqual(fast.tolka(''), (None, ''))


class SudoersTests(unittest.TestCase):
    """The one rule: the owner's account may run exactly this file, by its digest, as the test user and nobody else."""

    def test_the_rule_pins_this_script_as_the_test_user_and_nothing_else(self):
        text = SUDOERS.read_text()
        rules = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(rules, ['%s ALL = (%s) NOPASSWD: sha256:%s %s' % (fast.AGARE, fast.PROV, digest, fast.INSTALLERAD)])
        self.assertNotIn('ALL = (ALL', text); self.assertNotIn('root', ''.join(rules))

    def test_the_script_runs_under_the_root_owned_command_line_tools_python_and_keeps_to_3_9(self):
        first = SCRIPT.read_text().splitlines()[0]
        self.assertEqual(first, '#!/Library/Developer/CommandLineTools/usr/bin/python3 -IB')
        source = SCRIPT.read_text()
        self.assertNotRegex(source, r'\bmatch \w+:|:=|removeprefix|removesuffix|\| None')
        python39 = Path('/Library/Developer/CommandLineTools/usr/bin/python3')
        if python39.exists():
            done = subprocess.run([str(python39), '-IB', '-c', 'import ast,sys; ast.parse(open(sys.argv[1]).read(), feature_version=(3, 9))',
                                   str(SCRIPT)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_usage_is_refused_without_the_test_user(self):
        done = subprocess.run([sys.executable, '-B', str(SCRIPT), 'annat'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2); self.assertIn('VÄGRAR', done.stderr)
        try:
            prov = pwd.getpwnam(fast.PROV).pw_uid
        except KeyError:
            prov = None
        if os.getuid() == prov:
            # The suite is measured AS the test user (D042): the real probe would pass and write into its out directory.
            # Who else is refused is proven in-process (IdentityTests); the command line only for any other runner.
            return
        done = subprocess.run([sys.executable, '-B', str(SCRIPT), 'gransprob'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2); self.assertIn('VÄGRAR', done.stderr)


if __name__ == '__main__':
    unittest.main()
