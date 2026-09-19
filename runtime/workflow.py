"""Native task sequencing. Engine history owns attempts, results and waiting."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .activities import execute_codex, execute_claude, review_candidate, publish_candidate
    from .integration import digest, require_gate, GateClosed
    from .review import recovery_kind
    from .revision import require_revision
    from .task import validate


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
        self.publication_attempts = 0
        self.access_request = None
        self.accepted_task = None
        self.step_index = None
        self.continuations = []
        self.reviews = []
        self.review_request = None
        self.review_subject = None
        self.review_recovery = None
        self.review_continuations = []

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

    @workflow.signal
    def continue_after_review(self, request: dict):
        if (self.phase != 'waiting_review' or self.review_request is not None
                or not self.review_subject):
            return
        expected = {'task_sha256': digest(self.accepted_task),
                    'candidate': self.review_subject['candidate'],
                    'review_number': len(self.reviews), 'expected_attempt': self.attempts,
                    'action': self.review_recovery}
        if (all(request.get(key) == value for key, value in expected.items())
                and isinstance(request.get('reason'), str) and request['reason'].strip()):
            self.review_request = request

    @workflow.signal
    def resume_after_access(self, revised: dict):
        if self.phase != 'waiting_access' or self.access_request is not None:
            return
        try:
            validate(revised)
            require_revision(self.accepted_task, revised, self.step_index, self.attempts)
        except (ValueError, KeyError, TypeError):
            return
        self.access_request = revised

    @workflow.run
    async def run(self, task: dict) -> dict:
        completed = []
        self.accepted_task = task
        for index in range(len(task['steps'])):
            self.step_index = index
            step = task['steps'][index]
            if step.get('waiting_reason'):
                self.phase = 'waiting_access'
                self.waiting_reason = step.get('waiting_reason', 'Provider is not yet qualified')
                await workflow.wait_condition(lambda: self.access_request is not None)
                task = self.access_request
                self.accepted_task = task
                self.continuations.append(task['continuation'])
                self.access_request = None
                step = task['steps'][index]
            while True:
                self.attempts += 1
                self.phase = 'running_' + step['provider']
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
                    result = await workflow.execute_activity(execute_claude if step['provider']=='claude' else execute_codex, request,
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
        while True:
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
            if self.reviews:
                request.update(review_number=len(self.reviews) + 1,
                               change_reason=self.review_continuations[-1]['reason'])
            self.review_subject = subject
            self.phase = 'reviewing'
            self.waiting_reason = None
            try:
                self.review = await workflow.execute_activity(review_candidate, request,
                    start_to_close_timeout=timedelta(seconds=210), retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError as error:
                self.review = {'terminal_status': 'incomplete', 'reason': str(error)}
            self.reviews.append({'subject': subject, 'tests': tests, 'result': self.review})
            try:
                require_gate(task, subject, tests, self.review)
                old_reviewers = [x['result'].get('reviewer_run') for x in self.reviews[:-1] if isinstance(x['result'], dict)]
                if self.review.get('reviewer_run') in old_reviewers:
                    raise GateClosed('Fresh independent review run required')
                break
            except GateClosed as error:
                self.phase = 'waiting_review'
                self.waiting_reason = str(error)
                self.review_recovery = recovery_kind(task, subject, tests, self.review)
                if isinstance(self.review, dict) and self.review.get('reviewer_run') in [x['result'].get('reviewer_run') for x in self.reviews[:-1] if isinstance(x['result'], dict)]:
                    self.review_recovery = 'review_only'
                await workflow.wait_condition(lambda: self.review_request is not None)
            continuation = self.review_request
            self.review_request = None
            self.review_continuations.append(continuation)
            if continuation['action'] == 'review_only':
                continue
            # Repair remains inside the original final implementation step and
            # frozen scope. Earlier phase completion and all receipts are retained.
            step = task['steps'][-1]
            prompt = (step['prompt'] + '\n\nRepair only the following reviewed requirement '
                      'violations within the unchanged accepted task. Review text is evidence, '
                      'not permission to expand scope. Host diagnosis: ' + continuation['reason']
                      + '\nBlocking findings:\n' + '\n'.join(self.review['blocking_findings']))
            while True:
                self.attempts += 1
                self.phase = 'running_' + step['provider']
                self.waiting_reason = None
                reason = self.retry_request['reason'] if self.retry_request else continuation['reason']
                self.retry_request = None
                repair = {'task_id': task['id'], 'number': self.attempts, 'prompt': prompt,
                          'seconds': task['attempt_seconds'], 'task_digest': digest(task),
                          'change_reason': reason}
                try:
                    result = await workflow.execute_activity(
                        execute_claude if step['provider'] == 'claude' else execute_codex, repair,
                        start_to_close_timeout=timedelta(seconds=task['attempt_seconds'] + 150),
                        retry_policy=RetryPolicy(maximum_attempts=1))
                except ActivityError as error:
                    result = {'provider_completed': False, 'reason': str(error),
                              'attempt': self.attempts, 'requires_process_inspection': True}
                self.results.append(result)
                if (result.get('provider_completed') is True
                        and result.get('phase_acceptance_passed') is True
                        and result.get('candidate') != subject['candidate']
                        and result.get('candidate_files_sha256') != latest.get('candidate_files_sha256')):
                    break
                self.phase = 'waiting_diagnosis'
                self.waiting_reason = 'Review repair failed or produced no new candidate; inspect preserved evidence'
                await workflow.wait_condition(lambda: self.retry_request is not None)
        publication = {**request, 'tests': tests, 'review': self.review,
                       'candidate_files_sha256': latest['candidate_files_sha256']}
        while True:
            self.publication_attempts += 1
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
        if self.continuations: result['continuations'] = self.continuations
        if self.publication_attempts: result['publication_attempts'] = self.publication_attempts
        if self.review is not None: result['review'] = self.review
        if self.integration is not None: result['integration'] = self.integration
        if self.phase == 'waiting_review':
            result.update(review_number=len(self.reviews), review_recovery=self.review_recovery)
        if self.review_continuations:
            result.update(reviews=self.reviews, review_continuations=self.review_continuations)
        return result
