"""Known quota as frozen input: persistent native wait, zero provider calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from google.protobuf.json_format import MessageToDict
from temporalio import activity
from temporalio.worker import Worker
from runtime.profile import ROOT
from runtime.service import LocalService
from runtime.workflow import DevelopmentTask

CALLS=[]
@activity.defn(name='execute_codex')
async def forbidden(request):
    CALLS.append(request)
    raise AssertionError('Known quota wait must not invoke provider')

async def main():
    output=ROOT/'evidence/recovery-probe/capacity-wait-v2';output.mkdir(exist_ok=False)
    database=ROOT/'.runtime/recovery-capacity/temporal.sqlite'
    task={'id':'fixture-known-quota','steps':[{'provider':'codex','prompt':'must not run',
          'waiting_reason':'Known fixture quota exhausted; retain work and await changed capacity evidence'}],
          'attempt_seconds':2}
    states=[]
    for number in (1,2):
        async with LocalService(database,output/('service-'+str(number)),'nr-capacity-fixture') as client:
            async with Worker(client,task_queue='capacity-fixture',workflows=[DevelopmentTask],activities=[forbidden]):
                if number==1:
                    handle=await client.start_workflow(DevelopmentTask.run,task,id=task['id'],task_queue='capacity-fixture')
                else:handle=client.get_workflow_handle(task['id'])
                state=await asyncio.wait_for(handle.query(DevelopmentTask.state),10)
                assert state['phase']=='waiting_access' and state['attempts']==0 and state['results']==[]
                assert state['waiting_reason']==task['steps'][0]['waiting_reason']
                states.append(state)
                history=await handle.fetch_history()
                events=[MessageToDict(x) for x in history.events]
                assert not any('activityTaskScheduledEventAttributes' in x for x in events)
                (output/('history-'+str(number)+'.json')).write_text(json.dumps(events,indent=2)+'\n')
    assert states[0]==states[1] and CALLS==[]
    result={'passed':True,'model_calls':0,'provider_activity_calls':len(CALLS),'states':states,
            'scope':'known quota supplied as frozen input, not an actual provider quota response'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),50))
