"""Bounded real worker SIGKILL with harmless sandbox writer; no models or GitHub."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from google.protobuf.json_format import MessageToDict
from runtime.candidate import git
from runtime.integration import digest
from runtime.profile import ROOT
from runtime.run import check_unfinished_writers
from runtime.service import LocalService
from runtime.task import task_directory,evidence_directory
from runtime.workflow import DevelopmentTask
from scripts.bounded import stop_group

TASK_ID='runtime-recovery-fixture-1'
PROVIDER='''import json,sys,time
from pathlib import Path
number=int(sys.argv[1])
with Path('tools/recovery.txt').open('a') as out:out.write('attempt'+str(number)+'\\n')
print(json.dumps({'type':'thread.started','thread_id':'fixture-author-'+str(number)}),flush=True)
if number==1:time.sleep(20)
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':0,'output_tokens':0}}),flush=True)
'''

async def wait_until(predicate,seconds):
    end=asyncio.get_running_loop().time()+seconds
    while asyncio.get_running_loop().time()<end:
        if predicate():return
        await asyncio.sleep(.05)
    raise TimeoutError('Fixture condition not reached')

class RecordedGroup:
    def __init__(self,pid):self.pid=pid
    def poll(self):return None

async def main():
    output=ROOT/'evidence/recovery-probe'
    state=task_directory(TASK_ID);evidence=evidence_directory(TASK_ID)
    state.mkdir(exist_ok=False);evidence.mkdir(exist_ok=False)
    verifier=b'def verify(workspace): return {"passed": (workspace / "tools/recovery.txt").read_text() == "attempt1\\nattempt2\\n"}\n'
    task={'id':TASK_ID,'target':'Nortropic/nortropic-runtime','base':'1b020b55e937e12853e811491e56e8e25ee7cd7a',
          'allowed_paths':['tools/recovery.txt'],'steps':[{'provider':'codex','prompt':'Explicit harmless recovery fixture'}],
          'attempt_seconds':3,'automatic_retries':0,'acceptance_sha256':hashlib.sha256(verifier).hexdigest()}
    (state/'accepted.json').write_text(json.dumps(task));(state/'acceptance.py').write_bytes(verifier)
    (state/'brief.md').write_text('Harmless recovery fixture; no model or remote publication.')
    workspace=state/'candidate'
    subprocess.run(['git','clone','-q','--no-hardlinks','--no-checkout',str(ROOT),str(workspace)],check=True,timeout=30)
    git(workspace,'checkout','--detach',task['base']);git(workspace,'remote','remove','origin')
    (workspace/'.scratch').mkdir();(workspace/'.scratch/fixture_provider.py').write_text(PROVIDER)
    (workspace/'TASK.md').write_text('Explicit fixture, no model')
    workers=[];logs=[];launch=None
    result={'model_calls':0,'remote_publications':0,'native_activity_timeout_seconds':153}
    started=time.monotonic()
    def start_worker(n):
        log=(output/('worker-'+str(n)+'.log')).open('wb');logs.append(log)
        p=subprocess.Popen([sys.executable,'-m','experiments.recovery_probe.worker'],cwd=ROOT,
                           stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        workers.append(p);return p
    try:
        async with LocalService(ROOT/'.runtime/recovery-probe/temporal.sqlite',output/'service','nr-recovery-fixture') as client:
            worker=start_worker(1)
            handle=await client.start_workflow(DevelopmentTask.run,task,id=TASK_ID,task_queue='recovery-fixture')
            await wait_until(lambda:(workspace/'tools/recovery.txt').exists(),15)
            launch=json.loads((evidence/'attempt-1/launch.json').read_text())
            worker.kill();worker.wait(timeout=5)
            result['killed_worker_pid']=worker.pid
            try:check_unfinished_writers()
            except RuntimeError as error:result['active_writer_blocks_restart']=str(error)
            else:raise AssertionError('Active writer did not block startup')
            request={'task_id':TASK_ID,'number':2,'prompt':'fixture lock contender','seconds':3,
                     'task_digest':digest(task),'change_reason':'Lock rejection probe, not an authorized retry'}
            contender=subprocess.run([sys.executable,'-m','experiments.recovery_probe.fixture_attempt'],input=json.dumps(request),capture_output=True,text=True,cwd=ROOT,timeout=5)
            (output/'contender.json').write_text(json.dumps({'returncode':contender.returncode,'stdout':contender.stdout,'stderr':contender.stderr},indent=2)+'\n')
            assert contender.returncode!=0 and 'BlockingIOError' in contender.stderr
            assert not (evidence/'attempt-2').exists()
            result['concurrent_guardian_refused']=True
            start_worker(2)
            await wait_until(lambda:(evidence/'attempt-1/result.json').exists(),10)
            first=json.loads((evidence/'attempt-1/result.json').read_text())
            assert first['interrupted']=='deadline' and first['process_group_removed'] is True
            check_unfinished_writers()
            result['old_writer_stopped']=True
            (output/'after-worker-restart.json').write_text(json.dumps(await handle.query(DevelopmentTask.state),indent=2)+'\n')
            end=asyncio.get_running_loop().time()+170
            while asyncio.get_running_loop().time()<end:
                observed=await asyncio.wait_for(handle.query(DevelopmentTask.state),5)
                (output/'current-state.json').write_text(json.dumps(observed,indent=2)+'\n')
                if observed['phase']=='waiting_diagnosis':break
                await asyncio.sleep(.5)
            else:raise TimeoutError('Native activity did not enter bounded diagnosis wait')
            assert observed['attempts']==1 and len(observed['results'])==1
            assert len(list(evidence.glob('attempt-*/launch.json')))==1
            assert (workspace/'tools/recovery.txt').read_text()=='attempt1\n'
            (output/'before-diagnosis.json').write_text(json.dumps(observed,indent=2)+'\n')
            await handle.signal(DevelopmentTask.retry_after_diagnosis,{'expected_attempt':1,'reason':'Worker restarted; previous guardian deadline removed provider group; writer inspection passed; retained artifact verified'})
            final=await asyncio.wait_for(handle.result(),35)
            assert final['phase']=='completed' and final['attempts']==2 and final['publication_attempts']==1
            assert (workspace/'tools/recovery.txt').read_text()=='attempt1\nattempt2\n'
            calls=[json.loads(x)['kind'] for x in (output/'calls.jsonl').read_text().splitlines()]
            assert calls==['fixture_review','fixture_publication']
            assert len(list(evidence.glob('attempt-*/launch.json')))==2
            history=await handle.fetch_history()
            (output/'history.json').write_text(json.dumps([MessageToDict(x) for x in history.events],indent=2)+'\n')
            (output/'final-state.json').write_text(json.dumps(final,indent=2)+'\n')
            result.update(passed=True,attempts=2,fixture_publications=1,retained_work=True)
    finally:
        cleanup=[stop_group(p) for p in workers]
        for marker in evidence.glob('attempt-*/launch.json'):
            recorded=json.loads(marker.read_text())
            cleanup += [stop_group(RecordedGroup(recorded[k])) for k in ('executor_pid','provider_pid') if k in recorded]
        for log in logs:log.close()
        result.update(process_groups_removed=cleanup,elapsed_seconds=round(time.monotonic()-started,3))
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        assert all(cleanup)
    print(json.dumps(result))

if __name__=='__main__':asyncio.run(asyncio.wait_for(main(),240))
