"""Finite native parent; waiting consumes no activity slot or model call.

This runs only the two work identities in the accepted scope. It does not select
future goals, alter limits or replace DevelopmentTask's review/recovery logic.
"""
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .development_activity import development_step
    from .workflow import DevelopmentTask


@workflow.defn
class FiniteDevelopment:
    def __init__(self):
        self.phase = 'accepted'
        self.sequence = 0
        self.children = []
        self.results = []
        self.reason = None
        self.continuation = None
        self.continuations = []

    @workflow.signal
    def continue_after_diagnosis(self, reason: str):
        if self.phase == 'waiting_host_diagnosis' and isinstance(reason, str) and reason.strip():
            self.continuation = reason

    async def step(self, operation, **fields):
        self.sequence += 1
        request = {'contract_sha256': self.expected, 'operation': operation,
                   'key': 'step-' + str(self.sequence), **fields}
        while True:
            try:
                result = await workflow.execute_activity(development_step, request,
                    start_to_close_timeout=timedelta(seconds=1520),
                    retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError as error:
                self.phase = 'waiting_host_diagnosis'; self.reason = str(error)
                await workflow.wait_condition(lambda: self.continuation is not None)
                self.continuations.append({'sequence': self.sequence, 'reason': self.continuation})
                self.continuation = None
                # Do not replay a consumed side effect. A fresh operation key
                # preserves all earlier reservations, artifacts and diagnosis.
                self.sequence += 1; request['key'] = 'step-' + str(self.sequence)
                continue
            if result.get('capacity_wait'):
                self.phase = 'waiting_capacity'; self.reason = result['reason']
                await workflow.sleep(30)
                continue
            if result.get('control_wait'):
                self.phase = 'waiting_control'; self.reason = result['control']
                if result['control'] in ('stopped', 'revoked'):
                    return result
                await workflow.sleep(5)
                continue
            return result

    @workflow.run
    async def run(self, expected: str) -> dict:
        self.expected = expected
        for work in ('reconciliation', 'handoff'):
            revision_request = None
            while True:
                self.phase = 'preparing_' + work
                draft = await self.step('propose', work=work, revision_request=revision_request)
                if draft.get('hold') or draft.get('control_wait'):
                    self.phase = 'insufficient'; self.reason = draft
                    return self.state()
                self.phase = 'reviewing_preparation'
                review = await self.step('review', draft=draft)
                if review.get('approved') is True:
                    break
                decision = review.get('decision', {})
                if decision.get('verdict') == 'rejected' and decision.get('blocking_findings'):
                    revision_request = {'draft': draft, 'review': review['review']}
                    continue
                self.phase = 'preparation_not_approved'; self.reason = review
                return self.state()
            self.phase = 'freezing_task'
            frozen = await self.step('freeze', draft=draft, review=review['review'])
            if 'task' not in frozen:
                self.phase = 'stopped'; self.reason = frozen
                return self.state()
            task = frozen['task']
            child = await workflow.start_child_workflow(DevelopmentTask.run, task,
                id=task['id'], task_queue='development',
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
            self.children.append(task['id'])
            while True:
                self.phase = 'following_' + work
                control = await self.step('control')
                if control['control'] in ('stopped', 'revoked'):
                    child.cancel()
                    self.phase = 'stopped'; self.reason = control['control']
                    return self.state()
                observed = await self.step('observe', task_id=task['id'])
                state = observed['child']
                if state['phase'] == 'completed':
                    self.results.append(await child)
                    break
                if state['phase'] in ('waiting_diagnosis', 'waiting_review'):
                    self.phase = 'diagnosing_' + work
                    recovery = await self.step('diagnose', task_id=task['id'])
                    if recovery.get('action') in ('repair', 'review_only'):
                        await child.signal(DevelopmentTask.continue_after_review, recovery['request'])
                    elif recovery.get('action') == 'retry':
                        await child.signal(DevelopmentTask.retry_after_diagnosis, recovery['request'])
                    elif recovery.get('control') in ('stopped', 'revoked'):
                        child.cancel(); self.phase = 'stopped'; return self.state()
                    else:
                        self.phase = 'waiting_host_diagnosis'; self.reason = recovery
                        await workflow.wait_condition(lambda: self.continuation is not None)
                        self.continuations.append({'child': task['id'], 'reason': self.continuation})
                        self.continuation = None
                if state['phase'] == 'waiting_publication_reconciliation':
                    # An uncertain remote mutation requires actual readback,
                    # never a model's permission to repeat it.
                    self.phase = 'waiting_host_diagnosis'; self.reason = state
                    await workflow.wait_condition(lambda: self.continuation is not None)
                    self.continuations.append({'child': task['id'], 'reason': self.continuation})
                    self.continuation = None
                await workflow.sleep(5)
        # Deliberately NOT completion from two child PASS results. The separate
        # overall G1–G10 review/closure is a subsequent native bounded step.
        self.phase = 'awaiting_whole_goal_review'
        return self.state()

    @workflow.query
    def state(self) -> dict:
        return {'phase': self.phase, 'sequence': self.sequence, 'children': self.children,
                'results': self.results, 'reason': self.reason,
                'continuations': self.continuations, 'whole_goal_complete': False}
