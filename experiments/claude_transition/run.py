"""Native checkpoint transition with explicit harmless activities, no models/remote writes."""
import asyncio
import copy
import json
from google.protobuf.json_format import MessageToDict
from temporalio import activity
from temporalio.worker import Worker
from runtime.integration import digest, require_gate
from runtime.profile import ROOT
from runtime.service import LocalService
from runtime.workflow import DevelopmentTask

OUTPUT=ROOT/'evidence/claude-transition/native-fixture'
STATE=ROOT/'.runtime/claude-transition-fixture'
CALLS=[]
ACCEPTED=None


async def implementation(request,provider):
    number=request['number'];path=STATE/'inherited-work.txt'
    before=path.read_text() if path.exists() else ''
    if number>1:assert before.endswith(str(number-1)+'\n')
    path.write_text(before+provider+':'+str(number)+'\n')
    CALLS.append({'number':number,'provider':provider,'inherited':before})
    return {'provider_completed':number!=1,'phase_acceptance_passed':number!=1,
            'candidate':'b'*40,'workspace_name':'commit-'+str(number),'candidate_files_sha256':{},
            'thread_id':provider+'-'+str(number),'evidence':'fixture-only'}

@activity.defn(name='execute_codex')
async def codex(request):return await implementation(request,'codex')

@activity.defn(name='execute_claude')
async def claude(request):return await implementation(request,'claude')

@activity.defn(name='review_candidate')
async def review(request):
    result={k:request['subject'][k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
    return {**result,'scope':'whole_task','terminal_status':'completed','verdict':'approved',
            'blocking_findings':[],'reviewer_run':'separate-fixture-review'}

@activity.defn(name='publish_candidate')
async def publish(request):
    require_gate(ACCEPTED,request['subject'],request['tests'],request['review'])
    CALLS.append({'publication':request['subject']['candidate']})
    return {'merged':True,'fixture_only':True}

async def wait(handle,phase):
    for _ in range(200):
        state=await handle.query(DevelopmentTask.state)
        if state['phase']==phase:return state
        await asyncio.sleep(.05)
    raise AssertionError(state)

async def main():
    global ACCEPTED
    OUTPUT.mkdir(exist_ok=False);STATE.mkdir(exist_ok=False)
    original=json.loads((ROOT/'tasks/run-report.json').read_text());original['id']='fixture-access-transition'
    original['attempt_seconds']=2
    async with LocalService(STATE/'temporal.sqlite',OUTPUT/'service','nr-access-fixture') as client:
        async with Worker(client,task_queue='access-fixture',workflows=[DevelopmentTask],activities=[codex,claude,review,publish]):
            handle=await client.start_workflow(DevelopmentTask.run,original,id=original['id'],task_queue='access-fixture')
            await wait(handle,'waiting_diagnosis')
            await handle.signal(DevelopmentTask.retry_after_diagnosis,{'expected_attempt':1,'reason':'Fixture interrupted writer now stopped'})
            before=await wait(handle,'waiting_access');assert before['attempts']==2
            ACCEPTED=copy.deepcopy(original);ACCEPTED['steps'][1].pop('waiting_reason')
            ACCEPTED.update(base='a'*40,acceptance_sha256='f'*64,brief='tasks/run-report-complete.md',
                            continuation={'previous_task_sha256':digest(original),'expected_attempt':2,
                                          'reason':'Fixture qualified access','evidence':'fixture'})
            bad=copy.deepcopy(ACCEPTED);bad['continuation']['expected_attempt']=0
            await handle.signal(DevelopmentTask.resume_after_access,bad)
            await asyncio.sleep(.2)
            assert (await handle.query(DevelopmentTask.state))==before and len(CALLS)==2
            (OUTPUT/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        # A fresh native worker must reconstruct the same waiting state.
        async with Worker(client,task_queue='access-fixture',workflows=[DevelopmentTask],activities=[codex,claude,review,publish]):
            assert (await handle.query(DevelopmentTask.state))==before
            await handle.signal(DevelopmentTask.resume_after_access,ACCEPTED)
            await handle.signal(DevelopmentTask.resume_after_access,ACCEPTED) # duplicate cannot create a new attempt
            result=await asyncio.wait_for(handle.result(),15)
            assert result['phase']=='completed' and result['attempts']==4 and result['publication_attempts']==1
            assert [x['provider'] for x in CALLS if 'provider' in x]==['codex','codex','claude','codex']
            assert len(result['results'])==4 and len(result['continuations'])==1
            history=await handle.fetch_history()
            (OUTPUT/'history.json').write_text(json.dumps([MessageToDict(e) for e in history.events],indent=2)+'\n')
    (OUTPUT/'result.json').write_text(json.dumps({'passed':True,'model_calls':0,'remote_publications':0,
                                               'state':result,'calls':CALLS},indent=2)+'\n')
    print(json.dumps({'passed':True,'attempts':result['attempts'],'calls':CALLS}))

if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),90))
