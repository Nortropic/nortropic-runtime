"""Resume a copied v0.1 waiting workflow; preserve the original DB and all evidence."""
import asyncio
import json
from pathlib import Path
import sqlite3

from google.protobuf.json_format import MessageToDict
from temporalio import activity
from temporalio.worker import Worker

from runtime.integration import digest, require_gate
from runtime.profile import ROOT
from runtime.service import LocalService
from runtime.workflow import DevelopmentTask

TASK={'id':'fixture-missing-review','target':'Nortropic/nortropic-runtime','base':'a'*40,
      'steps':[{'provider':'codex','prompt':'fixture'}],'attempt_seconds':2,
      'acceptance_sha256':'f'*64,'allowed_paths':['tools/fixture.py']}
CALLS=[]

@activity.defn(name='review_candidate')
async def review(request):
    CALLS.append('review')
    assert request['review_number']==2
    result={k:request['subject'][k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
    return dict(result,scope='whole_task',terminal_status='completed',verdict='approved',
                blocking_findings=[],summary='Declared recovery fixture',reviewer_run='new-fixture-review')

@activity.defn(name='publish_candidate')
async def publish(request):
    require_gate(TASK,request['subject'],request['tests'],request['review']);CALLS.append('simulated_publication')
    return {'merged':True,'fixture_only':True}

async def main():
    output=ROOT/'evidence/review-continuation/legacy-restart';output.mkdir(exist_ok=False)
    directory=ROOT/'.runtime/review-continuation/legacy-restart';directory.mkdir(exist_ok=False)
    old=ROOT/'.runtime/connected-fixture-v2/temporal.sqlite'
    with sqlite3.connect('file:'+str(old)+'?mode=ro',uri=True) as source, sqlite3.connect(directory/'temporal.sqlite') as target:source.backup(target)
    states=[]
    # Stop and restart both native service and worker around the exact wait.
    for stage in ('inspect','resume'):
        async with LocalService(directory/'temporal.sqlite',output/stage,'nr-connected-fixture') as client:
            async with Worker(client,task_queue='fixture',workflows=[DevelopmentTask],activities=[review,publish]):
                handle=client.get_workflow_handle(TASK['id'])
                state=await asyncio.wait_for(handle.query(DevelopmentTask.state),10)
                assert state['phase']=='waiting_review' and state['attempts']==1 and state['review_recovery']=='review_only'
                states.append(state)
                if stage=='inspect':
                    first=await handle.fetch_history(); old_events=[MessageToDict(x) for x in first.events]
                else:
                    assert states[0]==states[1]
                    await handle.signal(DevelopmentTask.continue_after_review,
                        {'task_sha256':digest(TASK),'candidate':'b'*40,'review_number':1,
                         'expected_attempt':1,'action':'review_only','reason':'Legacy fixture missing evidence replaced by explicit valid fixture review'})
                    final=await asyncio.wait_for(handle.result(),15)
                    assert final['attempts']==1 and len(final['reviews'])==2 and final['publication_attempts']==1
                    events=[MessageToDict(x) for x in (await handle.fetch_history()).events]
                    assert events[:len(old_events)]==old_events
                    (output/'history.json').write_text(json.dumps(events,indent=2)+'\n')
                    (output/'state.json').write_text(json.dumps(final,indent=2)+'\n')
    result={'passed':True,'original_database_unchanged':True,'resumed_same_workflow':TASK['id'],
            'wait_survived_service_and_worker_restart':states[0]==states[1],
            'old_history_prefix_preserved':True,'calls':CALLS,'model_calls':0,'remote_publications':0,'fixture_only':True}
    assert CALLS==['review','simulated_publication']
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),60))
