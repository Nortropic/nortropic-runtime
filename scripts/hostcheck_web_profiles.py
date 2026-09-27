"""Host checks of the web profiles (D034): the real Chrome, the pinned tools, Runtime's sandbox and local sites.

Deliberately NOT named test_*.py, so the published suite discovers none of them: they need this host's Chrome, Node,
the pinned tool copy and the sandbox binary, and a skip inside the suite would be indistinguishable from a check that
quietly stopped. They run separately, and scripts/run_web_host_checks.py records their result as a receipt bound to
the commit, the bytes it exercised, where they were imported from, and the tool identities.

Nothing here starts a model or reaches anything but this host (127.0.0.1, or `localhost` in D035's check).
"""
import contextlib
import io
import json
import os
from pathlib import Path
import secrets as token_source
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from runtime import web_boundary, web_common as common, web_measure, web_visitor
from runtime.release import CODE_ROOT, ROOT


def latest(profile, label):
    runs = sorted((ROOT / '.runtime/profiler' / profile).glob('*-' + label))
    return runs[-1]


class ToolChecks(unittest.TestCase):
    def test_the_pinned_tools_match_the_lock_and_the_engine_hash(self):
        verified = common.verify_tools()
        self.assertEqual(verified['tree_sha256'], json.loads(common.TOOLS_LOCK.read_text())['tree_sha256'])
        self.assertEqual(common.sha256_file(common.impeccable_binary()), common.IMPECCABLE_SHA256)
        self.assertTrue(common.chrome_identity()['present'])
        self.assertTrue(common.node_identity()['present'])


class BarrierChecks(unittest.TestCase):
    def test_barriers_a_b_and_c_hold_for_the_claude_path_and_the_codex_path(self):
        outcome = web_boundary.host_check(label='vardkontroll')
        receipt = json.loads((Path(outcome['run']) / 'KVITTO.json').read_text())
        failing = {path: [name for name, ok in result['checks'].items() if not ok]
                   for path, result in receipt['results'].items()}
        self.assertEqual(failing, {'claude': [], 'codex': [], 'b': []})
        self.assertEqual(receipt['secret_hits'], [])
        self.assertTrue(outcome['passed'])


