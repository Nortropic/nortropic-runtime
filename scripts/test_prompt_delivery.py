"""The host must deliver the whole prompt and close stdin, under its own bound and stop.

Measured on the live application 2026-09-22: both review runs of ap11-step-5 produced a ZERO-byte event stream and
an empty stderr, at 182.2 s under a 180 s bound and again at 302.0 s under the raised 300 s bound, while the process
had started. The same invocation, the same workspace and the same 19777-byte prompt answer in seconds when the
prompt is written and stdin closed up front, so the bound was never the cause and raising it fixed nothing.

The cause is in the delivery: subprocess.communicate(input, timeout) abandons a partially written input when its
timeout fires and never closes stdin, so a child that is slow to read waits for an EOF that never comes. CPython
issue 141473 describes the same mechanism. Neither that issue nor the local reproduction is treated here as proof
that the correction works: these tests exercise the real transfer() with model-free children.

No model runs here. Every child is a plain Python process.
"""
import contextlib
import io
import os
import signal
import subprocess
import tempfile
import threading
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.attempt import transfer
from runtime.development_scope import ScopeClosed

# Measured by review N: a subprocess stdin pipe stalls at 16384 bytes on this host, and communicate writes it in
# 512-byte chunks, so the live 19777-byte prompt was just over the ceiling and 3393 bytes were abandoned. A payload
# well past that makes the transfer really continue across passes instead of fitting in one write; a short message
# would prove nothing about delayed delivery, and one under 16 KiB would not have failed even with the old code.
PAYLOAD = (b'nortropic-prompt-' * 4096 + b'\n') * 4      # ~272 KiB
STDIN_PIPE_STALL = 16384                                 # measured on this host


def child(body):
    return [sys.executable, '-c', 'import os,sys,time\n' + body]


# Reads its stdin to EOF at once and reports exactly what arrived.
READS_NOW = child('data = sys.stdin.buffer.read()\n'
                  'sys.stdout.write("%d %s\\n" % (len(data), __import__("hashlib").sha256(data).hexdigest()))\n')
# Does nothing for three seconds, then reads to EOF. This is the live shape: a child slow to start reading.
READS_LATE = child('time.sleep(3)\n'
                   'data = sys.stdin.buffer.read()\n'
                   'sys.stdout.write("%d %s\\n" % (len(data), __import__("hashlib").sha256(data).hexdigest()))\n')
# Never reads at all; the pipe fills and stays full.
NEVER_READS = child('time.sleep(600)\n')
# Exits immediately, before the transfer can finish.
EXITS_EARLY = child('sys.exit(7)\n')


