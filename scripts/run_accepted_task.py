"""Bounded operator run of one accepted native workflow; no alternate scheduler."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google.protobuf.json_format import MessageToDict
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from runtime.workflow import DevelopmentTask
from runtime.profile import ROOT
from scripts.bounded import stop_group

TASK = ROOT / 'tasks/run-report.json'
STATE = ROOT / '.runtime/tasks/runtime-run-report-1'
RESUME = sys.argv[1:] == ['--resume-after-diagnosis']
OUTPUT = ROOT / ('evidence/accepted-task/engine-resume-2' if RESUME else 'evidence/accepted-task/engine')


async def main():
    for port in (7339, 7340, 7341):
        with socket.socket() as s: s.bind(('127.0.0.1', port))
    task = json.loads(TASK.read_text())
    OUTPUT.mkdir(exist_ok=False)
    workspace = STATE / 'candidate'
    if RESUME:
        previous = json.loads((ROOT / 'evidence/accepted-task/attempt-1/launch.json').read_text())
        for field in ('executor_pid', 'provider_pid'):
            try: os.kill(previous[field], 0)
            except ProcessLookupError: pass
            else: raise RuntimeError('Previous writer PID still exists; inspect before resuming')
        try: os.killpg(previous['provider_pid'], 0)
        except ProcessLookupError: pass
        else: raise RuntimeError('Previous provider group still exists')
    else:
        STATE.mkdir(parents=True, exist_ok=False)
        subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(ROOT), str(workspace)], check=True, capture_output=True, timeout=30)
        subprocess.run(['git', '-C', str(workspace), 'checkout', '--detach', task['base']], check=True, capture_output=True, timeout=30)
        subprocess.run(['git', '-C', str(workspace), 'remote', 'remove', 'origin'], check=True, timeout=5)
        for folder in ('tools', '.scratch'): (workspace / folder).mkdir(exist_ok=False)
        shutil.copyfile(ROOT / 'tasks/run-report.md', workspace / 'TASK.md')
    # Exact acceptance/input identities are host evidence, not candidate-owned metadata.
    identities = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (TASK, ROOT / 'tasks/run-report.md', ROOT / task['acceptance'])}
    (OUTPUT / 'inputs.json').write_text(json.dumps({'task':task,'sha256':identities},indent=2)+'\n')
    processes, streams, observations = [], [], []
    def spawn(args, label):
        stream = (OUTPUT / (label + '.log')).open('wb'); streams.append(stream)
        p = subprocess.Popen(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(p)
        observations.append({'spawn':label,'pid':p.pid,'command':args})
        (OUTPUT / 'processes.json').write_text(json.dumps(observations,indent=2)+'\n')
        return p
    def server(label):
        return spawn([str(ROOT/'.runtime/bin/temporal-1.9.1'),'--disable-config-env','--disable-config-file',
                      'server','start-dev','--ip','127.0.0.1','--port','7339','--http-port','7340',
                      '--metrics-port','7341','--namespace','nortropic-runtime','--headless',
                      '--db-filename',str(STATE/'temporal.sqlite')],label)
    async def connect():
        end=time.monotonic()+15
        while time.monotonic()<end:
            try: return await asyncio.wait_for(Client.connect('127.0.0.1:7339',namespace='nortropic-runtime'),1)
            except Exception: await asyncio.sleep(.2)
        raise TimeoutError('service startup deadline')
    passed = False
    try:
        service=server('server-before')
        client=await connect()
        worker=spawn([sys.executable,'-m','runtime.worker'],'worker-before')
        if RESUME:
            handle=client.get_workflow_handle(task['id'])
            prior=await asyncio.wait_for(handle.query(DevelopmentTask.state),15)
            assert prior['phase']=='waiting_diagnosis' and prior['attempts']==1
            reason='D014: verifier stdin replaces unsafe write; nofollow immutable source snapshot; reviewed correction'
            await handle.signal(DevelopmentTask.retry_after_diagnosis,{'expected_attempt':1,'reason':reason})
            observations.append({'resumed_same_task':True,'prior':prior,'change_reason':reason})
        else:
            handle=await client.start_workflow(DevelopmentTask.run,task,id=task['id'],task_queue='development',
                                                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
            try:
                await client.start_workflow(DevelopmentTask.run,task,id=task['id'],task_queue='development')
                raise AssertionError('duplicate task started')
            except WorkflowAlreadyStartedError: observations.append({'duplicate_start_rejected':True})
        end=time.monotonic()+task['attempt_seconds']+130
        while time.monotonic()<end:
            state=await asyncio.wait_for(handle.query(DevelopmentTask.state),10)
            (OUTPUT/'state.json').write_text(json.dumps(state,indent=2)+'\n')
            if state['phase'].startswith('waiting_') and state['attempts'] == (2 if RESUME else 1): break
            await asyncio.sleep(1)
        else: raise TimeoutError('workflow did not reach a waiting state')
        observations.append({'before_restart':state})
        history=await handle.fetch_history()
        (OUTPUT/'history-before.json').write_text(json.dumps([MessageToDict(x) for x in history.events],indent=2)+'\n')
        # At this point the provider has exited and been cleaned up. Test wait replay.
        for proc in (worker,service):
            proc.kill(); proc.wait(timeout=3)
            assert stop_group(proc)
        service=server('server-after'); client=await connect()
        worker=spawn([sys.executable,'-m','runtime.worker'],'worker-after')
        restored=await asyncio.wait_for(client.get_workflow_handle(task['id']).query(DevelopmentTask.state),15)
        observations.append({'after_restart':restored})
        assert restored==state
        assert restored['attempts']==(2 if RESUME else 1)
        passed=state['phase']=='waiting_access'
    finally:
        cleanup=[stop_group(proc) for proc in reversed(processes)]
        for stream in streams: stream.close()
        result={'passed':passed and all(cleanup),'cleanup':cleanup,'observations':observations,
                'scope':'first Codex phase and preserved access wait only; not complete task/v0.1'}
        (OUTPUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    return 0 if result['passed'] else 1


async def bounded():
    task=asyncio.create_task(main()); loop=asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM,task.cancel)
    try: return await asyncio.wait_for(task,520)
    finally: loop.remove_signal_handler(signal.SIGTERM)

if __name__=='__main__': raise SystemExit(asyncio.run(bounded()))
