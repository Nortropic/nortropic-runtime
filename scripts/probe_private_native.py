"""Isolated synthetic schedule/cancel qualification on existing shared engine."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import uuid
from unittest.mock import patch
from runtime import obligation
from temporalio import activity
from temporalio.client import (Client,ScheduleIntervalSpec,ScheduleSpec,ScheduleUpdate,
                              ScheduleAlreadyRunningError,WorkflowFailureError)
from temporalio.worker import Worker
from runtime.private_workflow import PrivateAssessment
from runtime.obligation import definition

EVENTS=[]
@activity.defn(name='private_stage')
async def fake_stage(request:dict)->dict:
    EVENTS.append({'run':request['run_id'],'role':request['role'],'event':'start'})
    if request.get('mode')=='cancel':
        try:
            while True:
                activity.heartbeat('synthetic waiting');await asyncio.sleep(.1)
        finally:EVENTS.append({'run':request['run_id'],'role':request['role'],'event':'cleanup'})
    await asyncio.sleep(.1)
    if request['role']=='intake':return {'completed':True,'needs_model':True}
    if request['role']=='analysis':return {'completed':False,'reason':'synthetic quota unavailable'}
    return {'completed':True,'reviewed':False}

async def main():
    home=Path('.runtime/ap10/build-evidence')/('native-'+uuid.uuid4().hex);home.mkdir(parents=True)
    client=await Client.connect('127.0.0.1:7339',namespace='nortropic-runtime')
    identity=uuid.uuid4().hex;queue='ap10-qualification-'+identity;name=queue
    results={};schedule=None
    async with Worker(client,task_queue=queue,workflows=[PrivateAssessment],activities=[fake_stage],max_concurrent_activities=1):
        spec=definition({'config_sha256':'synthetic'})
        spec.action.task_queue=queue;spec.action.id=name
        spec.spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=1))])
        spec.state.limited_actions=True;spec.state.remaining_actions=2
        schedule=await client.create_schedule(name,spec)
        try:
            try:await client.create_schedule(name,spec)
            except ScheduleAlreadyRunningError:results['duplicate_install_refused']=True
            await asyncio.sleep(2)
            assert (await schedule.describe()).info.num_actions==0
            results['paused_no_start']=True
            await schedule.unpause(note='isolated synthetic two starts; no model')
            end=asyncio.get_running_loop().time()+20
            while asyncio.get_running_loop().time()<end:
                state=await schedule.describe()
                if state.info.num_actions==2 and not state.info.running_actions:break
                await asyncio.sleep(.25)
            assert state.info.num_actions==2 and not state.info.running_actions
            await schedule.pause(note='isolated pause persists')
            calls=list(EVENTS);await asyncio.sleep(2)
            assert calls==EVENTS
            results['bounded_real_schedule_starts']=2
            for action in state.info.recent_actions:
                run=await client.get_workflow_handle(action.action.workflow_id).result()
                assert not run['publication'] and run['outcomes']['analysis']['completed'] is False
                assert 'review' not in run['outcomes']
            # Same workflow ID cannot be started a second time while running.
            cancel=await client.start_workflow(PrivateAssessment.run,{'mode':'cancel','obligation':'synthetic'},id=name+'-cancel',task_queue=queue)
            end=asyncio.get_running_loop().time()+10
            while asyncio.get_running_loop().time()<end:
                if any(e['run']==cancel.first_execution_run_id for e in EVENTS):break
                await asyncio.sleep(.1)
            await cancel.cancel()
            try:await asyncio.wait_for(cancel.result(),15)
            except WorkflowFailureError:pass
            else:raise AssertionError('Cancellation became normal completion')
            own=[e for e in EVENTS if e['run']==cancel.first_execution_run_id]
            assert any(e['event']=='cleanup' for e in own) and all(e['role']=='intake' for e in own)
            results['native_cancel_cleanup_no_following_stage']=True
        finally:await schedule.pause(note='qualification finished; no further actions')
    class Attached:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    with patch.object(obligation,'NAME',name),patch.object(obligation,'require_active_code',return_value={'config_sha256':'synthetic'}),patch.object(obligation,'SharedService',Attached):
        stopped=await obligation.operate('stop')
        paused=await obligation.operate('pause')
        assert stopped['note'].startswith('STOPPED') and paused['note'].startswith('STOPPED')
        try:await obligation.operate('resume')
        except ValueError:pass
        else:raise AssertionError('stop-pause-resume erased terminal state')
        results['stop_pause_cannot_reset_terminal_state']=True
    # A fresh worker/client attachment cannot reset native pause/budget.
    client2=await Client.connect('127.0.0.1:7339',namespace='nortropic-runtime')
    async with Worker(client2,task_queue=queue,workflows=[PrivateAssessment],activities=[fake_stage],max_concurrent_activities=1):
        saved=await client2.get_schedule_handle(name).describe();assert saved.schedule.state.paused
        assert saved.info.num_actions==2 and saved.schedule.state.remaining_actions==0
        await asyncio.sleep(1);assert EVENTS==calls+own
        results['pause_and_spent_native_actions_survive_worker_return']=True
    # Delete only isolated fixture schedule after recording its final state.
    (home/'events.json').write_text(json.dumps(EVENTS,indent=2)+'\n')
    results.update(passed=True,model_calls=0,scope='isolated native schedule/fake activities; not actual source or operational daemon restart',schedule_id=name)
    (home/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    await schedule.delete();print(home)

if __name__=='__main__':asyncio.run(main())
