"""Isolated fake-provider process tests, explicitly not application evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime import development_model as model, development_host as host
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

    def test_agent_claim_of_quota_is_not_provider_authority(self):
        events = self.events(); events[1]['item']['text'] = '{"reason":"quota usage limit"}'
        self.assertTrue(self.run_fixture(events)['completed'])
        self.assertEqual(self.scope.inspect()['control'], 'active')


if __name__ == '__main__':
    unittest.main()
