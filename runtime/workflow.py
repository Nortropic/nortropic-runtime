"""Native task sequencing. Engine history owns attempts, results and waiting."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .activities import execute_codex, review_candidate, publish_candidate
    from .integration import digest, require_gate, GateClosed


@workflow.defn
class DevelopmentTask:
    def __init__(self):
        self.phase = 'accepted'
        self.attempts = 0
        self.results = []
        self.waiting_reason = None
        self.retry_request = None
        self.review = None
        self.integration = None
        self.reconciliation = None

    @workflow.signal
    def retry_after_diagnosis(self, request: dict):
        if (self.phase == 'waiting_diagnosis' and request.get('expected_attempt') == self.attempts
                and isinstance(request.get('reason'), str) and request['reason'].strip()):
            self.retry_request = request

    @workflow.signal
    def reconcile_publication(self, request: dict):
        if (self.phase == 'waiting_publication_reconciliation' and self.results
                and request.get('candidate') == self.results[-1].get('candidate')
                and isinstance(request.get('reason'), str) and request['reason'].strip()):
            self.reconciliation = request

    @workflow.run
    async def run(self, task: dict) -> dict:
        completed = []
        for index, step in enumerate(task['steps']):
            if step['provider'] != 'codex' or step.get('waiting_reason'):
                self.phase = 'waiting_access'
                self.waiting_reason = step.get('waiting_reason', 'Provider is not yet qualified')
                # No unverified Claude path, purchase or repeated denied call.
                await workflow.wait_condition(lambda: False)
            while True:
                self.attempts += 1
                self.phase = 'running_codex'
                self.waiting_reason = None
                request = {'task_id': task['id'], 'number': self.attempts,
                           'prompt': step['prompt'], 'seconds': task['attempt_seconds']}
                if 'acceptance_sha256' in task: request['task_digest'] = digest(task)
                if self.retry_request:
                    request['change_reason'] = self.retry_request['reason']
                elif self.attempts > 1:
                    request['change_reason'] = 'Next accepted implementation step ' + str(index)
                self.retry_request = None
                try:
                    result = await workflow.execute_activity(execute_codex, request,
                        start_to_close_timeout=timedelta(seconds=task['attempt_seconds'] + 150),
                        retry_policy=RetryPolicy(maximum_attempts=1))
                except ActivityError as error:
                    result = {'provider_completed': False, 'reason': str(error),
                              'attempt': self.attempts, 'requires_process_inspection': True}
                self.results.append(result)
                if result.get('provider_completed') is True and result.get('phase_acceptance_passed') is True:
                    completed.append(index)
                    break
                self.phase = 'waiting_diagnosis'
                self.waiting_reason = 'Phase incomplete or failed; preserved evidence, no automatic repetition'
                await workflow.wait_condition(lambda: self.retry_request is not None)
        latest = self.results[-1]
        subject = {'task_id': task['id'], 'task_sha256': digest(task), 'base': task['base'],
                   'candidate': latest['candidate'], 'completed_steps': completed,
                   'acceptance_sha256': task['acceptance_sha256'],
                   'implementation_runs': [x['thread_id'] for x in self.results if x.get('thread_id')]}
        tests = {key: subject[key] for key in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
        tests.update(scope='whole_task', terminal_status='completed', passed=True,
                     source_evidence=latest['evidence'] + '/acceptance.json')
        request = {'task_id': task['id'], 'task_digest': digest(task), 'subject': subject,
                   'workspace_name': latest['workspace_name']}
        self.phase = 'reviewing'
        try:
            self.review = await workflow.execute_activity(review_candidate, request,
                start_to_close_timeout=timedelta(seconds=210), retry_policy=RetryPolicy(maximum_attempts=1))
        except ActivityError as error:
            self.review = {'terminal_status': 'incomplete', 'reason': str(error)}
        try:
            require_gate(task, subject, tests, self.review)
        except GateClosed as error:
            self.phase = 'waiting_review'
            self.waiting_reason = str(error)
            await workflow.wait_condition(lambda: False)
        publication = {**request, 'tests': tests, 'review': self.review,
                       'candidate_files_sha256': latest['candidate_files_sha256']}
        while True:
            self.phase = 'publishing'
            self.waiting_reason = None
            self.reconciliation = None
            try:
                self.integration = await workflow.execute_activity(publish_candidate, publication,
                    start_to_close_timeout=timedelta(seconds=150), retry_policy=RetryPolicy(maximum_attempts=1))
                break
            except ActivityError as error:
                self.phase = 'waiting_publication_reconciliation'
                self.waiting_reason = str(error)
                await workflow.wait_condition(lambda: self.reconciliation is not None)
        self.phase = 'completed'
        return self.state()

    @workflow.query
    def state(self) -> dict:
        result = {'phase': self.phase, 'attempts': self.attempts,
                  'results': self.results, 'waiting_reason': self.waiting_reason}
        if self.review is not None: result['review'] = self.review
        if self.integration is not None: result['integration'] = self.integration
        return result
