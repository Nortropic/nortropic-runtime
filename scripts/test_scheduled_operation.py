"""Release binding and native schedule definition, isolated fixtures only."""
import copy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from runtime.scheduled_operation import operation
from runtime.operation_schedule import definition


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
        self.assertEqual(schedule.action.task_queue, 'development')
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


if __name__ == '__main__': unittest.main()
