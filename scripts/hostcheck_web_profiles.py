"""Host checks of the web profiles (D034): the real Chrome, the pinned tools, Runtime's sandbox and local sites.

Deliberately NOT named test_*.py, so the published suite discovers none of them: they need this host's Chrome, Node,
the pinned tool copy and the sandbox binary, and a skip inside the suite would be indistinguishable from a check that
quietly stopped. They run separately, and scripts/run_web_host_checks.py records their result as a receipt bound to
the commit, the bytes it exercised, where they were imported from, and the tool identities.

Nothing here starts a model or reaches anything but 127.0.0.1.
"""
import json
import os
from pathlib import Path
import secrets as token_source
import shutil
import tempfile
import unittest

from runtime import web_boundary, web_common as common, web_measure
from runtime.release import ROOT


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


if __name__ == '__main__':
    unittest.main()
