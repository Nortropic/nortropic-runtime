"""Bounded AP11 host steps on the existing shared native activity queue."""
import asyncio
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys
import time

from temporalio import activity
from temporalio.client import Client
from google.protobuf.json_format import MessageToDict

from .development_model import active_scope
from .development_capacity import inspect_capacity
from .development_scope import identifier, decode
from . import development_host as host
from .private_stage import write, stop_private_group
from .release import ROOT, CODE_ROOT
from .shared import process_identity
from .snapshot import read_regular
from .task import load, evidence_directory
from .workflow import DevelopmentTask


def run_model(request):
    scope, _ = active_scope(request['contract_sha256'])
    stage = scope.directory / 'calls' / identifier(request['nonce'])
    # No concurrent or orphaned AP11 writer. A native retry is never sufficient
    # justification to dismiss an earlier process identity or lost receipt.
    for launch_file in (scope.directory/'calls').glob('*/launch.json'):
        launch = decode(read_regular(launch_file.parent, launch_file.name))
        result_file = launch_file.with_name('result.json')
        if result_file.exists() and decode(read_regular(result_file.parent, result_file.name)).get('process_group_removed') is True:
            continue
        raise ValueError('Unresolved earlier AP11 model ownership; explicit inspection required')
    write(stage / 'dispatch.json', request)
    proc = None
    with (stage/'dispatch.stdout').open('xb') as out, (stage/'dispatch.stderr').open('xb') as err, \
            (stage/'dispatch.json').open('rb') as inp:
        try:
            proc = subprocess.Popen([sys.executable, '-B', '-m', 'runtime.development_model'],
                                    cwd=CODE_ROOT, stdin=inp, stdout=out, stderr=err, start_new_session=True)
            write(stage/'dispatch-launch.json', {'pid': proc.pid, 'identity': process_identity(proc.pid)})
            end = time.monotonic()+490
            while proc.poll() is None:
                activity.heartbeat(request['nonce'])
                if activity.is_cancelled() or time.monotonic() >= end or out.tell()+err.tell() > 65536:
                    raise RuntimeError('Bounded AP11 call cancelled or unavailable')
                time.sleep(.25)
            if proc.returncode:
                raise ValueError('AP11 model guardian incomplete; preserve actual evidence')
            return host.call_result(scope, request['nonce'])
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        pass
                if not stop_private_group(proc):
                    raise RuntimeError('AP11 guardian remains')
                # If the guardian was hard-killed, reconcile only its own exact
                # provider identity. Never kill by a possibly recycled PID.
                path = stage/'launch.json'
                if path.exists():
                    launch = decode(read_regular(stage, 'launch.json'))
                    pid, identity = launch['provider_pid'], launch['provider_identity']
                    actual = process_identity(pid)
                    if actual and actual != identity:
                        raise RuntimeError('AP11 provider PID reused; preserve and inspect')
                    if actual:
                        class Owned:
                            def __init__(self): self.pid = pid
                            def poll(self): return None if process_identity(pid) == identity else 0
                        if not stop_private_group(Owned()):
                            raise RuntimeError('AP11 provider remains')
                    else:
                        try:
                            os.killpg(pid, 0)
                        except ProcessLookupError:
                            pass
                        else:
                            raise RuntimeError('Unidentified AP11 provider group remains')


async def native_observation(task_id):
    async def read():
        client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
        handle = client.get_workflow_handle(task_id)
        state = await handle.query(DevelopmentTask.state)
        return state
    return await asyncio.wait_for(read(), 1)


def save_child(scope, task_id, key):
    if task_id not in scope.inspect()['tasks']:
        raise ValueError('Cannot inspect or control an unrelated child')
    state = asyncio.run(native_observation(task_id))
    dest = evidence_directory(task_id)/'observations'/identifier(key)
    dest.mkdir(parents=True, mode=0o700, exist_ok=False)
    write(dest/'state.json', state)
    write(dest/'observation.json', {'observed_at': datetime.now(timezone.utc).isoformat(),
                                   'source': 'actual native child query'})
    return state


