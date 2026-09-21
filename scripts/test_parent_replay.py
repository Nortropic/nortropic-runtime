"""The finite parent's wait cycles must stay replay-compatible with recorded native histories.

Fixture: a REAL 44-event native history recorded on a throwaway engine with the then-active parent code
(five second timers) and a stand-in host step: control wait, interactive wait, control wait, stop.
Offline: the replayer needs no engine. Explicitly NOT application evidence.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner

from runtime import development_workflow
from runtime.development_workflow import FiniteDevelopment
from runtime.workflow import DevelopmentTask

FIXTURE = Path('evidence/ap11-parent-history/wait-cycles-recorded-5s.json')


class ParentReplayTest(unittest.IsolatedAsyncioTestCase):
    def history(self):
        return WorkflowHistory.from_json('office-ap11', FIXTURE.read_text())

    async def test_recorded_wait_cycles_replay_in_the_sandboxed_production_form(self):
        self.assertEqual(len(self.history().events), 44)
        result = await Replayer(workflows=[FiniteDevelopment, DevelopmentTask]).replay_workflow(self.history(), raise_on_replay_failure=False)
        self.assertIsNone(result.replay_failure)

    async def test_the_instrument_detects_a_wait_that_records_no_timer(self):
        async def no_timer(self): return None
        with patch.object(FiniteDevelopment, 'host_wait', no_timer):
            result = await Replayer(workflows=[FiniteDevelopment, DevelopmentTask], workflow_runner=UnsandboxedWorkflowRunner()) \
                .replay_workflow(self.history(), raise_on_replay_failure=False)
        self.assertIsNotNone(result.replay_failure)
        self.assertIn('ondeterminism', repr(result.replay_failure))

    def test_a_pause_is_waited_for_not_polled(self):
        self.assertEqual(development_workflow.POLL_SECONDS, 30)
        self.assertGreaterEqual(development_workflow.HOST_WAIT_SECONDS, 6*3600)
        per_day = 24*3600//development_workflow.HOST_WAIT_SECONDS*11          # one fallback cycle is about eleven events
        self.assertLessEqual(per_day, 44)
        # Measured replay speed: about 25 000 events fit in the ten second workflow task timeout with margin.
        self.assertLess(365*per_day, 25000)                                   # a year of an untouched pause stays restart-safe
        from runtime import service
        limit = int(dict(v.split('=') for v in service.HISTORY_LIMITS[1::2])['limit.historyCount.error'])
        self.assertLess(365*per_day, limit)                                   # a year stays below the explicit engine margin


if __name__ == '__main__':
    unittest.main()
