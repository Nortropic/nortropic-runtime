"""Isolated fake-provider process tests, explicitly not application evidence."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from runtime import development_model as model, development_host as host, model_question
from runtime.development_scope import Scope, ScopeClosed, initialize
from scripts.test_development_scope import contract


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.scope = Scope(self.root/'scope', initialize(self.root/'scope', contract()))
        self.nonce = 'fixture-call'
        self.stage = self.scope.directory/'calls'/self.nonce
        self.workspace = self.stage/'workspace'
        self.workspace.mkdir(parents=True); (self.workspace/'.scratch').mkdir()
        schema = {'type': 'object'}
        files = {'CONTEXT.json': b'{"synthetic":true}', 'OUTPUT_SCHEMA.json': json.dumps(schema).encode()}
        for name, value in files.items(): (self.workspace/name).write_bytes(value)
        data = {'prompt': 'Synthetic no-model process fixture', 'schema': schema, 'work': 'goal',
                'role': 'driver', 'seconds': 5,
                'workspace_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
        raw = json.dumps(data).encode(); (self.stage/'input.json').write_bytes(raw)
        self.request = {'contract_sha256': self.scope.expected, 'nonce': self.nonce,
                        'input_sha256': hashlib.sha256(raw).hexdigest()}
        # A capacity question is a host record; here it lands in this test's own directory, never in the checkout.
        for patcher in (patch.object(model_question, 'ROOT', self.root), patch('runtime.release.installed', return_value=None)):
            patcher.start(); self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temp.cleanup()

    def run_fixture(self, events):
        # command() receives --output-schema after our -c program; Python
        # ignores those argv values. No Codex binary/model is invoked.
        source = 'import json\nfor e in '+repr(events)+': print(json.dumps(e),flush=True)'
        with patch.object(model, 'active_scope', return_value=(self.scope, {})), \
             patch.object(model, 'command', return_value=[sys.executable, '-u', '-c', source, '-']), \
             patch.object(model, 'require_workspace_instructions', return_value={}), \
             patch.object(model, 'environment', return_value={}):
            return model.execute(self.request)

    def events(self):
        return [{'type': 'thread.started', 'thread_id': 'synthetic-native-like-id'},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"action":"hold"}'}},
                {'type': 'turn.completed', 'usage': {'input_tokens': 1}}]

    def test_process_context_count_cleanup_and_no_redelivery(self):
        result = self.run_fixture(self.events())
        self.assertTrue(result['completed']); self.assertTrue(result['process_group_removed'])
        self.assertEqual(len(self.scope.inspect()['calls']), 1)
        self.assertEqual(self.scope.inspect()['started'], [self.nonce])
        self.assertEqual(host.call_result(self.scope, self.nonce, 'driver'), result)
        launch = json.loads((self.stage/'launch.json').read_text())
        self.assertNotEqual(subprocess.run(['ps', '-p', str(launch['provider_pid'])], capture_output=True).returncode, 0)
        with self.assertRaises(FileExistsError): self.run_fixture(self.events())
        self.assertEqual(len(self.scope.inspect()['calls']), 1)

    def test_changed_context_prevents_first_launch_and_later_reuse(self):
        (self.workspace/'CONTEXT.json').write_text('{"changed":true}')
        with self.assertRaises(ScopeClosed): self.run_fixture(self.events())
        self.assertEqual(self.scope.inspect()['calls'], [])

    def test_after_call_changed_context_is_not_a_fresh_approval(self):
        self.run_fixture(self.events())
        (self.workspace/'CONTEXT.json').write_text('{"changed":true}')
        with self.assertRaises(ValueError): host.call_result(self.scope, self.nonce, 'driver')

    def test_driver_output_cannot_be_used_as_separate_review(self):
        self.run_fixture(self.events())
        with self.assertRaises(ValueError): host.call_result(self.scope, self.nonce, 'preparation-review')

    def test_provider_quota_error_persists_without_new_start(self):
        result = self.run_fixture([{'type': 'thread.started', 'thread_id': 'fixture'},
                                   {'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}])
        self.assertFalse(result['completed']); self.assertEqual(self.scope.inspect()['control'], 'quota')
        with self.assertRaises(ScopeClosed): self.scope.reserve('goal', 'driver', 'new')
        self.assertEqual(len(self.scope.inspect()['calls']), 1)
        # The wait now carries the owner's question (D030): which executor and model, in the provider's own words.
        question = json.loads((self.root / result['model_question']).read_text())
        self.assertEqual((question['executor'], question['model'], question['provider_said']), ('codex', 'gpt-6-astra', 'usage limit reached'))
        self.assertEqual(question['where'], {'kind': 'goal call', 'role': 'driver', 'nonce': self.nonce})
        self.assertIs(question['automatic_switch'], False)

    def test_a_failure_that_is_not_capacity_asks_nothing(self):
        result = self.run_fixture([{'type': 'thread.started', 'thread_id': 'fixture'},
                                   {'type': 'turn.failed', 'error': {'message': 'stream disconnected'}}])
        self.assertFalse(result['completed']); self.assertNotIn('model_question', result)
        self.assertFalse(model_question.home().exists())

    def test_agent_claim_of_quota_is_not_provider_authority(self):
        events = self.events(); events[1]['item']['text'] = '{"reason":"quota usage limit"}'
        self.assertTrue(self.run_fixture(events)['completed'])
        self.assertEqual(self.scope.inspect()['control'], 'active')


# The real guardian in its own process, as the worker starts it; only what run_fixture() substitutes is substituted.
GUARDIAN = '''
import json, sys
from pathlib import Path
from unittest.mock import patch
from runtime import development_model as model
from runtime.development_scope import Scope
root, expected, provider = Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
with patch.object(model, 'active_scope', return_value=(Scope(root / 'scope', expected), {})), \\
     patch.object(model, 'command', return_value=provider), \\
     patch.object(model, 'require_workspace_instructions', return_value={}), \\
     patch.object(model, 'environment', return_value={}):
    print(json.dumps(model.execute(json.load(sys.stdin))))
'''


class GuardianSignalTests(unittest.TestCase):
    """The guardian's own termination handling, driven by a REAL signal to a REAL guardian process (D026).

    Found live, not by review: the fourth assessment's interruption sent SIGTERM to the verified guardian and the
    counted review ran on to its verdict. The handler raised InterruptedError, which selectors.select() catches and
    turns into an empty result, so a signal that arrived while the loop waited on the provider - nearly always - was
    lost. Every earlier test called execute() in-process and never signalled it.
    """

    def setUp(self):
        ModelTests.setUp(self)
        data = json.loads((self.stage/'input.json').read_text()); data['seconds'] = 60
        raw = json.dumps(data).encode(); (self.stage/'input.json').write_bytes(raw)
        self.request = dict(self.request, input_sha256=hashlib.sha256(raw).hexdigest())

    def tearDown(self):
        ModelTests.tearDown(self)

    def test_a_termination_signal_ends_a_running_call_and_removes_its_provider(self):
        # One event, then silence: the guardian then waits in streams.select(), where the signal used to be lost.
        provider = [sys.executable, '-u', '-c', 'import json,time\n'
                    'print(json.dumps({"type":"thread.started","thread_id":"synthetic"}),flush=True)\ntime.sleep(60)', '-']
        events = self.stage/'events.jsonl'
        with subprocess.Popen([sys.executable, '-B', '-c', GUARDIAN, str(self.root), self.scope.expected,
                               json.dumps(provider)], cwd=Path(__file__).resolve().parents[1],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True) as guardian:
            try:
                guardian.stdin.write(json.dumps(self.request).encode()); guardian.stdin.close()
                deadline = time.monotonic() + 20
                while not (events.is_file() and events.stat().st_size):
                    self.assertIsNone(guardian.poll(), guardian.stderr.read() if guardian.poll() is not None else '')
                    self.assertLess(time.monotonic(), deadline); time.sleep(.05)
                time.sleep(.5)
                sent = time.monotonic(); os.kill(guardian.pid, signal.SIGTERM)
                guardian.wait(timeout=10)
                ended = time.monotonic() - sent
                out, err = guardian.stdout.read(), guardian.stderr.read()
            finally:
                if guardian.poll() is None:
                    guardian.kill(); guardian.wait()
                if (self.stage/'launch.json').is_file():
                    try:
                        os.killpg(json.loads((self.stage/'launch.json').read_text())['provider_pid'], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        self.assertEqual(guardian.returncode, 0, err)
        result = json.loads(out)
        self.assertEqual((result['completed'], result['reason'], result['process_group_removed']),
                         (False, 'goal call signal', True))
        self.assertEqual(json.loads((self.stage/'result.json').read_text()), result)
        self.assertLess(ended, 5)
        launch = json.loads((self.stage/'launch.json').read_text())
        self.assertNotEqual(subprocess.run(['ps', '-p', str(launch['provider_pid'])], capture_output=True).returncode, 0)
        # Counted once and never refunded: the interrupted call stays reserved and started.
        self.assertEqual(self.scope.inspect()['started'], [self.nonce])


if __name__ == '__main__':
    unittest.main()
