"""Model-free 54c10b P2/P3 on a new loopback-only engine and empty database.

No live engine, schedule, credentials, partner or daemon is read or changed.
Use the release's Python environment; --binary must name the qualified local CLI.
"""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
import uuid

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker, UnsandboxedWorkflowRunner
from scripts.bounded import stop_group

STOP=threading.Event()


@activity.defn
def beat(seconds: int) -> int:
    end=time.monotonic()+seconds;count=0
    while time.monotonic()<end and not STOP.wait(.25):
        activity.heartbeat(count);count+=1
    return count


@workflow.defn
class HeartbeatProbe:
    @workflow.run
    async def run(self,seconds: int) -> int:
        return await workflow.execute_activity(beat,seconds,start_to_close_timeout=timedelta(seconds=seconds+30),
            heartbeat_timeout=timedelta(seconds=10),retry_policy=RetryPolicy(maximum_attempts=1))


def now():return datetime.now(timezone.utc).isoformat()


async def measure(args):
    if not 60<=args.seconds<=7200 or args.port in (7339,7340,7341) or not 1024<=args.port<=65532:
        raise ValueError('Explicit isolated port and60–7200seconds required')
    if args.until and Path(args.until).exists():raise ValueError('Load result already exists; no retrospective overlap')
    out=Path(args.output).resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    binary=Path(args.binary).resolve()
    if not binary.is_file():raise ValueError('Named qualified binary missing')
    for port in range(args.port,args.port+3):
        if port in (7339,7340,7341):raise ValueError('Live port refused')
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    queue='heartbeat-probe-'+uuid.uuid4().hex;namespace='heartbeat-probe'
    command=[str(binary),'--disable-config-env','--disable-config-file','server','start-dev',
        '--ip','127.0.0.1','--port',str(args.port),'--http-port',str(args.port+1),
        '--metrics-port',str(args.port+2),'--namespace',namespace,'--headless','--db-filename',str(out/'engine.sqlite')]
    record={'started_at':now(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'command':command,
        'seconds_limit':args.seconds,'throttle_cap_seconds':args.cap,'heartbeat_timeout_seconds':10,
        'activity_heartbeat_period_seconds':.25,'poll_period_seconds':.4,'load_result':args.until,
        'samples':[],'outcome':'unknown','max_observed_gap_seconds':None,'minimum_margin_seconds':None}
    from importlib.metadata import version
    import sys
    record['python']=sys.version;record['temporalio']=version('temporalio')
    if record['temporalio']!='1.33.0':raise ValueError('Probe requires the pinned temporalio1.33.0')
    STOP.clear();proc=None
    try:
        with (out/'server.log').open('xb') as log:
            proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=out,start_new_session=True)
            record['engine_pid']=proc.pid
            deadline=time.monotonic()+30
            while True:
                if proc.poll() is not None:raise RuntimeError('Isolated engine exited')
                try:client=await asyncio.wait_for(Client.connect('127.0.0.1:'+str(args.port),namespace=namespace),1);break
                except (RuntimeError,TimeoutError):
                    if time.monotonic()>deadline:raise TimeoutError('Isolated engine readiness')
                    await asyncio.sleep(.2)
            kwargs={} if args.cap is None else {'max_heartbeat_throttle_interval':timedelta(seconds=args.cap)}
            with ThreadPoolExecutor(max_workers=1) as executor:
                async with Worker(client,task_queue=queue,workflows=[HeartbeatProbe],activities=[beat],
                                  activity_executor=executor,workflow_runner=UnsandboxedWorkflowRunner(),**kwargs):
                    try:
                        handle=await client.start_workflow(HeartbeatProbe.run,args.seconds,id=queue,task_queue=queue)
                        result=asyncio.create_task(handle.result());record['observation_started_at']=now()
                        while not result.done():
                            raw=(await handle.describe()).raw_description
                            row={'observed_at':now(),'monotonic':time.monotonic(),'heartbeats':[]}
                            for pending in raw.pending_activities:
                                if pending.HasField('last_heartbeat_time'):
                                    row['heartbeats'].append(pending.last_heartbeat_time.ToDatetime(tzinfo=timezone.utc).isoformat())
                            record['samples'].append(row)
                            if args.until and Path(args.until).exists():
                                loadraw=Path(args.until).read_bytes()
                                try:record['load']=json.loads(loadraw)
                                except ValueError:
                                    await asyncio.sleep(.4);continue
                                record['load_sha256']=hashlib.sha256(loadraw).hexdigest();STOP.set()
                            await asyncio.sleep(.4)
                        record['heartbeat_calls']=await result;record['observation_finished_at']=now()
                        if args.until and 'load' not in record:raise TimeoutError('Load did not finish inside probe')
                        record['outcome']='completed'
                    finally:
                        STOP.set()

    except BaseException as error:
        record['outcome']='failed';record['failure_type']=type(error).__name__;raise
    finally:
        STOP.set()
        record['finished_at']=now();record['process_group_removed']=proc is None or stop_group(proc)
        seen=sorted({t for row in record['samples'] for t in row['heartbeats']})
        gaps=[(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds() for a,b in zip(seen,seen[1:])]
        if gaps:
            record['max_observed_gap_seconds']=max(gaps);record['minimum_margin_seconds']=10-max(gaps)
        record['max_poll_gap_seconds']=max((b['monotonic']-a['monotonic'] for a,b in zip(record['samples'],record['samples'][1:])),default=None)
        (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps({k:record[k] for k in ('outcome','max_observed_gap_seconds','minimum_margin_seconds','max_poll_gap_seconds','process_group_removed')}))
        if not record['process_group_removed']:raise RuntimeError('Own engine remains')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--port',type=int,default=38339);parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--cap',type=float);parser.add_argument('--until')
    args=parser.parse_args()
    if args.cap is not None and not 0<args.cap<=10:raise ValueError('Invalid heartbeat cap')
    asyncio.run(measure(args))


if __name__=='__main__':main()

