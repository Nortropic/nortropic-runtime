"""A daemon start must not depend on executions the engine removes by retention, and missing evidence is never a pass.

Synthetic histories and a stand-in client; no engine. Explicitly NOT application evidence.
"""
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from temporalio.service import RPCError, RPCStatusCode

from runtime import daemon


def history(run_id, phase='completed', kind='DevelopmentTask', closing='workflowExecutionCompletedEventAttributes', name=None):
    result = base64.b64encode(json.dumps({'phase': phase, 'integration': {'merged': True}}).encode()).decode()
    return {'events': [{'eventId': '1', 'workflowExecutionStartedEventAttributes': {'workflowId': name, 'originalExecutionRunId': run_id, 'workflowType': {'name': kind}}},
                       {'eventId': '2', closing: {'result': {'payloads': [{'data': result}]}}}]}


class Client:
    def __init__(self, answers): self.answers = answers; self.asked = []
    def get_workflow_handle(self, name):
        self.asked.append(name); answer = self.answers[name]
        return SimpleNamespace(query=AsyncMock(side_effect=answer if isinstance(answer, Exception) else None, return_value=answer))


GONE = RPCError('workflow not found', RPCStatusCode.NOT_FOUND, b'')
LIVE = {name: {'phase': 'completed'} for name in daemon.HISTORICAL}


class DeliveredHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.release = Path(self.temp.name).resolve(); (self.release/'history').mkdir()
        self.config = {'directory': str(self.release), 'files': {}, 'historical_archives': {}}
        for number, name in enumerate(daemon.HISTORICAL): self.bind(name, 'run-%d' % number)

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, name, run_id, content=None, bound_run=None):
        raw = json.dumps(content if content is not None else history(run_id, name=name)).encode(); relative = 'history/' + name + '.json'
        (self.release/relative).write_bytes(raw); digest = hashlib.sha256(raw).hexdigest()
        self.config['files'][relative] = digest
        self.config['historical_archives'][name] = {'file': relative, 'run_id': bound_run or run_id, 'sha256': digest}

    def run_check(self, answers, config=None):
        client = Client(answers); return asyncio.run(daemon.delivered_histories(client, config or self.config)), client

    def test_the_engine_is_asked_first_and_a_live_completed_delivery_needs_no_archive(self):
        observed, client = self.run_check(LIVE, {'directory': str(self.release), 'files': {}})       # nothing bound at all
        self.assertEqual(observed, {name: {'source': 'engine'} for name in daemon.HISTORICAL}); self.assertEqual(client.asked, list(daemon.HISTORICAL))
        for phase in ('waiting_diagnosis', None):
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, 'unavailable or changed: office-assignment-core-1'):
                self.run_check({**LIVE, 'office-assignment-core-1': {'phase': phase}})

    def test_an_execution_removed_by_retention_is_evidenced_only_by_the_bound_verified_archive(self):
        observed, _ = self.run_check({**LIVE, 'office-result-1': GONE})
        self.assertEqual(observed['office-result-1'], {'source': 'archive bound by the release', 'run_id': 'run-0',
                                                       'sha256': self.config['historical_archives']['office-result-1']['sha256']})
        self.assertEqual(observed['office-owner-view-1'], {'source': 'engine'})
        observed, _ = self.run_check({name: GONE for name in daemon.HISTORICAL})                     # all three expired: still startable
        self.assertEqual({v['source'] for v in observed.values()}, {'archive bound by the release'})

    def test_missing_or_wrong_evidence_is_never_a_pass(self):
        gone = {**LIVE, 'office-result-1': GONE}; good = copy.deepcopy(self.config)
        def changed(mutate):
            config = copy.deepcopy(good); mutate(config); return config
        bound = lambda c: c['historical_archives']['office-result-1']
        cases = {'no archives bound': lambda c: c.pop('historical_archives'), 'this name not bound': lambda c: c['historical_archives'].pop('office-result-1'),
                 'extra key': lambda c: bound(c).update(note='x'), 'missing key': lambda c: bound(c).pop('run_id'), 'non-string': lambda c: bound(c).update(run_id=7),
                 'outside history/': lambda c: bound(c).update(file='runtime/daemon.py'), 'escaping': lambda c: bound(c).update(file='history/../x.json'),
                 'not in the release file map': lambda c: c['files'].pop('history/office-result-1.json'),
                 'file map names other bytes': lambda c: c['files'].update({'history/office-result-1.json': 'f'*64})}
        for name, mutate in cases.items():
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'no verified archive is bound: office-result-1'):
                self.run_check(gone, changed(mutate))
        # The same verified bytes, correctly listed and hashed, but NOT under history/: only the location refuses.
        genuine = (self.release/'history/office-result-1.json').read_bytes(); digest = hashlib.sha256(genuine).hexdigest()
        for elsewhere in ('runtime/office-result-1.json', 'history/deep/office-result-1.json', 'office-result-1.json'):
            (self.release/elsewhere).parent.mkdir(parents=True, exist_ok=True); (self.release/elsewhere).write_bytes(genuine)
            def moved(c, elsewhere=elsewhere): bound(c).update(file=elsewhere); c['files'][elsewhere] = digest
            with self.subTest(elsewhere=elsewhere), self.assertRaisesRegex(ValueError, 'no verified archive is bound: office-result-1'):
                self.run_check(gone, changed(moved))
        (self.release/'history/office-result-1.json').write_bytes(b'{"events": []}')
        with self.assertRaisesRegex(ValueError, 'Bound archive of delivered native history changed'): self.run_check(gone)
        # A link to IDENTICAL bytes: only the link itself refuses.
        (self.release/'history/office-result-1.json').unlink(); (self.release/'history/office-result-1.json').symlink_to(self.release/'runtime/office-result-1.json')
        self.assertEqual(hashlib.sha256((self.release/'history/office-result-1.json').read_bytes()).hexdigest(), digest)
        with self.assertRaisesRegex(ValueError, 'Bound archive of delivered native history changed'): self.run_check(gone)
        (self.release/'history/office-result-1.json').unlink()
        mine = 'office-result-1'
        for name, content, run in (('another run', history('someone-else', name=mine), 'run-0'), ('not completed', history('run-0', phase='waiting_diagnosis', name=mine), None),
                                   ('another workflow type', history('run-0', kind='PrivateAssessment', name=mine), None),
                                   ('the archive of ANOTHER execution bound under this name', history('run-0', name='office-owner-view-1'), None)):
            self.bind('office-result-1', 'run-0', content, bound_run=run)
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'does not show that run completing'): self.run_check(gone)
        for name, content in (('terminated, not completed', history('run-0', closing='workflowExecutionTerminatedEventAttributes', name=mine)), ('no events', {'events': []}), ('not a history', ['x'])):
            self.bind('office-result-1', 'run-0', content)
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'does not show a completed delivery'): self.run_check(gone)

    def test_any_other_engine_failure_is_not_mistaken_for_retention(self):
        for status in (RPCStatusCode.UNAVAILABLE, RPCStatusCode.PERMISSION_DENIED):
            with self.subTest(status=status), self.assertRaises(RPCError): self.run_check({**LIVE, 'office-result-1': RPCError('x', status, b'')})
        with self.assertRaises(asyncio.TimeoutError): self.run_check({**LIVE, 'office-result-1': asyncio.TimeoutError()})

    def test_the_real_daemon_start_uses_exactly_this_requirement_before_it_writes_a_receipt(self):
        """Runs the REAL daemon main() up to the requirement, with the engine, the worker and the release lookup substituted."""
        home = self.release/'host'; (home/'.runtime').mkdir(parents=True); database = home/'.runtime/runtime.sqlite'
        import sqlite3
        with sqlite3.connect(database) as connection: connection.execute('create table t (x)')
        config = {**self.config, 'config_sha256': 'c'*64, 'database': str(database), 'runtime_revision': 'r'*40, 'office_revision': 'o'*40}
        identity = {k: config[k] for k in ('config_sha256', 'database', 'runtime_revision', 'office_revision')}
        class Engine:
            proc = SimpleNamespace(pid=1, poll=lambda: None)
            def __init__(self, *args): pass
            async def __aenter__(self): return SimpleNamespace(start_workflow=AsyncMock(), get_workflow_handle=lambda name: SimpleNamespace(query=AsyncMock(return_value=identity)))
            async def __aexit__(self, *args): return None
        required = AsyncMock(side_effect=ValueError('requirement reached'))
        worker = SimpleNamespace(pid=2, poll=lambda: None)
        with patch.object(daemon, 'require_active_code', return_value=config), patch.object(daemon, 'ROOT', home), patch.object(daemon, 'LocalService', Engine), \
             patch.object(daemon, 'check_unfinished_writers'), patch.object(daemon, 'check_private_processes'), patch.object(daemon.subprocess, 'Popen', return_value=worker), \
             patch.object(daemon, 'stop_group', return_value=True), patch.object(daemon, 'delivered_histories', required):
            with self.assertRaisesRegex(ValueError, 'requirement reached'): asyncio.run(daemon.main())
        required.assert_awaited_once(); self.assertIs(required.await_args.args[1], config)
        self.assertFalse((home/'.runtime/ap10/service.json').exists())                 # no receipt without the requirement


if __name__ == '__main__':
    unittest.main()
