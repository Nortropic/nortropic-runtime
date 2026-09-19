"""Real native workflow with explicit no-model activity fixtures, no remote writes."""
import asyncio
import json
from pathlib import Path
from datetime import timedelta

from google.protobuf.json_format import MessageToDict
from temporalio import activity
from temporalio.worker import Worker

from runtime.integration import require_gate
from runtime.profile import ROOT
from runtime.service import LocalService
from runtime.workflow import DevelopmentTask

COUNTS = {}


def note(kind):
    task_id = activity.info().workflow_id
    counts = COUNTS.setdefault(task_id, {'implementation': 0, 'review': 0, 'publication': 0, 'remote_mutations': 0})
    counts[kind] += 1
    return task_id


@activity.defn(name='execute_codex')
async def implementation(request):
    task_id = note('implementation')
    return {'provider_completed': True, 'phase_acceptance_passed': task_id != 'fixture-failed-test',
            'candidate': 'b'*40, 'workspace_name': 'commit-1', 'candidate_files_sha256': {},
            'thread_id': 'author-thread', 'evidence': 'fixture-only'}


@activity.defn(name='review_candidate')
async def review(request):
    task_id = note('review')
    subject = request['subject']
    result = {key: subject[key] for key in ('task_id','task_sha256','candidate','acceptance_sha256')}
    result.update(scope='whole_task', terminal_status='completed', verdict='approved',
                  blocking_findings=[], reviewer_run='review-thread')
    if task_id == 'fixture-rejected': result.update(verdict='rejected',blocking_findings=['fixture blocker'])
    if task_id == 'fixture-missing-review': return {'terminal_status':'incomplete'}
    if task_id == 'fixture-stale-review': result['candidate'] = 'c'*40
    if task_id == 'fixture-self-review': result['reviewer_run'] = 'author-thread'
    return result


@activity.defn(name='publish_candidate')
async def publish(request):
    task_id = activity.info().workflow_id
    task = {'id':task_id,'target':'Nortropic/nortropic-runtime','base':'a'*40,
            'steps':[{'provider':'codex','prompt':'fixture'}], 'attempt_seconds':2,
            'acceptance_sha256':'f'*64,'allowed_paths':['tools/fixture.py']}
    require_gate(task,request['subject'],request['tests'],request['review'])
    note('publication')
    counts = COUNTS[task_id]
    if counts['publication'] == 1:
        counts['remote_mutations'] += 1
        if task_id == 'fixture-ack-loss': raise TimeoutError('Injected lost acknowledgement after simulated remote merge')
    return {'merged':True,'fixture_only':True}


async def main():
    output=ROOT/'evidence/connected-workflow/native-fixtures-v2'
    output.mkdir(exist_ok=False)
    state=ROOT/'.runtime/connected-fixture-v2';state.mkdir(exist_ok=False)
    reports=[]
    async with LocalService(state/'temporal.sqlite',output/'service','nr-connected-fixture') as client:
        async with Worker(client,task_queue='fixture',workflows=[DevelopmentTask],
                          activities=[implementation,review,publish],max_concurrent_activities=1):
            cases={'fixture-complete':'completed','fixture-failed-test':'waiting_diagnosis',
                   'fixture-rejected':'waiting_review','fixture-missing-review':'waiting_review',
                   'fixture-stale-review':'waiting_review','fixture-self-review':'waiting_review',
                   'fixture-ack-loss':'waiting_publication_reconciliation'}
            for task_id,expected in cases.items():
                task={'id':task_id,'target':'Nortropic/nortropic-runtime','base':'a'*40,
                      'steps':[{'provider':'codex','prompt':'fixture'}],'attempt_seconds':2,
                      'acceptance_sha256':'f'*64,'allowed_paths':['tools/fixture.py']}
                handle=await client.start_workflow(DevelopmentTask.run,task,id=task_id,task_queue='fixture')
                end=asyncio.get_running_loop().time()+15
                while asyncio.get_running_loop().time()<end:
                    observed=await asyncio.wait_for(handle.query(DevelopmentTask.state),2)
                    if observed['phase']==expected:break
                    await asyncio.sleep(.05)
                else:raise AssertionError((task_id,observed))
                if task_id == 'fixture-ack-loss':
                    assert COUNTS[task_id] == {'implementation':1,'review':1,'publication':1,'remote_mutations':1}
                    (output/'before-reconciliation.json').write_text(json.dumps(observed,indent=2)+'\n')
                    await handle.signal(DevelopmentTask.reconcile_publication,
                                        {'candidate':'b'*40,'reason':'Fixture remote state can now be reconciled'})
                    observed=await asyncio.wait_for(handle.result(),10)
                    assert observed['phase']=='completed' and observed['publication_attempts']==2
                    assert COUNTS[task_id] == {'implementation':1,'review':1,'publication':2,'remote_mutations':1}
                else:
                    assert COUNTS[task_id]['publication']==(1 if expected=='completed' else 0)
                assert COUNTS[task_id]['implementation']==1
                if task_id=='fixture-failed-test':assert COUNTS[task_id]['review']==0
                history=await handle.fetch_history()
                (output/(task_id+'.json')).write_text(json.dumps([MessageToDict(x) for x in history.events],indent=2)+'\n')
                reports.append({'task':task_id,'state':observed,'calls':COUNTS[task_id]})
    result={'passed':True,'model_calls':0,'remote_publications':0,'reports':reports}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'states':[(r['task'],r['state']['phase']) for r in reports]}))


if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),90))
