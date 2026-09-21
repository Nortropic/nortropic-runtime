"""The local engine is started with an explicit history safety margin; synthetic, no engine is started."""
import unittest

from runtime import service


class EngineLimitTest(unittest.TestCase):
    def test_history_limits_are_explicit_ordered_and_above_the_engine_default(self):
        pairs = dict(value.split('=') for value in service.HISTORY_LIMITS[1::2])
        self.assertEqual(service.HISTORY_LIMITS[0::2], ['--dynamic-config-value']*4)
        self.assertEqual(set(pairs), {'limit.historyCount.warn', 'limit.historyCount.error', 'limit.historySize.warn', 'limit.historySize.error'})
        self.assertGreater(int(pairs['limit.historyCount.error']), 51200)
        self.assertLess(int(pairs['limit.historyCount.warn']), int(pairs['limit.historyCount.error']))
        self.assertGreater(int(pairs['limit.historySize.error']), 50*1024*1024)
        self.assertLess(int(pairs['limit.historySize.warn']), int(pairs['limit.historySize.error']))

    def test_the_real_engine_start_passes_them_to_the_pinned_cli(self):
        """Runs the REAL LocalService.__aenter__ up to the process start, which is captured and refused."""
        import asyncio, tempfile
        from pathlib import Path
        from unittest.mock import patch
        seen = []
        def popen(command, **kwargs):
            seen.append(list(command)); raise RuntimeError('captured before any engine starts')
        with tempfile.TemporaryDirectory() as directory, patch.object(service, 'ROOT', Path(directory)), \
             patch.object(service, 'require_ports_available', return_value=None), patch.object(service.subprocess, 'Popen', side_effect=popen):
            (Path(directory)/'.runtime').mkdir()
            local = service.LocalService(Path(directory)/'.runtime/db.sqlite', Path(directory)/'out')
            with self.assertRaisesRegex(RuntimeError, 'captured before any engine starts'):
                asyncio.run(local.__aenter__())
        self.assertEqual(len(seen), 1); command = seen[0]
        self.assertEqual(command[-len(service.HISTORY_LIMITS):], service.HISTORY_LIMITS)
        self.assertIn('start-dev', command); self.assertEqual(command[command.index('--db-filename')+1], str(Path(directory)/'.runtime/db.sqlite'))

if __name__ == '__main__':
    unittest.main()
