from datetime import datetime, timedelta, timezone
import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch
from runtime.development_capacity import admission, inspect_capacity


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 21, 6, 50, tzinfo=timezone.utc)
        self.status = {'obligation': 'office-python-temporal', 'paused': False,
                       'observed_at': self.now.isoformat(), 'running': [],
                       'next_action_times': [(self.now+timedelta(minutes=10)).isoformat()]}

    def test_full_activity_not_only_model_must_fit(self):
        self.assertTrue(admission(self.status, self.now, 480)['available'])
        self.assertFalse(admission(self.status, self.now, 540)['available'])
        self.assertFalse(admission(self.status, self.now, 630)['available'])

    def test_running_watch_wins_even_when_paused(self):
        self.status.update(paused=True, running=[{'workflow_id': 'fixture'}])
        self.assertFalse(admission(self.status, self.now, 10)['available'])
        self.status['running'] = []
        self.assertTrue(admission(self.status, self.now, 10)['available'])

    def test_unavailable_stale_or_malformed_schedule_is_not_idle(self):
        for changes in ({'next_action_times': []}, {'next_action_times': ['bad']},
                        {'next_action_times': [self.now.isoformat()]},
                        {'observed_at': (self.now-timedelta(seconds=6)).isoformat()},
                        {'observed_at': self.now.replace(tzinfo=None).isoformat()},
                        {'running': None}, {'paused': 'false'}):
            with self.subTest(changes=changes):
                self.assertFalse(admission({**self.status, **changes}, self.now, 10)['available'])

    def test_no_side_effects_and_no_zero_unbounded_activity(self):
        before = repr(self.status)
        self.assertLessEqual(admission(self.status, self.now, 630)['wait_seconds'], 30)
        self.assertEqual(repr(self.status), before)
        for value in (0, True, 3901):
            with self.assertRaises(ValueError):
                admission(self.status, self.now, value)

    def test_entire_native_probe_has_one_second_budget(self):
        config = {key: 'fixture' for key in
                  ('config_sha256', 'database', 'runtime_revision', 'office_revision')}
        receipt = {'native_identity': config, 'identity_workflow': 'fixture'}
        async def hung(*args, **kwargs):
            await asyncio.sleep(60)
        start = time.monotonic()
        with patch('runtime.development_capacity.require_active_code', return_value=config), \
             patch('runtime.development_capacity.read_regular', return_value=json.dumps(receipt).encode()), \
             patch('runtime.development_capacity.Client.connect', side_effect=hung):
            with self.assertRaises(TimeoutError):
                asyncio.run(inspect_capacity(100))
        self.assertLess(time.monotonic()-start, 2)


if __name__ == '__main__':
    unittest.main()
