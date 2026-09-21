"""Native private read/assessment chain. No development or publication shortcut."""
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import CancelledError, ActivityError


@workflow.defn
class PrivateAssessment:
    def __init__(self):
        self.current = {'phase':'starting'}

    @workflow.query
    def state(self) -> dict:
        return self.current

    @workflow.run
    async def run(self, request: dict) -> dict:
        info = workflow.info()
        request = {**request, 'run_id':info.run_id, 'workflow_id':info.workflow_id,
                   'started_at':info.start_time.isoformat()}
        outcomes = {}
        for role, seconds in [('intake',90),('analysis',480),('review',240),('report',60)]:
            if role in ('analysis','review') and not outcomes.get('intake',{}).get('needs_model'):
                continue
            if role == 'review' and not outcomes.get('analysis',{}).get('completed'):
                continue
            self.current = {'phase':role,'run_id':info.run_id,'outcomes':outcomes}
            try:
                outcomes[role] = await workflow.execute_activity(
                    'private_stage', {**request,'role':role,'seconds':seconds,'outcomes':outcomes},
                    start_to_close_timeout=timedelta(seconds=seconds+10),
                    schedule_to_close_timeout=timedelta(seconds=seconds+15),
                    heartbeat_timeout=timedelta(seconds=10),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED)
            except CancelledError:
                raise
            except Exception as error:
                if isinstance(error,ActivityError) and isinstance(error.cause,CancelledError):raise
                # An unavailable stage is not a substantive positive result.
                outcomes[role] = {'completed':False,'reason':type(error).__name__}
        self.current = {'phase':'completed','run_id':info.run_id,'outcomes':outcomes,
                        'publication':False}
        return self.current
