"""One deliberately small workflow, using engine-owned history and signals."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import record_effect


@workflow.defn
class ContinuityProbe:
    def __init__(self):
        self.phase = 'starting'
        self.executions = 0
        self.continuation_requested = False

    @workflow.run
    async def run(self) -> dict:
        self.executions += 1
        await workflow.execute_activity(record_effect, 'first',
                                        start_to_close_timeout=timedelta(seconds=5),
                                        retry_policy=RetryPolicy(maximum_attempts=1))
        self.phase = 'waiting'
        await workflow.wait_condition(lambda: self.continuation_requested)
        self.executions += 1
        await workflow.execute_activity(record_effect, 'second',
                                        start_to_close_timeout=timedelta(seconds=5),
                                        retry_policy=RetryPolicy(maximum_attempts=1))
        self.phase = 'done'
        return self.state()

    @workflow.signal
    def continue_work(self):
        self.continuation_requested = True

    @workflow.query
    def state(self) -> dict:
        return {'phase': self.phase, 'executions': self.executions,
                'continuation_requested': self.continuation_requested}
