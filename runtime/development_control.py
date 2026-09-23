"""Explicit operator controls for the one finite goal, never a second engine."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys

from temporalio.client import WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode
from . import development_assessment as assessment
from . import development_host as host
from .development_model import active_scope
from .development_workflow import FiniteDevelopment, FiniteAssessment
from .release import delegate, require_active_code
from .shared import SharedService

NAME = assessment.APPLICATION


def build_only(config):
    """The interactive routes belong to the BUILD of the application and to nothing else.

    Independent review of the assessment decision found this open: with an assessment bound, the
    interactive-retry gate matches a paused assessment exactly - phase waiting_control or
    waiting_host_diagnosis with no children - so it could have launched a real interactive driver session
    against the run whose preserved evidence a second assessment exists to examine unchanged, and could have
    signalled it without the host-answer check that operate('continue') applies.
    """
    if assessment.identity(config) != NAME:
        raise ValueError('An interactive route belongs to the application build, not to a further '
                         'assessment; the bound identity is ' + assessment.identity(config))


async def operate(action, reason=None):
    config = require_active_code()
    scope, _ = active_scope(config.get('development', {}).get('contract_sha256'))
    if action in ('pause','resume','stop','continue'):
        if not isinstance(reason,str) or not reason.strip():
            raise ValueError('Explicit scoped reason required')
        if action!='continue' and not (action=='stop' and scope.inspect()['control'] in ('stopped','revoked','exhausted')):
            scope.control({'pause':'paused','resume':'active','stop':'stopped'}[action],reason)
    # The identity a start would use. It is the original application unless the ACTIVE configuration binds a
    # separately reviewed further assessment, and it is resolved from that configuration rather than chosen here.
    current = assessment.identity(config)
    async with SharedService() as client:
        handle = client.get_workflow_handle(current)
        if action in ('start','interactive-start'):
            if scope.inspect()['control'] != 'active':
                raise ValueError('The finite goal is not active')
            # The BUILD sequence is pinned to the ORIGINAL application identity, never to a further
            # assessment's. Otherwise binding an assessment would quietly give the interactive session,
            # the A/B preparation, the implementations and the publication a second identity to run under,
            # which is the opposite of what a re-assessment is for.
            await client.start_workflow(FiniteDevelopment.run,scope.expected,id=NAME,task_queue='development',
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        elif action == 'assess':
            # Straight to the whole-goal assessment of the SAME delivered application, under the bound
            # identity. No interactive session, no draft, no task, no child, no publication.
            if scope.inspect()['control'] != 'active':
                raise ValueError('The finite goal is not active')
            if current == NAME:
                raise ValueError('No separately reviewed further assessment is bound in the active configuration')
            # What it follows: an actual whole-goal review that was NOT approved, and runs that are really
            # closed. The second check is what keeps a second writer off this one scope; REJECT_DUPLICATE
            # still protects the new identity against being started twice itself.
            followed, _ = assessment.preserved_refusal(scope, config)
            assessment.changed_evidence(scope, followed)
            # Retention-proof: REJECT_DUPLICATE below refuses only what the engine still holds.
            assessment.unused_identity(scope, current)
            for earlier in assessment.identities(config)[:-1]:
                try:
                    described = await asyncio.wait_for(client.get_workflow_handle(earlier).describe(), 10)
                except RPCError as error:
                    # The engine removes a closed execution one day after it closed, and a removed execution is
                    # not running. That it really ran and was not approved is what preserved_refusal() above read
                    # from the scope; its history is then delivered from the verified archive.
                    if error.status != RPCStatusCode.NOT_FOUND:
                        raise
                    continue
                if described.status == WorkflowExecutionStatus.RUNNING:
                    raise ValueError('The application a further assessment follows is still running: '+earlier)
            await client.start_workflow(FiniteAssessment.run,scope.expected,id=current,task_queue='development',
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
            assessment.record_start(scope, current, datetime.now(timezone.utc).isoformat())
        elif action == 'stop':
            # Scope is closed before cancellation, so queued task starts and
            # new publication effects remain denied even if cancellation lags.
            errors=[]
            # EVERY run identity this commitment has had, plus its tasks - not only the latest. A stop must
            # reach an assessment that is actually running, and must not depend on which identity happens to
            # be current. A run that is already closed is left alone rather than cancelled again: cancelling
            # a completed execution is not a stop, it is an error this branch would then have to report.
            # Nothing outside this scope is touched, so AP10 and unrelated work are unaffected.
            for task_id in [*scope.inspect()['tasks'],*assessment.identities(config)]:
                try:
                    described=await asyncio.wait_for(client.get_workflow_handle(task_id).describe(),10)
                    if described.status!=WorkflowExecutionStatus.RUNNING:
                        continue
                    await asyncio.wait_for(client.get_workflow_handle(task_id).cancel(),10)
                except RPCError as error:
                    if error.status != RPCStatusCode.NOT_FOUND:
                        errors.append({'workflow':task_id,'status':str(error.status)})
                except TimeoutError:
                    errors.append({'workflow':task_id,'status':'cancellation readback timeout'})
            if errors:
                raise RuntimeError('Scope is stopped; native cancellation requires inspection: '+json.dumps(errors))
        elif action=='continue':
            # The HOST answers a diagnosis the model already made, so the chain can leave the host-diagnosis wait
            # without spending one of the counted interactive starts. It supplies no content: the reason states a host
            # fact, the answer is recorded for the next diagnosis, and every later decision is still the model's.
            native=await handle.query(FiniteDevelopment.state)
            if native.get('phase')!='waiting_host_diagnosis':
                raise ValueError('Only a parent waiting for host diagnosis can be continued; observed '+str(native.get('phase')))
            if scope.inspect()['control']!='active':
                raise ValueError('Resume the finite goal explicitly before answering its diagnosis')
            host.check_host_answer(scope,reason)   # every refusal BEFORE the continuation is spent
            await asyncio.wait_for(handle.signal(FiniteDevelopment.continue_after_diagnosis,reason),10)
            # Recorded only after the parent has accepted the signal. A recorded answer is what the next diagnosis is
            # shown and what lets a host-interrupted review be re-run, so it must never outlive an undelivered signal.
            recorded=host.record_host_answer(scope,reason,(native.get('children') or [None])[-1],native)
        elif action not in ('status','pause','resume','wake'):
            raise ValueError('Unknown finite-goal action')
        wake = None
        if action in ('pause','resume','wake'):
            # The waiting parent does not poll a pause: tell it to re-read the host state now. The scope
            # control above is already written, so whatever the parent reads next is current. Best effort:
            # an undelivered signal costs at most the parent's rare fallback timer, and is REPORTED so
            # the operator can repeat `wake` instead of finding out hours later.
            try:
                await asyncio.wait_for(handle.signal(FiniteDevelopment.host_state_changed),10);wake='accepted by the engine'
            except (RPCError,TimeoutError) as error:
                wake='NOT delivered ('+type(error).__name__+'); repeat wake, or the parent notices at its fallback timer'
        try:
            native = await handle.query(FiniteDevelopment.state)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:raise
            native = {'available':False,'reason':'Named native workflow has not been found; no execution or success inferred'}
        return {'observed_at':datetime.now(timezone.utc).isoformat(),'scope':scope.inspect(),
                'native':native,'config_sha256':config['config_sha256'],**({'wake_signal':wake} if wake else {}),
                **({'host_answer':recorded} if action=='continue' else {}),
                'meaning':'Dated native observation, not whole-goal approval; status starts no work'}


def main():
    delegated=delegate('runtime.development_control',sys.argv[1:])
    if delegated is not None:return delegated
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['interactive-start','interactive-retry','assess','status','pause','resume','stop','wake','continue']);parser.add_argument('--reason')
    args=parser.parse_args()
    if args.action=='interactive-start':
        from .development_interactive import prepare,execute,preflight
        config=require_active_code();build_only(config)
        preflight(config['development']['contract_sha256'])
        request=prepare(config['development']['contract_sha256'])
        # Start the waiting native parent BEFORE the interactive handover.
        asyncio.run(operate('interactive-start'))
        result=execute(request);print(json.dumps(result,indent=2));return 0 if result['completed'] else 1
    if args.action=='interactive-retry':
        from .development_interactive import prepare_retry,execute,preflight,pending
        config=require_active_code();build_only(config)
        # Executor, terminal, subscription and trust refusals come BEFORE a retry
        # slot is bound, the scope resumed or the parent signalled.
        preflight(config['development']['contract_sha256'])
        current=asyncio.run(operate('status'))
        phase=current['native'].get('phase')
        if phase not in ('waiting_control','waiting_host_diagnosis') or current['native'].get('children'):
            raise ValueError('Existing native parent must be paused before any child')
        request=pending(config['development']['contract_sha256']) or prepare_retry(config['development']['contract_sha256'],args.reason)
        asyncio.run(operate('resume',args.reason))
        if phase=='waiting_host_diagnosis':
            async def diagnosed():
                async with SharedService() as client:
                    await client.get_workflow_handle(NAME).signal(
                        FiniteDevelopment.continue_after_diagnosis,args.reason)
            asyncio.run(diagnosed())
        result=execute(request);print(json.dumps(result,indent=2));return 0 if result['completed'] else 1
    print(json.dumps(asyncio.run(operate(args.action,args.reason)),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
