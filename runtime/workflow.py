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

    @workflow.run
    async def run(self, task: dict) -> dict:
        # This bounded delivery enables precisely one substantive Codex phase.
        self.attempts += 1
        self.phase = 'running_codex'
        try:
            result = await workflow.execute_activity(execute_codex, {
                'task_id': task['id'], 'number': self.attempts,
                'prompt': task['steps'][0]['prompt'], 'seconds': task['attempt_seconds']},
                start_to_close_timeout=timedelta(seconds=task['attempt_seconds'] + 150),
                retry_policy=RetryPolicy(maximum_attempts=1))
        except ActivityError as error:
            result = {'provider_completed': False, 'reason': str(error),
                      'attempt': self.attempts, 'requires_process_inspection': True}
        self.results.append(result)
        if not result.get('provider_completed') or not result.get('phase_acceptance_passed'):
            self.phase = 'waiting_diagnosis'
            self.waiting_reason = 'Phase incomplete or failed; preserved evidence, no automatic repetition'
        else:
            self.phase = 'waiting_access'
            self.waiting_reason = task['steps'][1]['waiting_reason']
        # No placeholder Claude adapter or approval signal silently bypasses access.
        # Next reviewed delivery will add continuation when access is available.
        await workflow.wait_condition(lambda: False)
        return self.state()

    @workflow.query
    def state(self) -> dict:
        return {'phase': self.phase, 'attempts': self.attempts,
                'results': self.results, 'waiting_reason': self.waiting_reason}
