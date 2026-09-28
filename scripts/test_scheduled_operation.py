"""Release binding and native schedule definition, isolated fixtures only."""
import copy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from temporalio.service import RPCError, RPCStatusCode
from runtime.scheduled_operation import operation
from runtime.operation_schedule import definition
from runtime.operation_schedule import execution_status, operate


class ScheduledOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = {'directory': str(self.home), 'config_sha256': 'a' * 64, 'files': {},
            'scheduled_operations': {'accepted-case': {'input': 'operations/accepted-case.json', 'interval_seconds': 300}}}
        for name in ('operations/accepted-case.json', 'office/tools/driftoperation.py'):
            p = self.home / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{}')
            self.config['files'][name] = sha256(p.read_bytes()).hexdigest()
        self.request = {'operation': 'accepted-case', 'config_sha256': 'a' * 64}

    def test_exact_binding_and_paused_bounded_definition(self):
        self.assertEqual(operation(self.config, self.request)[0], self.home / 'operations/accepted-case.json')
        schedule = definition(self.config, 'accepted-case')
        self.assertTrue(schedule.state.paused)
        self.assertEqual(schedule.action.task_queue, 'office-operations')
        self.assertEqual(schedule.action.retry_policy.maximum_attempts, 1)
        self.assertEqual(schedule.policy.catchup_window.total_seconds(), 60)

    def test_unknown_id_release_tamper_and_input_refused(self):
        for request in ({**self.request, 'operation': 'other'}, {**self.request, 'config_sha256': 'b' * 64},
                        {**self.request, 'path': '/tmp/command'}):
            with self.assertRaises(ValueError): operation(self.config, request)
        (self.home / 'office/tools/driftoperation.py').write_text('changed')
        with self.assertRaises(ValueError): operation(self.config, self.request)

    def test_no_arbitrary_path_interval_or_symlink(self):
        for change in ({'input': '../outside.json'}, {'interval_seconds': 1}, {'interval_seconds': True}):
            config = copy.deepcopy(self.config); config['scheduled_operations']['accepted-case'].update(change)
            with self.assertRaises(ValueError): operation(config, self.request)
        path = self.home / 'operations/accepted-case.json'; path.unlink(); path.symlink_to(self.home / 'office/tools/driftoperation.py')
        with self.assertRaises(ValueError): operation(self.config, self.request)


class ExecutionObservationTests(unittest.IsolatedAsyncioTestCase):
    def observed(self, count=1):
        now = datetime.now(timezone.utc)
        return NS(info=NS(recent_actions=[NS(action=NS(workflow_id='work-' + str(i),
            first_execution_run_id='run-' + str(i)), scheduled_at=now, started_at=now)
            for i in range(count)]))

    async def test_missing_history_timeout_and_later_success_are_distinct(self):
        missing = NS(describe=AsyncMock(side_effect=RPCError('expired', RPCStatusCode.NOT_FOUND, b'')))
        slow = NS(describe=AsyncMock(return_value=NS(status=NS(name='COMPLETED'))),
                  result=AsyncMock(side_effect=TimeoutError()))
        healthy = NS(describe=AsyncMock(return_value=NS(status=NS(name='COMPLETED'))),
                     result=AsyncMock(return_value={'result': {'completed': True}}))
        client = NS(get_workflow_handle=Mock(side_effect=[missing, slow, healthy]))
        rows = await execution_status(client, self.observed(3))
        self.assertEqual(rows[0]['status'], 'unavailable')
        self.assertEqual(rows[0]['observation_error'], 'RPCError')
        self.assertIsNone(rows[0]['business_completed'])
        self.assertEqual(rows[1]['status'], 'COMPLETED')
        self.assertEqual(rows[1]['observation_error'], 'TimeoutError')
        self.assertIsNone(rows[1]['business_completed'])
        self.assertTrue(rows[2]['business_completed'])

    async def test_stop_retains_successful_native_mutation_when_history_expired(self):
        description = self.observed()
        description.schedule = NS(state=NS(paused=False, note=''))
        description.info.num_actions = 1
        description.info.num_actions_missed_catchup_window = 0
        description.info.num_actions_skipped_overlap = 0
        description.info.running_actions = []
        description.info.next_action_times = []
        async def pause(note):
            description.schedule.state.paused = True
            description.schedule.state.note = note
        schedule = NS(describe=AsyncMock(return_value=description), pause=AsyncMock(side_effect=pause))
        expired = NS(describe=AsyncMock(side_effect=RPCError('expired', RPCStatusCode.NOT_FOUND, b'')))
        client = NS(get_schedule_handle=Mock(return_value=schedule), get_workflow_handle=Mock(return_value=expired))
        service = AsyncMock(); service.__aenter__.return_value = client
        with patch('runtime.operation_schedule.require_active_code', return_value={'config_sha256': 'a'*64}), \
             patch('runtime.operation_schedule.definition'), patch('runtime.operation_schedule.validate', new=AsyncMock()), \
             patch('runtime.operation_schedule.SharedService', return_value=service):
            receipt = await operate('stop', 'accepted-case')
        schedule.pause.assert_awaited_once()
        self.assertTrue(receipt['paused'])
        self.assertTrue(receipt['note'].startswith('STOPPED'))
        self.assertEqual(receipt['recent_executions'][0]['status'], 'unavailable')


if __name__ == '__main__': unittest.main()
