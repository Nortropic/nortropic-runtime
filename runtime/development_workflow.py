"""Finite native parent; waiting consumes no activity slot or model call.

This runs only the two work identities in the accepted scope. It does not select
future goals, alter limits or replace DevelopmentTask's review/recovery logic.
"""
import asyncio
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .development_activity import development_step
    from .workflow import DevelopmentTask

# Every poll cycle costs about eleven history events (an activity, a timer and their
# workflow tasks); following a child costs more. Measured on the real waiting parent: a
# five second cycle reached 32 000 events in 4 h 20 min, the engine terminates an execution
# at its history count limit, and a full replay of that history took as long as the ten
# second workflow task timeout, so a restart could no longer be survived. A longer timer is
# replay-compatible: the recorded history replays unchanged under this value.
POLL_SECONDS = 30
# A pause, or a wait for the host's whole-goal evidence, can last days. It is therefore not
# polled: the parent waits for the host's wake signal, and a rare fallback timer keeps it
# live if a signal is ever lost. About 44 events per day instead of 32 000, plus about 12 per
# pause, resume or wake: from a history of N events, (25 000 - N) / 44 days of untouched pause
# before a cold restart stops being safe, more than a year from a small history. Not forever:
# continue-as-new would be the unbounded remedy and is deliberately not taken here. The same
# native command (a timer) is recorded, so earlier histories replay unchanged. Forward-only:
# a history in which this signal was processed no longer replays under earlier parent code.
HOST_WAIT_SECONDS = 6*3600
# The one accepted application. Named here rather than imported: this module is loaded inside the workflow
# sandbox, and the assessment module that owns the same name reaches host code that has no place there.
APPLICATION = 'office-ap11'


def key_prefix(identity):
    """The counted-step key prefix of a run identity: the original application keeps the build's 'step-', and
    every further assessment uses its own full identity, so a stage on disk says which run consumed it and no
    new identity needs a code change to get a namespace of its own."""
    return 'step-' if identity == APPLICATION else identity + '-step-'


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
        self.final = None
        self.wake = False

    @workflow.signal
    def host_state_changed(self):
        """The host changed control or preserved evidence: re-read now. Carries no data and starts nothing by itself."""
        self.wake = True

    async def host_wait(self):
        # The flag is cleared BEFORE the host step reads the state (see step), never here: a wake that
        # arrives while that step is in flight must end this wait at once, or a resume would be missed
        # until the fallback (measured in review with a slowed step).
        try:
            await workflow.wait_condition(lambda: self.wake, timeout=HOST_WAIT_SECONDS)
        except asyncio.TimeoutError:
            pass

    @workflow.signal
    def continue_after_diagnosis(self, reason: str):
        if self.phase == 'waiting_host_diagnosis' and isinstance(reason, str) and reason.strip():
            self.continuation = reason

    # The counted call stages live in ONE scope, keyed by this prefix and a sequence. A run that restarts the
    # sequence in a scope another run already used would collide on the first key that run consumed, and
    # prepare_call creates its stage with exist_ok=False - so the collision is not a refusal but a repeating
    # host-diagnosis loop that rebuilds the whole evidence package and records spurious operator answers into
    # the very evidence it is delivering. Every run identity therefore owns its own prefix.
    def key_prefix(self):
        return key_prefix(APPLICATION)

    async def step(self, operation, **fields):
        self.sequence += 1
        request = {'contract_sha256': self.expected, 'operation': operation,
                   'key': self.key_prefix() + str(self.sequence), **fields}
        while True:
            self.wake = False
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
                self.sequence += 1; request['key'] = self.key_prefix() + str(self.sequence)
                continue
            if result.get('capacity_wait'):
                self.phase = 'waiting_capacity'; self.reason = result['reason']
                await workflow.sleep(30)
                continue
            if result.get('interactive_wait'):
                self.phase = 'waiting_interactive_session_end'
                await workflow.sleep(POLL_SECONDS)
                continue
            if result.get('proof_wait'):
                self.phase = 'waiting_whole_goal_evidence'; self.reason = result['reason']
                await self.host_wait()
                continue
            if result.get('control_wait'):
                self.phase = 'waiting_control'; self.reason = result['control']
                if result['control'] in ('stopped', 'revoked'):
                    return result
                await self.host_wait()
                continue
            return result

    @workflow.run
    async def run(self, expected: str) -> dict:
        self.expected = expected
        # A real interactive driver authors A, then actually exits. Temporal
        # is already waiting; no observer instruction starts the continuation.
        self.phase = 'waiting_interactive_session_end'
        initial = await self.step('interactive')
        if initial.get('control_wait'):
            self.phase = 'stopped'; self.reason = initial; return self.state()
        for work in ('reconciliation', 'handoff'):
            revision_request = None
            while True:
                self.phase = 'preparing_' + work
                if work == 'reconciliation' and revision_request is None:
                    draft = initial
                else:
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
                await workflow.sleep(POLL_SECONDS)
        self.phase = 'awaiting_whole_goal_review'
        self.final = await self.step('final-review')
        self.phase = 'completed' if self.final.get('whole_goal_complete') is True else 'whole_goal_not_approved'
        return self.state()

    @workflow.query
    def state(self) -> dict:
        return {'phase': self.phase, 'sequence': self.sequence, 'children': self.children,
                'results': self.results, 'reason': self.reason,
                'continuations': self.continuations, 'final': self.final,
                'whole_goal_complete': bool(self.final and self.final.get('whole_goal_complete') is True)}

@workflow.defn
class FiniteAssessment(FiniteDevelopment):
    """A further whole-goal assessment of the SAME already delivered application.

    It reuses the counted step machinery, the signals and the state query of the build workflow, and nothing
    else of it, but NOT its key namespace: it shares the build's scope, whose earlier keys already exist. It never
    runs the interactive session, never prepares or reviews a draft, never freezes a task,
    never starts a child and never publishes: the delivery it assesses already exists and re-driving it is
    exactly what this entry is for avoiding. The preserved delivery is verified BEFORE the counted review, so a
    scope without both integrations refuses without spending a model call.
    """

    # The run's own identity as the engine holds it, so a stage on disk says which run consumed it. For the second
    # assessment this is exactly the prefix it ran under, so its recorded history replays unchanged. identifier()
    # allows 80 characters of [a-z0-9-]; an assessment identity plus '-step-' and a sequence stays well inside that.
    def key_prefix(self):
        return key_prefix(workflow.info().workflow_id)

    @workflow.run
    async def run(self, expected: str) -> dict:
        self.expected = expected
        self.phase = 'verifying_preserved_delivery'
        delivered = await self.step('preserved-delivery')
        if delivered.get('control_wait'):
            self.phase = 'stopped'; self.reason = delivered
            return self.state()
        if not delivered.get('complete'):
            self.phase = 'preserved_delivery_incomplete'; self.reason = delivered
            return self.state()
        self.phase = 'awaiting_whole_goal_review'
        self.final = await self.step('final-review')
        self.phase = 'completed' if self.final.get('whole_goal_complete') is True else 'whole_goal_not_approved'
        return self.state()
