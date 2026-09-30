"""Preserved-host attempts use a synthetic private ledger, never real host state."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from runtime.failure_ledger import Ledger, Refused
from scripts import run_host_checks as host


class HostAttemptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.book = Ledger(self.root/'book', {'literals': []})
        self.commit = 'a'*40
        self.old_cwd = Path.cwd(); self.addCleanup(os.chdir, self.old_cwd)

    def run_host(self, name, failing=False, diagnostic=None, lost=False, interrupted=False):
        class Case(unittest.TestCase):
            def test_host_case(inner):
                if interrupted: raise KeyboardInterrupt()
                if failing: inner.fail('synthetic failure')
        suite = unittest.TestSuite([Case('test_host_case')])
        with patch.dict(os.environ, {'NR_HOST_ROOT': str(self.root/'preserved')}), \
             patch('runtime.failure_ledger.Ledger', return_value=self.book), \
             patch.object(host, 'git', side_effect=lambda *a: self.commit if a[-1]=='HEAD' else ''), \
             patch.object(host.unittest.defaultTestLoader, 'loadTestsFromName', side_effect=RuntimeError('synthetic import loss') if lost else None, return_value=suite):
            return host.main(self.root/name, diagnostic)

    def receipt(self, name):
        import json
        return json.loads((self.root/name).read_text())

    def test_green_receipt_binds_actual_begin_finish_source_and_is_exclusive(self):
        self.assertEqual(self.run_host('green.json'), 0)
        receipt = self.receipt('green.json')
        self.book.require_host(self.commit, receipt)
        for change in ({'runner_sha256': 'f'*64}, {'journal_head': {'changed': True}},
                       {'ledger_finish_sha256': '0'*64}, {'cases': []}, {'run': True}):
            with self.subTest(change=change), self.assertRaises(Refused):
                self.book.require_host(self.commit, dict(receipt, **change))
        with self.assertRaises(FileExistsError): self.run_host('green.json')
        self.assertEqual(len(self.book.begins(self.commit)), 1)

    def test_red_blocks_new_host_attempt_and_green_diagnostic_never_qualifies(self):
        self.assertEqual(self.run_host('red.json', failing=True), 1)
        failed = self.receipt('red.json')['ledger_run']
        with self.assertRaises(Refused): self.run_host('retry.json')
        self.assertEqual(self.run_host('diagnostic.json', diagnostic=failed), 0)
        with self.assertRaises(Refused): self.book.require_host(self.commit, self.receipt('diagnostic.json'))
        self.assertFalse(self.book.publishable(self.commit))

    def test_import_loss_is_permanent_before_the_first_test_can_start(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic import loss'):
            self.run_host('lost.json', lost=True)
        begins = self.book.begins(self.commit)
        self.assertEqual(len(begins), 1)
        ending = self.book.ending(begins[0])
        self.assertFalse(ending['complete']); self.assertFalse(ending['passed'])
        with self.assertRaises(Refused): self.run_host('later-green.json')

    def test_interruption_preserves_the_started_case_as_unknown(self):
        with self.assertRaises(KeyboardInterrupt): self.run_host('interrupt.json', interrupted=True)
        ending = self.book.ending(self.book.begins(self.commit)[0])
        self.assertFalse(ending['complete']); self.assertFalse(ending['passed'])
        self.assertEqual(len(ending['cases']), 1)
        self.assertEqual(ending['cases'][0]['status'], 'unknown')

    def test_read_acl_is_refused_before_host_import_or_first_receipt_byte(self):
        import subprocess
        from runtime.measurement_observer import Refused as OutputRefused
        subprocess.run(['/bin/chmod','+a','user:_spotlight allow read,file_inherit',str(self.root)],check=True)
        with patch.object(host.unittest.defaultTestLoader,'loadTestsFromName') as imported:
            with self.assertRaises(OutputRefused):self.run_host('private.json')
        imported.assert_not_called()
        self.assertEqual(self.book.begins(self.commit),[])
        output=self.root/'private.json'
        self.assertFalse(output.exists() and output.stat().st_size>0)

    def test_public_or_linked_receipt_parent_refuses_before_host_attempt(self):
        from runtime.measurement_observer import Refused as OutputRefused
        public=self.root/'public';public.mkdir(mode=0o755);public.chmod(0o755)
        linked=self.root/'linked';linked.symlink_to(public,target_is_directory=True)
        for relative in ('public/receipt.json','linked/receipt.json'):
            with self.subTest(relative=relative),self.assertRaises(OutputRefused):self.run_host(relative)
        self.assertEqual(self.book.begins(self.commit),[])
        self.assertFalse((public/'receipt.json').exists())
