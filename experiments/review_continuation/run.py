"""Bounded native continuation proof with real Git/tests and explicit provider fixtures.

No model, GitHub or business-code execution. Review decisions use a separate
read-only verifier subprocess; local atomic Git ref update represents integration.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import patch

from google.protobuf.json_format import MessageToDict
from temporalio import activity
from temporalio.worker import Worker

from runtime import candidate
from runtime.integration import digest, require_gate
from runtime.profile import ROOT
from runtime.service import LocalService
from runtime.workflow import DevelopmentTask

CASES = {}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


@activity.defn(name='execute_codex')
def implement(request):
    case = CASES[request['task_id']]
    number = request['number']
    output = case['output'] / ('attempt-' + str(number)); output.mkdir()
    if number > 1:
        assert 'Blocking findings:' in request['prompt'] and 'zero' in request['prompt']
        assert request['change_reason']
    # Deliberate, declared fixture defect: the zero boundary is only checked by
    # the independent review process, demonstrating why passing tests is not approval.
    code = ('def increment(value):\n    return value + 1 if value else 0\n' if number == 1
            and case['kind'] in ('rejected', 'repair-test-failure', 'no-change')
            else 'def increment(value):\n    return value + 1\n')
    if case['kind'] == 'no-change' and number == 2:
        code = 'def increment(value):\n    return value + 1 if value else 0\n'
    (case['source']/'tools/increment.py').write_text(code)
    with patch.object(candidate, 'ROOT', case['origin']), patch.object(candidate, 'task_directory', return_value=case['state']):
        frozen = candidate.prepare(case['task'], number, case['source'])
    workspace = case['state']/frozen['workspace_name']
    candidate.git(workspace, 'bundle', 'create', str(output/'candidate.bundle'), 'HEAD')
    (output/'candidate.py').write_bytes(candidate.git(workspace, 'show', frozen['candidate']+':tools/increment.py', raw=True))
    check = subprocess.run([sys.executable, '-B', '-c',
        'from tools.increment import increment; assert increment(1) == 2'],
        cwd=workspace, capture_output=True, text=True, timeout=5)
    passed = check.returncode == 0 and not (case['kind'] == 'repair-test-failure' and number == 2)
    save(output/'acceptance.json', {'passed':passed,'returncode':check.returncode,
        'stderr':check.stderr,'injected_failure':case['kind']=='repair-test-failure' and number==2})
    result = dict(frozen, provider_completed=True, phase_acceptance_passed=passed,
        evidence=str(output.relative_to(ROOT)), thread_id='fixture-author-'+uuid.uuid4().hex)
    save(output/'result.json', result)
    return result


@activity.defn(name='review_candidate')
def review(request):
    case=CASES[request['task_id']]; number=request.get('review_number',1)
    output=case['output']/('review-'+str(number)); output.mkdir()
    if number>1: assert request['change_reason']
    if case['kind']=='nonobject' and number==1:
        result=None
    elif case['kind']=='missing' and number==1:
        result={'terminal_status':'incomplete','reason':'Injected absent provider result; no candidate defect inferred'}
    else:
        workspace=case['state']/request['workspace_name']
        # Independent process receives immutable candidate source, not an author
        # verdict. It checks the accepted zero requirement, and cannot publish.
        script=('import json,os; from tools.increment import increment; '
                'actual=increment(0); print(json.dumps({"pid":os.getpid(),"actual":actual,"passed":actual==1}))')
        proc=subprocess.run([sys.executable,'-B','-c',script],cwd=workspace,
                            capture_output=True,text=True,timeout=5,check=True)
        observation=json.loads(proc.stdout); save(output/'observation.json',observation)
        result={key:request['subject'][key] for key in ('task_id','task_sha256','candidate','acceptance_sha256')}
        result.update(scope='whole_task',terminal_status='completed',
            reviewer_run='fixture-review-process-'+str(observation['pid'])+'-'+uuid.uuid4().hex,
            verdict='approved' if observation['passed'] else 'rejected',
            blocking_findings=[] if observation['passed'] else ['tools/increment.py:2: accepted zero requirement fails: increment(0) returns 0, expected 1.'],
            summary='Separate verifier process checked the accepted zero requirement.')
        if number==1 and case['kind']=='stale': result['candidate']='f'*40
        if number==1 and case['kind']=='self-review': result['reviewer_run']=request['subject']['implementation_runs'][0]
        if number==1 and case['kind']=='inconclusive': result.update(verdict='inconclusive',summary='Injected unjudgeable review')
    save(output/'decision.json',result)
    return result


@activity.defn(name='publish_candidate')
def publish(request):
    case=CASES[request['task_id']]
    require_gate(case['task'],request['subject'],request['tests'],request['review'])
    subject=request['subject']; workspace=case['state']/request['workspace_name']
    assert candidate.git(workspace,'rev-list','--parents','-n','1',subject['candidate']).split()==[subject['candidate'],subject['base']]
    for name,expected in request['candidate_files_sha256'].items():
        assert hashlib.sha256(candidate.git(workspace,'show',subject['candidate']+':'+name,raw=True)).hexdigest()==expected
    # Real local integration, conditional on the exact old ref; no remote API.
    candidate.git(case['origin'],'fetch',str(workspace),subject['candidate'])
    candidate.git(case['origin'],'update-ref','refs/heads/integrated',subject['candidate'],subject['base'])
    assert candidate.git(case['origin'],'rev-parse','integrated')==subject['candidate']
    result={'merged':True,'local_fixture_only':True,'candidate':subject['candidate'],
            'tree':candidate.git(workspace,'rev-parse',subject['candidate']+'^{tree}')}
    save(case['output']/'integration.json',result)
    return result


async def observe(handle, phase, attempts=None, reviews=None):
    end=asyncio.get_running_loop().time()+15
    while asyncio.get_running_loop().time()<end:
        state=await asyncio.wait_for(handle.query(DevelopmentTask.state),2)
        if (state['phase']==phase and (attempts is None or state['attempts']==attempts)
                and (reviews is None or state.get('review_number')==reviews)):return state
        await asyncio.sleep(.05)
    raise AssertionError(state)


def signal(task, state, action, reason):
    return {'task_sha256':digest(task),'candidate':state['results'][-1]['candidate'],
            'review_number':state['review_number'],'expected_attempt':state['attempts'],
            'action':action,'reason':reason}


async def main(name):
    output=ROOT/'evidence/review-continuation'/name;output.mkdir(parents=True,exist_ok=False)
    state=ROOT/'.runtime/review-continuation'/name;state.mkdir(parents=True,exist_ok=False)
    kinds=('rejected','nonobject','missing','stale','self-review','inconclusive','repair-test-failure','no-change')
    reports=[]
    with ThreadPoolExecutor(max_workers=1) as executor:
        async with LocalService(state/'temporal.sqlite',output/'service','nr-review-continuation') as client:
            async with Worker(client,task_queue='review-proof',workflows=[DevelopmentTask],
                    activities=[implement,review,publish],activity_executor=executor,max_concurrent_activities=1):
                for kind in kinds:
                    task_id='review-proof-'+kind
                    case_state=state/kind;case_state.mkdir();origin=case_state/'origin';origin.mkdir()
                    candidate.git(origin,'init','-q');candidate.git(origin,'config','user.name','Runtime fixture')
                    candidate.git(origin,'config','user.email','fixture@example.invalid')
                    (origin/'README').write_text('Explicitly isolated fixture: increment(n) must equal n+1, including zero.\n')
                    candidate.git(origin,'add','.');candidate.git(origin,'commit','-qm','fixture accepted base')
                    base=candidate.git(origin,'rev-parse','HEAD');candidate.git(origin,'branch','integrated',base)
                    source=case_state/'candidate';candidate.git(case_state,'clone','-q',str(origin),str(source));(source/'tools').mkdir()
                    task={'id':task_id,'target':'Nortropic/nortropic-runtime','base':base,
                          'steps':[{'provider':'codex','prompt':'Implement increment(n)=n+1 including zero, only tools/increment.py.'}],
                          'attempt_seconds':5,'acceptance_sha256':'a'*64,'allowed_paths':['tools/increment.py']}
                    case_output=output/kind;case_output.mkdir()
                    CASES[task_id]={'task':task,'kind':kind,'state':case_state,'origin':origin,'source':source,'output':case_output}
                    handle=await client.start_workflow(DevelopmentTask.run,task,id=task_id,task_queue='review-proof')
                    before=await observe(handle,'waiting_review',1,1);save(case_output/'before.json',before)
                    assert before['review_recovery']==('repair' if kind in ('rejected','repair-test-failure','no-change') else 'review_only')
                    assert not (case_output/'integration.json').exists()
                    initial_history=await handle.fetch_history();save(case_output/'before-history.json',[MessageToDict(x) for x in initial_history.events])
                    request=signal(task,before,before['review_recovery'],'Inspected fixture zero violation; repair it within original scope' if before['review_recovery']=='repair' else 'Injected review failure removed; same candidate can be independently reviewed')
                    # Stale and inappropriate signals must not schedule any work.
                    for bad in ({**request,'candidate':'e'*40},{**request,'review_number':0},
                                {**request,'task_sha256':'b'*64},{**request,'expected_attempt':0},
                                {**request,'action':'review_only' if request['action']=='repair' else 'repair'},
                                {**request,'reason':''}):
                        await handle.signal(DevelopmentTask.continue_after_review,bad)
                    unchanged=await handle.query(DevelopmentTask.state);assert unchanged==before
                    await handle.signal(DevelopmentTask.continue_after_review,request)
                    await handle.signal(DevelopmentTask.continue_after_review,request) # duplicate is ignored
                    if kind in ('repair-test-failure','no-change'):
                        diagnosed=await observe(handle,'waiting_diagnosis',2);save(case_output/'diagnosis.json',diagnosed)
                        assert not (case_output/'review-2').exists() and not (case_output/'integration.json').exists()
                        await handle.signal(DevelopmentTask.retry_after_diagnosis,{'expected_attempt':2,'reason':'Fixture failure diagnosed; next fixture attempt changes the zero behavior and passes tests'})
                    final=await asyncio.wait_for(handle.result(),20);save(case_output/'state.json',final)
                    expected_attempts=3 if kind in ('repair-test-failure','no-change') else 2 if kind=='rejected' else 1
                    assert final['attempts']==expected_attempts and len(final['reviews'])==2 and final['publication_attempts']==1
                    assert final['results'][0]==before['results'][0] and final['reviews'][0]['result']==before.get('review')
                    assert (final['reviews'][0]['subject']['candidate']==final['reviews'][1]['subject']['candidate'])==(request['action']=='review_only')
                    history=await handle.fetch_history();events=[MessageToDict(x) for x in history.events]
                    old=[MessageToDict(x) for x in initial_history.events];assert events[:len(old)]==old
                    save(case_output/'history.json',events)
                    reports.append({'case':kind,'passed':True,'attempts':expected_attempts,'reviews':2,'local_integrations':1,'old_history_prefix_preserved':True})
    save(output/'result.json',{'passed':True,'model_calls':0,'remote_publications':0,'provider_fixtures':True,'real_local_git_and_test_review_subprocesses':True,'reports':reports})
    print(json.dumps(reports))

if __name__=='__main__':asyncio.run(asyncio.wait_for(main(sys.argv[1]),180))