class MeasurementChecks(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.parent)

    def assert_complete_measurement(self, run):
        receipt = json.loads((run / 'KVITTO.json').read_text())
        self.assertEqual(receipt['outcome'], 'klar', receipt.get('reason'))
        for view in ('mobil-390', 'desktop-1440'):
            for name in ('forsta-vyn', 'sektion-1', 'sektion-2', 'hela'):
                self.assertTrue((run / 'skarm' / ('%s-%s.png' % (view, name))).is_file(), (view, name))
            first = common.sha256_file(run / 'skarm' / (view + '-forsta-vyn.png'))
            self.assertNotEqual(first, common.sha256_file(run / 'skarm' / (view + '-sektion-1.png')))
            measured = json.loads((run / 'matning' / (view + '.json')).read_text())
            self.assertGreaterEqual(measured['h1'][0]['lines'], 1)
            self.assertTrue(measured['action']['found'] and measured['action']['fully_in_first_view'])
            axe = json.loads((run / 'axe' / (view + '.json')).read_text())
            self.assertIn('image-alt', [v['id'] for v in axe['violations']])
            findings = json.loads((run / 'detektor' / (view + '.json')).read_text())
            # The side accent comes from the external stylesheet: found only if the snapshot inlined it.
            self.assertIn('side-tab', [f['antipattern'] for f in findings])
        for form in ('mobil', 'desktop'):
            report = json.loads((run / 'lighthouse' / (form + '.json')).read_text())
            self.assertIsNone(report.get('runtimeError'))
            self.assertIsNotNone(report['categories']['accessibility']['score'])
        self.assertTrue(receipt['chrome_profile_removed'])
        self.assertFalse((run / '.chrome-profil').exists())
        return receipt

    def test_an_address_is_measured_in_both_views_with_every_part(self):
        site = web_boundary.Site('A', self.parent / 'a.jsonl')
        site.start()
        try:
            web_measure.run(['--mal', site.url('/'), '--etikett', 'vardkontroll-adress',
                             '--handling-text', 'Gör en demoförfrågan'])
        finally:
            site.stop()
        self.assert_complete_measurement(latest('matning', 'vardkontroll-adress'))

    def test_a_local_file_is_served_read_only_and_measured_the_same_way(self):
        site = self.parent / 'komp'
        site.mkdir()
        server = web_boundary.Site('A', self.parent / 'x.jsonl')
        server.start()
        try:
            import urllib.request
            for name in ('/', '/stil.css', '/bild.png'):
                with urllib.request.urlopen(server.url(name)) as response:
                    (site / ('index.html' if name == '/' else name[1:])).write_bytes(response.read())
        finally:
            server.stop()
        web_measure.run(['--fil', str(site / 'index.html'), '--etikett', 'vardkontroll-fil',
                         '--handling-selektor', '[data-cta]'])
        receipt = self.assert_complete_measurement(latest('matning', 'vardkontroll-fil'))
        self.assertEqual(receipt['target']['kind'], 'fil')
        self.assertEqual(receipt['target']['sha256'], common.sha256_file(site / 'index.html'))

    def test_a_protected_address_is_reached_through_the_exception_and_the_value_is_nowhere(self):
        secret = 'falsk-' + token_source.token_hex(16)
        secret_file = ROOT / '.runtime' / ('web-vardkontroll-hemlighet-%s' % token_source.token_hex(4))
        descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(secret + '\n')
        site = web_boundary.Site('A', self.parent / 'skyddad.jsonl', secret=secret)
        site.start()
        try:
            web_measure.run(['--mal', site.url('/'), '--etikett', 'vardkontroll-skyddad',
                             '--handling-text', 'Gör en demoförfrågan', '--undantag-fil', str(secret_file)])
        finally:
            site.stop()
            secret_file.unlink()
        run = latest('matning', 'vardkontroll-skyddad')
        receipt = self.assert_complete_measurement(run)
        self.assertTrue(receipt['secret']['used'])
        self.assertEqual(receipt['secret']['hits_removed'], [])
        self.assertEqual(common.secret_hits(run, secret), [])
        log = web_boundary.read_log(self.parent / 'skyddad.jsonl')
        header = [i for i, row in enumerate(log) if row.get('header_present')]
        self.assertTrue(header, 'the exception was never presented')
        after = log[max(header) + 1:]
        self.assertTrue(after and all(r.get('cookie_present') and not r.get('header_present') for r in after))
        self.assertFalse([r for r in log if r.get('status') == 401])


class VisitorStartChecks(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.parent)

    def test_the_holder_reaches_a_target_whose_name_is_not_the_proxys_address(self):
        # Before D035 the host rules left only the target's name resolvable, so a target not named 127.0.0.1 left
        # the browser unable to reach its own proxy. `localhost` is such a name and still only reaches this host.
        site = web_boundary.Site('A', self.parent / 'namn.jsonl')
        site.start()
        run = self.parent / 'korning'
        (run / 'spar').mkdir(parents=True)
        workspace = web_visitor.prepare_workspace(self.parent, 'claude', 10)
        origin = 'http://localhost:%d' % site.port
        holder = None
        try:
            holder, ready = web_visitor.start_holder(run, workspace, origin + '/', [origin], 'desktop', 10)
            self.assertIsNone(web_visitor.start_problem(ready, [origin]), ready)
            self.assertEqual(ready['start'], origin + '/')
            self.assertIn('EXCLUDE 127.0.0.1', ready['resolver_rules'])
            code, text = web_boundary.run_action('claude', workspace, ['read'])
            self.assertEqual(code, 0, text)
            self.assertIn('ADRESS: %s/' % origin, text)
        finally:
            if holder:
                web_visitor.stop_holder(holder)
            common.end_chrome(run / '.chrome-profil')
            site.stop()
        log = web_boundary.read_log(self.parent / 'namn.jsonl')
        self.assertTrue(log and all(row['host'] == 'localhost:%d' % site.port for row in log), log)

    def test_no_model_starts_when_the_start_page_does_not_open(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            closed = probe.getsockname()[1]
        task = self.parent / 'UPPGIFT.md'
        task.write_text('Hitta kontaktsidan.')
        never = mock.Mock(side_effect=AssertionError('a model would start'))
        with mock.patch.object(web_visitor, 'claude_command', never), \
                mock.patch.object(web_visitor, 'codex_command', never), contextlib.redirect_stdout(io.StringIO()):
            code = web_visitor.run(['--start', 'http://127.0.0.1:%d/' % closed, '--tillatna',
                                    'http://127.0.0.1:%d' % closed, '--uppgift', str(task), '--vy', 'mobil',
                                    '--utforare', 'claude', '--modell', 'claude-opus-5', '--etikett', 'vardkontroll-start'])
        self.assertEqual(code, 1)
        never.assert_not_called()
        run = latest('provare', 'vardkontroll-start')
        receipt = json.loads((run / 'KVITTO.json').read_text())
        self.assertEqual(receipt['outcome'], 'start_misslyckades')
        self.assertIsNone(receipt['session'])
        self.assertTrue(receipt['start_problem'])
        self.assertTrue(receipt['holder_stopped'] and receipt['chrome_profile_removed'])
        for absent in ('start.json', 'session.jsonl', 'slutrapport.txt'):
            self.assertFalse((run / absent).exists(), absent)


def processes_naming(text):
    listing = subprocess.run(['/bin/ps', '-axww', '-o', 'pid=,command='], capture_output=True, text=True,
                             check=True).stdout
    return [int(line.split(None, 1)[0]) for line in listing.splitlines() if text in line]


def until(condition, seconds):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.2)
    return condition()