@activity.defn
def development_step(request: dict) -> dict:
    scope, config = active_scope(request['contract_sha256'])
    control = scope.inspect()['control']
    operation = request['operation']; key = identifier(request['key'])
    if operation == 'control':
        return {'control': control}
    if operation == 'preserved-delivery':
        # A direct assessment must never enter the build sequence. This reports what is ALREADY
        # integrated - no model call, no capacity reservation, nothing prepared - so an assessment
        # refuses before spending anything if the delivery it exists to assess is not actually there.
        state = scope.inspect()
        return {'control': control, 'integrated': sorted(state['integrated']),
                'complete': set(state['integrated']) == {'reconciliation', 'handoff'}}
    # Even an observation/cancel preparation must not occupy AP10's time budget.
    # B preparation includes remote binding + exact Git extraction (up to480s),
    # a bounded model guardian (490s) and cleanup. Reserve the whole host step.
    occupied = 20 if operation in ('observe','interactive') else 1500
    try:
        capacity = asyncio.run(inspect_capacity(occupied))
    except Exception:
        capacity = {'available': False, 'wait_seconds': 30, 'reason': 'Native capacity unavailable'}
    if not capacity['available']:
        return {'capacity_wait': True, 'reason': capacity['reason']}
    if operation == 'observe':
        return {'child': save_child(scope, request['task_id'], key), 'control': control}
    if control != 'active':
        return {'control_wait': True, 'control': control}
    if operation == 'interactive':
        from .development_interactive import selected_nonce
        nonce=selected_nonce(scope,config);stage=scope.directory/'calls'/nonce
        if not (stage/'result.json').exists():
            return {'interactive_wait':True}
        result=host.call_result(scope,nonce,'driver')
        ended=decode(read_regular(stage,'session-exit.json'))
        if (result['provider'].get('interactive') is not True
                or ended.get('process_absent') is not True or ended.get('process_group_removed') is not True):
            raise ValueError('Actual interactive driver session has not verifiably ended')
        return host.draft_from_call(scope.expected,nonce)
    if operation == 'propose':
        context, files = host.base_context(scope, config, request['work'], key)
        previous = request.get('revision_request')
        if previous:
            prior = host.call_result(scope, previous['review'], 'preparation-review')
            if prior['answer'].get('verdict') != 'rejected' or not prior['answer'].get('blocking_findings'):
                raise ValueError('Missing review is not a task defect or a reason to re-prepare')
            files['PREVIOUS_DRAFT.json'] = read_regular(scope.directory/'drafts'/identifier(previous['draft']['draft']), 'draft.json')
            files['PREPARATION_REJECTION.json'] = json.dumps(prior, indent=2).encode()
            context['changed_prerequisite'] = 'Address these actual separately reviewed scope/verification findings within the unchanged goal'
        call = host.prepare_call(scope.expected, key, 'driver', request['work'], context, files)
        result = run_model(call)
        if result['answer'].get('action') != 'task':
            return {'hold': True, 'reason': result['answer'].get('reason', 'No justified task'), 'call': key}
        return host.draft_from_call(scope.expected, key)
    if operation == 'review':
        call = host.review_call(scope.expected, request['draft'], key)
        result = run_model(call)
        return {'review': key, 'approved': host.policy(config).review(result['answer']),
                'decision': result['answer']}
    if operation == 'freeze':
        return {'task': host.freeze(scope.expected, request['draft'], request['review'])}
    if operation == 'diagnose':
        state = save_child(scope, request['task_id'], key)
        call = host.diagnosis_call(scope.expected, request['task_id'], state, key)
        run_model(call)
        # Re-read before proposing an exact-subject native signal. A changed
        # state cannot receive a diagnosis for a previous candidate/review.
        current = asyncio.run(native_observation(request['task_id']))
        if current != state:
            raise ValueError('Child changed during diagnosis; no continuation signal')
        return host.recovery_request(scope, request['task_id'], state, key)
    if operation == 'final-review':
        from .development_final import prepare,close
        call=prepare(scope,config,key)
        if call.get('proof_wait'):return call
        run_model(call)
        return close(scope,config,key)
    raise ValueError('Unknown finite development operation')
