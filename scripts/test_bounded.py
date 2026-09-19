"""Real process regressions for the operator experiment limiter."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('bounded.py')
CHILD = 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'


class BoundedTest(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory(prefix='nr-bounded-') as directory:
            output = Path(directory) / 'evidence'
            leader = ('import subprocess,sys,time; '
                      'p=subprocess.Popen([sys.executable,"-c",' + repr(CHILD) + '],stdout=subprocess.PIPE); '
                      'p.stdout.readline(); print(p.pid,flush=True); '
                      + ('time.sleep(60)' if mode != 'normal' else 'sys.exit(0)'))
            proc = subprocess.Popen([sys.executable, str(SCRIPT), '--seconds', '1' if mode == 'timeout' else '30',
                                     '--output', str(output), '--', sys.executable, '-c', leader],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    p = output / 'stdout.log'
                    if p.exists() and p.read_text().strip():
                        break
                    time.sleep(0.02)
                else:
                    self.fail('fixture child never became ready')
                child_pid = int(p.read_text().strip())
                if mode == 'signal':
                    proc.send_signal(signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=10)
                self.assertEqual(proc.returncode, {'normal': 0, 'timeout': 124, 'signal': 143}[mode], stderr + stdout)
                metadata = json.loads((output / 'run.json').read_text())
                self.assertTrue(metadata['process_group_removed'])
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def test_normal_leader_exit_with_term_ignoring_child(self):
        self.exercise('normal')

    def test_timeout_with_term_ignoring_child(self):
        self.exercise('timeout')

    def test_sigterm_with_term_ignoring_child(self):
        self.exercise('signal')


if __name__ == '__main__':
    unittest.main()