class ChildChecks(unittest.TestCase):
    """A run that ends other than normally leaves none of its processes, and no Chrome profile, behind (D035, D036):
    not after a time limit, an error, SIGTERM, or a killed command."""

    def setUp(self):
        self.parent = Path(tempfile.mkdtemp()).resolve()
        self.site = web_boundary.Site('A', self.parent / 'a.jsonl')
        self.site.start()
        self.started = []

    def tearDown(self):
        for process in self.started:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
        self.site.stop()
        shutil.rmtree(self.parent)

    def command(self, *arguments):
        environment = dict(os.environ, NR_HOST_ROOT=str(ROOT))
        process = subprocess.Popen([sys.executable, '-B', *arguments], cwd=CODE_ROOT, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self.started.append(process)
        return process

    def running_measurement(self, label):
        """The run directory of a measurement command once its Chrome is running."""
        def found():
            runs = sorted((ROOT / '.runtime/profiler/matning').glob('*-' + label))
            return runs and common.chrome_processes(runs[-1] / '.chrome-profil') and runs[-1]
        self.assertTrue(until(found, 60), 'the measurement never started its Chrome')
        return found()

    def test_a_measurement_ended_by_its_time_limit_leaves_no_chrome(self):
        with mock.patch.object(web_measure, 'MEASURE_SECONDS', 4):
            web_measure.run(['--mal', self.site.url('/'), '--etikett', 'vardkontroll-tidsgrans'])
        run = latest('matning', 'vardkontroll-tidsgrans')
        receipt = json.loads((run / 'KVITTO.json').read_text())
        self.assertEqual(receipt['browser_half']['exit'], 'tidsgräns')
        self.assertEqual(common.chrome_processes(run / '.chrome-profil'), [])
        self.assertEqual(processes_naming(str(run / 'matning-konfig.json')), [])
        self.assertFalse((run / '.chrome-profil').exists())

    def test_a_visitor_that_fails_after_its_holder_started_leaves_no_holder_and_no_chrome(self):
        task = self.parent / 'UPPGIFT.md'
        task.write_text('Hitta kontaktsidan.')
        failing = mock.Mock(side_effect=RuntimeError('provfel efter start'))
        with mock.patch.object(web_visitor, 'claude_command', failing), \
                mock.patch.object(web_visitor, 'codex_command', failing), self.assertRaises(RuntimeError):
            web_visitor.run(['--start', self.site.url('/'), '--tillatna', 'http://127.0.0.1:%d' % self.site.port,
                             '--uppgift', str(task), '--vy', 'mobil', '--utforare', 'claude', '--modell',
                             'claude-opus-5', '--etikett', 'vardkontroll-fel'])
        failing.assert_called_once()
        run = latest('provare', 'vardkontroll-fel')
        self.assertTrue((run / 'hallare-stopp.json').is_file())
        self.assertEqual(common.chrome_processes(run / '.chrome-profil'), [])
        self.assertEqual(processes_naming(str(run / 'hallare-konfig.json')), [])
        self.assertFalse((run / '.chrome-profil').exists())

    def test_a_measurement_command_stopped_by_sigterm_ends_its_children_before_it_exits(self):
        process = self.command('-m', 'runtime.web_measure', '--mal', self.site.url('/'), '--etikett',
                               'vardkontroll-sigterm')
        run = self.running_measurement('vardkontroll-sigterm')
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=90)
        # Checked at once: the command's own cleanup, not the children noticing later that their parent is gone.
        self.assertEqual(common.chrome_processes(run / '.chrome-profil'), [])
        self.assertEqual(processes_naming(str(run / 'matning-konfig.json')), [])
        self.assertEqual(process.returncode, 3, output)
        self.assertEqual(json.loads(output.strip().splitlines()[-1])['outcome'], 'avbruten')
        self.assertFalse((run / 'KVITTO.json').exists())
        self.assertFalse((run / '.chrome-profil').exists())

    def test_a_measurement_whose_command_was_killed_ends_by_itself(self):
        # A local address that accepts and never answers, so the measurement cannot finish by itself in the window.
        with socket.socket() as silent:
            silent.bind(('127.0.0.1', 0))
            silent.listen(16)
            process = self.command('-m', 'runtime.web_measure', '--mal',
                                   'http://127.0.0.1:%d/' % silent.getsockname()[1], '--etikett', 'vardkontroll-dod')
            run = self.running_measurement('vardkontroll-dod')
            process.kill()
            process.wait()
            self.assertTrue(until(lambda: not common.chrome_processes(run / '.chrome-profil')
                                  and not processes_naming(str(run / 'matning-konfig.json')), 20))
            self.assertTrue(until(lambda: not (run / '.chrome-profil').exists(), 5))

    def test_a_holder_whose_command_was_killed_stops_by_itself(self):
        run = self.parent / 'korning'
        (run / 'spar').mkdir(parents=True)
        origin = 'http://127.0.0.1:%d' % self.site.port
        script = ('import sys, tempfile, time; from pathlib import Path; from runtime import web_visitor as v; '
                  'w = v.prepare_workspace(Path(tempfile.mkdtemp(dir=sys.argv[3])), "claude", 10); '
                  'v.start_holder(Path(sys.argv[1]), w, sys.argv[2] + "/", [sys.argv[2]], "desktop", 10); '
                  'print("klar", flush=True); time.sleep(600)')
        process = self.command('-c', script, str(run), origin, str(self.parent))
        self.assertEqual(process.stdout.readline().strip(), 'klar')
        self.assertTrue(processes_naming(str(run / 'hallare-konfig.json')))
        process.kill()
        process.wait()
        self.assertTrue(until(lambda: not common.chrome_processes(run / '.chrome-profil')
                              and not processes_naming(str(run / 'hallare-konfig.json')), 20))
        self.assertTrue((run / 'hallare-stopp.json').is_file())
        self.assertFalse((run / '.chrome-profil').exists())

    def test_a_holder_whose_command_was_killed_during_its_start_ends_by_itself(self):
        # The start page never answers, so the holder is still in its start navigation, before its full stop is armed.
        run = self.parent / 'korning'
        (run / 'spar').mkdir(parents=True)
        with socket.socket() as silent:
            silent.bind(('127.0.0.1', 0))
            silent.listen(16)
            origin = 'http://127.0.0.1:%d' % silent.getsockname()[1]
            script = ('import sys, tempfile; from pathlib import Path; from runtime import web_visitor as v; '
                      'w = v.prepare_workspace(Path(tempfile.mkdtemp(dir=sys.argv[3])), "claude", 10); '
                      'v.start_holder(Path(sys.argv[1]), w, sys.argv[2] + "/", [sys.argv[2]], "desktop", 10)')
            process = self.command('-c', script, str(run), origin, str(self.parent))
            self.assertTrue(until(lambda: common.chrome_processes(run / '.chrome-profil'), 60), 'Chrome never started')
            self.assertFalse((run / 'hallare-klar.json').exists())
            process.kill()
            process.wait()
            self.assertTrue(until(lambda: not common.chrome_processes(run / '.chrome-profil')
                                  and not processes_naming(str(run / 'hallare-konfig.json')), 20))
            # Chrome had started (the check above waited for it), so the profile goes with the holder's exit (D036).
            self.assertTrue(until(lambda: not (run / '.chrome-profil').exists(), 5))


if __name__ == '__main__':
    unittest.main()
