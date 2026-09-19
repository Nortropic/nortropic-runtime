"""First accepted-task slice. Engine history owns attempts, results and waiting."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .activities import execute_codex


@workflow.defn
class DevelopmentTask:
    def __init__(self):
        self.phase = 'accepted'
        self.attempts = 0
        self.results = []
        self.waiting_reason = None
        self.retry_request = None

    @workflow.signal
    def retry_after_diagnosis(self, request: dict):
        if (self.phase == 'waiting_diagnosis' and request.get('expected_attempt') == self.attempts
                and isinstance(request.get('reason'), str) and request['reason'].strip()):
            self.retry_request = request

    @workflow.run
    async def run(self, task: dict) -> dict:
        while True:
            self.attempts += 1
            self.phase = 'running_codex'
            self.waiting_reason = None
            request = {'task_id': task['id'], 'number': self.attempts,
                       'prompt': task['steps'][0]['prompt'], 'seconds': task['attempt_seconds']}
            if self.attempts > 1:
                request['change_reason'] = self.retry_request['reason']
            self.retry_request = None
            try:
                result = await workflow.execute_activity(execute_codex, request,
                    start_to_close_timeout=timedelta(seconds=task['attempt_seconds'] + 150),
                    retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError as error:
                result = {'provider_completed': False, 'reason': str(error),
                          'attempt': self.attempts, 'requires_process_inspection': True}
            self.results.append(result)
            if not result.get('provider_completed') or not result.get('phase_acceptance_passed'):
                self.phase = 'waiting_diagnosis'
                self.waiting_reason = 'Phase incomplete or failed; preserved evidence, no automatic repetition'
                await workflow.wait_condition(lambda: self.retry_request is not None)
            else:
                self.phase = 'waiting_access'
                self.waiting_reason = task['steps'][1]['waiting_reason']
                # Deliberately no unverified Claude path in this bounded delivery.
                await workflow.wait_condition(lambda: False)
        return self.state()

    @workflow.query
    def state(self) -> dict:
        return {'phase': self.phase, 'attempts': self.attempts,
                'results': self.results, 'waiting_reason': self.waiting_reason}