class PromptDeliveryTests(unittest.TestCase):
    def run_child(self, argv, seconds, control=None, payload=PAYLOAD, watchdog=45):
        """Every run is bounded by a watchdog of its own: review N showed that neutering os.set_blocking makes the
        transfer block forever, and an unbounded test turns that into a hung suite instead of a red test."""
        alarm = threading.Timer(watchdog, lambda: os.kill(os.getpid(), signal.SIGALRM))
        previous = signal.signal(signal.SIGALRM, self._expired)
        alarm.start()
        self.addCleanup(alarm.cancel)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        read, write = os.pipe()
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=write, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        os.close(write)
        started = time.monotonic()
        outcome = None
        try:
            transfer(proc, payload, argv, seconds, started, control=control)
        except BaseException as error:                       # noqa: BLE001 - the outcome is what is being measured
            outcome = error
        elapsed = time.monotonic() - started
        os.set_blocking(read, False)
        try:
            reported = os.read(read, 4096)
        except BlockingIOError:
            reported = b''
        os.close(read)
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        return {'outcome': outcome, 'elapsed': elapsed, 'reported': reported.decode().strip(),
                'returncode': proc.returncode, 'stdin_closed': proc.stdin.closed}

    @staticmethod
    def _expired(signum, frame):
        raise AssertionError('the transfer did not return within the watchdog: it is blocking somewhere')

    def expect_whole_payload(self, result):
        import hashlib
        self.assertIsNone(result['outcome'], 'the transfer completed without raising')
        size, digest = result['reported'].split()
        self.assertEqual(int(size), len(PAYLOAD), 'byte-identical length')
        self.assertEqual(digest, hashlib.sha256(PAYLOAD).hexdigest(), 'byte-identical content')
        self.assertTrue(result['stdin_closed'], 'and the child saw EOF, or read() would never have returned')

    def test_a_child_that_reads_at_once_receives_every_byte_and_an_eof(self):
        self.expect_whole_payload(self.run_child(READS_NOW, 30))

    def test_a_child_that_starts_reading_late_still_receives_every_byte_and_an_eof(self):
        """The live shape. The old delivery gave this child nothing at all."""
        result = self.run_child(READS_LATE, 30)
        self.expect_whole_payload(result)
        self.assertGreater(result['elapsed'], 3, 'the transfer really did span the delay')
        self.assertGreater(len(PAYLOAD), STDIN_PIPE_STALL,
                           'and the payload is past where a stdin pipe stalls, so it could not go out in one write')

    def test_a_child_that_never_reads_is_ended_by_the_runs_own_deadline(self):
        result = self.run_child(NEVER_READS, 4)
        self.assertIsInstance(result['outcome'], subprocess.TimeoutExpired,
                              'the transfer is bounded by the same seconds as the run')
        self.assertLess(result['elapsed'], 8, 'and it does not wait past that bound')

    def test_a_child_that_exits_before_the_transfer_finishes_is_not_the_host_failing(self):
        result = self.run_child(EXITS_EARLY, 30)
        self.assertIsNone(result['outcome'], 'no exception: the child ended, the host did not fail to deliver')
        self.assertEqual(result['returncode'], 7, "and the child's own result decides the outcome")
        self.assertTrue(result['stdin_closed'])

    def test_the_transfer_obeys_a_stop_while_it_is_still_sending(self):
        """Stop capability must survive the change: the old loop re-read the control every pass and so does this."""
        states = iter(['active', 'active', 'stopped'] + ['stopped'] * 50)
        result = self.run_child(NEVER_READS, 30, control=lambda: next(states))
        self.assertIsInstance(result['outcome'], ScopeClosed)
        self.assertIn('Active scoped process stopped: stopped', str(result['outcome']))
        self.assertLess(result['elapsed'], 10, 'the stop is honoured while sending, not after the deadline')

    def test_a_stop_signal_during_the_stdin_close_is_not_swallowed(self):
        """Review N: InterruptedError IS an OSError, so a signal landing in the close would have been consumed with
        no effect. The window is a single syscall, so the guard is measured directly - no child, no timing, nothing
        that could make this pass or fail by ordering."""
        read, write = os.pipe()
        self.addCleanup(os.close, read)

        class Stdin:
            def __init__(self, descriptor):
                self._descriptor = descriptor

            def fileno(self):
                return self._descriptor

            def close(self):
                os.close(self._descriptor)
                raise InterruptedError(15)

        stand_in = type('Proc', (), {'stdin': Stdin(write)})()
        with self.assertRaises(InterruptedError):
            transfer(stand_in, b'a short payload that goes out in one write', ['stand-in'], 30, time.monotonic())

    def test_a_paused_scope_keeps_sending_because_a_started_run_may_finish(self):
        result = self.run_child(READS_LATE, 30, control=lambda: 'paused')
        self.expect_whole_payload(result)

    def test_the_control_is_read_on_every_pass_not_only_at_the_start(self):
        seen = []

        def control():
            seen.append(time.monotonic())
            return 'active'
        self.run_child(READS_LATE, 30, control=control)
        self.assertGreater(len(seen), 3, 'the scope is re-read while the transfer is still in progress')


class AttemptPathTests(unittest.TestCase):
    """The whole affected attempt path, with a model-free provider.

    transfer() being correct is not enough: what failed live was a real run, so the wiring from execute() to the
    delivery is measured here rather than argued. The provider is a plain Python process that reports the prompt it
    received and then writes a valid event stream, so no model runs.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'task'; (self.state / 'candidate').mkdir(parents=True)
        self.evidence = self.root / 'evidence'; self.evidence.mkdir()

    def test_the_real_attempt_path_delivers_the_whole_prompt_to_its_provider(self):
        from runtime import attempt as attempt_module
        import hashlib
        received = self.root / 'received.txt'
        provider = child('time.sleep(2)\n'
                         'data = sys.stdin.buffer.read()\n'
                         'open(%r, "w").write("%%d %%s" %% (len(data), __import__("hashlib").sha256(data).hexdigest()))\n'
                         'sys.stdout.write(\'{"type":"system","subtype":"init"}\\n\')\n'
                         % str(received))
        task = {'id': 'delivery-probe', 'attempt_seconds': 60, 'allowed_paths': ['tools/x.py'],
                'target': 'Nortropic/nortropic-projektkontor', 'steps': [{'provider': 'codex'}]}
        prompt = PAYLOAD.decode('latin-1')
        with patch.object(attempt_module, 'load', return_value=task), \
             patch.object(attempt_module, 'task_directory', return_value=self.state), \
             patch.object(attempt_module, 'evidence_directory', return_value=self.evidence), \
             patch.object(attempt_module, 'command', return_value=provider), \
             patch.object(attempt_module, 'reserve_task_call', return_value=None), \
             patch.object(attempt_module, 'ROOT', self.root):
            # execute() prints its own report; the publication wrapper requires the suite's last line to be OK.
            with contextlib.redirect_stdout(io.StringIO()) as reported:
                attempt_module.execute('delivery-probe', 1, prompt, 30, provider='codex')
        self.assertIn('delivery-probe', reported.getvalue(), 'the run reported on its own stream, not on the suite')
        self.assertTrue(received.is_file(), 'the provider reported what it received')
        size, digest = received.read_text().split()
        self.assertEqual(int(size), len(prompt.encode()), 'byte-identical length through the real path')
        self.assertEqual(digest, hashlib.sha256(prompt.encode()).hexdigest(), 'byte-identical content')


if __name__ == '__main__':
    unittest.main()
