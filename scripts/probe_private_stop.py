"""Zero-model native test of named stop during its own synthetic child activity.

Uses the existing engine, an isolated queue/schedule and harmless child. Does not
touch the real obligation or substitute any production activity implementation.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import patch

from temporalio import activity, workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.worker import Worker
from runtime import obligation
from runtime.private_stage import stop_private_group
from runtime.private_workflow import PrivateAssessment
from runtime.shared import process_identity

EVENTS = []
CHILDREN = []


@activity.defn(name='private_stage')
async def waiting_stage(request: dict) -> dict:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'],
                             start_new_session=True)
    CHILDREN.append(child)
    EVENTS.append(dict(run=request['run_id'], role=request['role'], event='start',
                       pid=child.pid, identity=process_identity(child.pid)))
    try:
        while True:
            activity.heartbeat('synthetic waiting child')
            await asyncio.sleep(.1)
    finally:
        removed = stop_private_group(child)
        EVENTS.append(dict(run=request['run_id'], role=request['role'], event='cleanup',
                           pid=child.pid, removed=removed, exit_code=child.returncode))


# This isolated timer/signal fixture has no IO in workflow code. Its module
# imports host probe helpers, so only this fixture omits import re-sandboxing.
# The actual PrivateAssessment workflow keeps its existing sandbox unchanged.
@workflow.defn(sandboxed=False)
class Unrelated:
    def __init__(self):
        self.done = False

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self.done)
        return 'completed normally'

    @workflow.signal
    def finish(self):
        self.done = True


async def main():
    os.umask(0o077)
    root = Path.cwd()
    home = root / '.runtime/ap10/build-evidence' / ('stop-inflight-' + uuid.uuid4().hex)
    home.mkdir(parents=True, mode=0o700)
    before = json.loads((root / '.runtime/ap10/service.json').read_text())
    client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
    name = 'ap10-stop-fixture-' + uuid.uuid4().hex
    results = {'model_calls': 0, 'source_intakes': 0, 'schedule_id': name}
    schedule = None
    other = None

    class Attached:
        async def __aenter__(self): return client
        async def __aexit__(self, *args): pass

    async with Worker(client, task_queue=name, workflows=[PrivateAssessment, Unrelated],
                      activities=[waiting_stage], max_concurrent_activities=1):
        try:
            other = await client.start_workflow(Unrelated.run, id=name+'-other', task_queue=name)
            spec = obligation.definition({'config_sha256': 'synthetic'},
                                         datetime.now(timezone.utc)+timedelta(seconds=2))
            spec.action.task_queue = name
            spec.action.id = name
            spec.state.paused = False
            schedule = await client.create_schedule(name, spec)
            deadline = asyncio.get_running_loop().time()+20
            while not EVENTS and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(.1)
            assert EVENTS, 'Own synthetic activity did not start'
            native_before = await schedule.describe()
            assert native_before.info.running_actions
            # Only fixture binding/service attachment are substituted. Actual
            # operate(stop), native cancellation and cleanup checks execute.
            with patch.object(obligation, 'NAME', name), \
                 patch.object(obligation, 'require_active_code', return_value={'config_sha256': 'synthetic'}), \
                 patch.object(obligation, 'SharedService', Attached):
                stopped = await obligation.operate('stop')
                paused = await obligation.operate('pause')
                assert stopped['note'].startswith('STOPPED') and paused['note'].startswith('STOPPED')
                try:
                    await obligation.operate('resume')
                except ValueError:
                    results['stopped_resume_refused'] = True
                else:
                    raise AssertionError('Stopped fixture resumed')
            for item in native_before.info.running_actions:
                try:
                    await client.get_workflow_handle(item.workflow_id,
                        first_execution_run_id=item.first_execution_run_id).result()
                except WorkflowFailureError:
                    pass
                else:
                    raise AssertionError('Stopped own run completed normally')
            assert all(e['role'] == 'intake' for e in EVENTS)
            assert any(e['event'] == 'cleanup' and e['removed'] for e in EVENTS)
            for child in CHILDREN:
                assert child.poll() is not None and not process_identity(child.pid)
            assert (await other.describe()).status.name == 'RUNNING'
            await other.signal(Unrelated.finish)
            assert await asyncio.wait_for(other.result(),10) == 'completed normally'
            after = json.loads((root / '.runtime/ap10/service.json').read_text())
            assert after == before
            assert all(process_identity(before[k]['pid']) == before[k]['identity']
                       for k in ('daemon','engine','worker'))
            results.update(passed=True, own_inflight_stopped=True,
                           actual_child_group_removed=True, no_following_stage=True,
                           unrelated_completed_normally=True, shared_service_unchanged=True,
                           stopped=stopped, paused=paused,
                           scope='Isolated real native stop with synthetic child; no model or supplier intake')
        finally:
            if schedule:
                await schedule.pause(note='fixture cleanup')
                for item in (await schedule.describe()).info.running_actions:
                    handle=client.get_workflow_handle(item.workflow_id,
                        first_execution_run_id=item.first_execution_run_id)
                    await handle.cancel()
                    try: await asyncio.wait_for(handle.result(),15)
                    except WorkflowFailureError: pass
                await schedule.delete()
            if other and (await other.describe()).status.name == 'RUNNING':
                await other.signal(Unrelated.finish)
                await asyncio.wait_for(other.result(),10)
            for child in CHILDREN:
                if child.poll() is None: stop_private_group(child)
            (home/'events.json').write_text(json.dumps(EVENTS,indent=2)+'\n')
            (home/'result.json').write_text(json.dumps(results,indent=2,default=str)+'\n')
    print(home)


if __name__ == '__main__':
    asyncio.run(main())
