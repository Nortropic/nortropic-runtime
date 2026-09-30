"""The pinned Codex CLI (D047): every launch reads one path, and the measurements are of that program."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from runtime import codex_pin, profile, web_visitor
from runtime.release import ROOT
from scripts.probe_bridge import worker_command

CODE = Path(__file__).resolve().parents[1]           # the checkout under test, whatever NR_HOST_ROOT names
EVIDENCE = CODE / codex_pin.EVIDENCE
VERSIONED_PATH = re.compile(r'codex-\d+\.\d+\.\d+')


class OnePathTests(unittest.TestCase):
    def test_the_pin_names_a_directory_of_its_own_for_its_version(self):
        self.assertEqual(codex_pin.BINARY, '.runtime/bin/codex-%s/codex' % codex_pin.VERSION)
        self.assertEqual(codex_pin.EVIDENCE, 'evidence/codex-' + codex_pin.VERSION)
        self.assertRegex(codex_pin.SHA256, '^[0-9a-f]{64}$')

    def test_the_startup_chain_launches_the_pinned_binary(self):
        self.assertEqual(worker_command()[0], str(ROOT / codex_pin.BINARY))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(profile.command(Path(directory), writable=False)[0], str(ROOT / codex_pin.BINARY))
            self.assertEqual(profile.sandbox_command(Path(directory), ['true'])[0], str(ROOT / codex_pin.BINARY))
            self.assertEqual(web_visitor.codex_sandbox_command(Path(directory), ['true'])[0],
                             str((ROOT / codex_pin.BINARY).resolve()))

    def test_the_activator_compares_the_measurement_with_the_same_path(self):
        from scripts import model_choice
        self.assertEqual(model_choice.CODEX_BINARY, codex_pin.BINARY)

    def test_no_code_names_a_codex_version_of_its_own(self):
        named = []
        for folder in ('runtime', 'scripts'):
            for path in sorted((CODE / folder).glob('*.py')):
                if path.name == 'codex_pin.py' or path.name.startswith('test_'):
                    continue
                for number, line in enumerate(path.read_text().splitlines(), 1):
                    if VERSIONED_PATH.search(line):
                        named.append('%s/%s:%d' % (folder, path.name, number))
        self.assertEqual(named, [], 'a Codex version belongs in runtime/codex_pin.py only')

    def test_the_issuer_reads_the_pin_file_it_imports(self):
        from runtime import check_issuer
        from scripts import host_publication
        self.assertIn('runtime/codex_pin.py', check_issuer.CODE)
        self.assertIn('runtime/codex_pin.py', host_publication.CODE)


class MeasuredProgramTests(unittest.TestCase):
    def test_the_provenance_is_of_the_pinned_bytes_from_the_official_release(self):
        record = json.loads((EVIDENCE / 'provenance.json').read_text())
        codex = record['installed']['codex']
        self.assertEqual(codex['path'], codex_pin.BINARY)
        self.assertEqual(codex['sha256'], codex_pin.SHA256)
        self.assertEqual(codex['reports'], 'codex-cli ' + codex_pin.VERSION)
        self.assertTrue(codex['code_signature_verifies'])
        self.assertEqual(codex['code_signature'], record['previous']['code_signature'], 'the same signer as before')
        self.assertEqual(record['source']['release'], 'openai/codex rust-v' + codex_pin.VERSION)
        self.assertEqual({name: t['digest_equal'] for name, t in record['source']['tarballs'].items()},
                         {'codex-aarch64-apple-darwin.tar.gz': True,
                          'codex-code-mode-host-aarch64-apple-darwin.tar.gz': True})
        self.assertEqual(record['installed']['codex-code-mode-host']['path'],
                         str(Path(codex_pin.BINARY).parent / 'codex-code-mode-host'))

    def test_the_sandbox_keeps_its_boundary(self):
        shape = json.loads((EVIDENCE / 'sandbox-shape.json').read_text())
        self.assertTrue(shape['read_the_workspace'])
        self.assertTrue(shape['scratch_written'])
        self.assertFalse(shape['read_only_written'])
        self.assertFalse(shape['home_written'])
        self.assertNotEqual(shape['exit_status']['network'], '0', 'the network stays closed')

    def test_an_exec_run_ends_in_a_terminal_the_runtime_reads(self):
        shape = json.loads((EVIDENCE / 'exec-shape.json').read_text())
        self.assertEqual(shape['returncode'], 0)
        self.assertTrue(shape['valid_terminal'])
        self.assertEqual(shape['answer'], '42', 'the last agent message is the answer')
        self.assertTrue(shape['answer_correct'])
        self.assertIn('turn.completed', shape['event_types'])


if __name__ == '__main__':
    unittest.main()
