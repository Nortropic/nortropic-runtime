"""Private stage executor; frozen Office policy, no publisher and no model retries."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import platform
import selectors
import importlib.metadata

from .release import ROOT, require_active_code, sha, require_workspace_instructions
from .profile import command, environment
from .provider_result import parse
from .shared import process_identity
from scripts.bounded import stop_group

HOME = ROOT/'.runtime/ap10/rounds'
LIMIT_BYTES = 512*1024*1024
LOG_BYTES = 2*1024*1024


def write(path, value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    Path(path).chmod(0o600)


def module(config):
    path=Path(config['directory'])/'office/tools/bevakning.py'
    spec=importlib.util.spec_from_file_location('office_watch',path)
    value=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(path.parent));spec.loader.exec_module(value)
    return value


def regular(path):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
        raise ValueError('Non-regular private evidence')
    return path


def previous():
    # Reports are immutable evidence, not a scheduler or authority database.
    candidates=[]
    for path in HOME.glob('*/report/result.json'):
        try:
            report=json.loads(regular(path).read_text())
            if report.get('reviewed') is True:
                packet=path.parent.parent/'intake/data/packet.json'
                if sha(regular(packet))==report.get('packet_sha256'):
                    candidates.append((report['reported_at'],path.parent.parent,report))
        except (OSError,ValueError,KeyError):continue
    if not candidates:return None
    _,home,report=max(candidates,key=lambda x:x[0])
    return {'home':str(home),'report':report,
            'packet':json.loads((home/'intake/data/packet.json').read_text())}


def model(stage, workspace, prompt, schema, seconds, parent):
    (workspace/'.scratch').mkdir(mode=0o700,exist_ok=True)
    write(workspace/'OUTPUT_SCHEMA.json',schema)
    argv=command(workspace,writable=False)
    argv=argv[:-1]+['--output-schema',str(workspace/'OUTPUT_SCHEMA.json'),'-']
    record={'parent_pid':parent,'parent_identity':process_identity(parent),
            'started_epoch':time.time(),'seconds_limit':seconds,'automatic_retries':0,
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
    # The exclusive marker is consumed BEFORE launch. A restart never refunds it.
    write(stage/'budget.json',{'model_calls':1,'role':stage.name,'limit':1})
    write(stage/'prompt.json',{'prompt':prompt,'schema':schema})
    prompt_file=stage/'stdin.txt'
    with prompt_file.open('x') as f:f.write(prompt)
    prompt_file.chmod(0o600)
    proc=None;reason=None;start=time.monotonic();signalled=[]
    def interrupted(sig, frame):
        # Recorded here and acted on by the loop, never raised from the handler (D026, D031). The loop waits almost all
        # the time inside streams.select(), and the standard selectors catch InterruptedError and return no events, so a
        # handler that raised it was swallowed there and the call ran on to its bound while the activity's stop waited.
        signalled.append(sig)
    old={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        with (stage/'events.jsonl').open('xb') as out,(stage/'stderr.log').open('xb') as err,prompt_file.open('rb') as inp,selectors.DefaultSelector() as streams:
            proc=subprocess.Popen(argv,cwd=workspace,env=environment(),stdin=inp,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            for source,target in ((proc.stdout,out),(proc.stderr,err)):
                os.set_blocking(source.fileno(),False)
                streams.register(source,selectors.EVENT_READ,target)
            record.update(provider_pid=proc.pid,provider_identity=process_identity(proc.pid))
            write(stage/'launch.json',record)
            while streams.get_map() or proc.poll() is None:
                if signalled:raise InterruptedError('stage signal')
                if os.getppid()!=parent or process_identity(parent)!=record['parent_identity']:
                    raise InterruptedError('worker parent ended')
                if time.monotonic()-start>seconds:raise TimeoutError('model deadline')
                if private_size()>LIMIT_BYTES:raise ValueError('private storage limit')
                for key,_ in streams.select(.25):
                    raw=os.read(key.fileobj.fileno(),65536)
                    if not raw:
                        streams.unregister(key.fileobj);key.fileobj.close();continue
                    # Bound only these captured outputs. A process-wide file-size
                    # limit also kills the native CLI while opening its own state.
                    target=key.data;remaining=LOG_BYTES//2-target.tell()
                    target.write(raw[:remaining]);target.flush()
                    if len(raw)>remaining:raise ValueError('provider output limit')
    except (InterruptedError,TimeoutError,ValueError,OSError) as error:
        reason=type(error).__name__
    finally:
        for sig in old:signal.signal(sig,signal.SIG_IGN)
        try:
            removed=proc is None or stop_private_group(proc)
        finally:
            if proc is not None:
                for stream in (proc.stdout,proc.stderr):
                    if stream is not None:stream.close()
            for sig,handler in old.items():signal.signal(sig,handler)
    records=[]
    try:
        for line in (stage/'events.jsonl').read_text().splitlines():records.append(json.loads(line))
        parsed=parse('codex',records)
        if not parsed.get('valid_terminal'):reason=reason or 'no valid provider terminal'
        require_workspace_instructions(workspace)
    except (OSError,ValueError):parsed={};reason=reason or 'invalid evidence or changed active binding'
    messages=[r.get('item',{}).get('text') for r in records if r.get('type')=='item.completed' and r.get('item',{}).get('type')=='agent_message']
    answer=None
    try:answer=json.loads(messages[-1])
    except (ValueError,IndexError,TypeError):reason=reason or 'no structured answer'
    result={'completed':reason is None and proc is not None and proc.returncode==0 and removed,
            'reason':reason,'provider':parsed,'elapsed_seconds':round(time.monotonic()-start,3),
            'exit_code':proc.returncode if proc is not None else None,
            'process_group_removed':removed,'answer':answer}
    write(stage/'result.json',result)
    return result


def stop_private_group(proc):
    try:return stop_group(proc)
    except PermissionError:
        # macOS can report EPERM during a just-exited group transition. Do not
        # infer cleanup from that error: require a reaped leader AND no OS group.
        if proc.poll() is None:
            if not hasattr(proc,'wait'):raise
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:raise
        groups=subprocess.check_output(['ps','-axo','pgid='],text=True,timeout=5)
        if str(proc.pid) in groups.split():raise
        return True


def private_size():
    # Periodic cap across actual writable private areas, not a filesystem quota.
    # Bursts between samples can exceed it; no exact disk/token/cost promise.
    total=0
    for root in (HOME,ROOT/'.runtime/ap10/dispatch'):
        for p in root.rglob('*'):
            try:
                if p.is_file() and not p.is_symlink():total+=p.stat().st_size
            except FileNotFoundError:pass
    return total


def check_private_processes():
    """Fail closed on an unclean prior provider; never reset the native budget.

    A normal worker loss is detected by the stage guardian and cleans the model
    group. A hard-killed guardian must be diagnosed by the operator, not retried.
    """
    for path in (ROOT/'.runtime/ap10/dispatch').glob('*.launch.json'):
        launch=json.loads(regular(path).read_text())
        pid=launch.get('stage_pid')
        if pid and pid!=os.getpid() and launch.get('stage_identity') and process_identity(pid)==launch.get('stage_identity'):
            raise ValueError('Unfinished private stage; inspect before new private work')
    for path in HOME.glob('*/*/launch.json'):
        launch=json.loads(regular(path).read_text())
        result_path=path.with_name('result.json')
        if result_path.exists() and json.loads(regular(result_path).read_text()).get('process_group_removed') is True:
            continue
        pid=launch.get('provider_pid')
        if pid and launch.get('provider_identity') and process_identity(pid)==launch.get('provider_identity'):
            raise ValueError('Unfinished private provider; inspect its recorded identity before restart')
        if pid:
            try:os.killpg(pid,0)
            except ProcessLookupError:pass
            else:raise ValueError('Unresolved private process group; no blind restart')


def cleanup_private_run(run_id):
    """Explicit stop cleans only recorded groups of this native round.

    PID reuse or an unidentifiable orphan fails closed; never kill an unrelated
    process. A preserved launch marker is not itself proof of successful cleanup.
    """
    if not re.fullmatch('[0-9a-f-]{36}',run_id):raise ValueError('Invalid run ID')
    records=[]
    for path in HOME.joinpath(run_id).glob('*/launch.json'):
        launch=json.loads(regular(path).read_text());records.append((launch['provider_pid'],launch['provider_identity']))
    for path in (ROOT/'.runtime/ap10/dispatch').glob(run_id+'-*.launch.json'):
        launch=json.loads(regular(path).read_text());records.append((launch['stage_pid'],launch['stage_identity']))
    for pid,identity in records:
        actual=process_identity(pid)
        if actual and actual!=identity:raise ValueError('Recorded PID reused; no unsafe cleanup')
        if actual and actual==identity:
            class Recorded:
                def __init__(self,pid):self.pid=pid
                def poll(self):return None if process_identity(self.pid)==identity else 0
            if not stop_private_group(Recorded(pid)):raise ValueError('Private process group remains')
        else:
            try:os.killpg(pid,0)
            except ProcessLookupError:pass
            else:raise ValueError('Unidentified remaining group; explicit diagnosis required')
    return {'run_id':run_id,'recorded_groups':len(records),'process_groups_removed':True}


def main(request):
    os.umask(0o077)
    config=require_active_code()
    check_private_processes()
    if request.get('config_sha256')!=config['config_sha256'] or request.get('obligation')!='office-python-temporal':
        raise ValueError('Only the exact activated named private obligation is allowed')
    run=request.get('run_id','');role=request.get('role')
    if not re.fullmatch('[0-9a-f-]{36}',run) or role not in ('intake','analysis','review','report'):
        raise ValueError('Invalid native run or role')
    expected={'intake':90,'analysis':480,'review':240,'report':60}
    if request.get('seconds')!=expected[role]:raise ValueError('Fixed stage budget required')
    HOME.mkdir(parents=True,exist_ok=True,mode=0o700)
    if any(p.is_symlink() for p in (HOME,*HOME.parents)):raise ValueError('Unsafe round home')
    total=private_size()
    if total>LIMIT_BYTES-64*1024*1024:raise ValueError('Private storage budget unavailable; preserve previous reports')
    round_home=HOME/run;round_home.mkdir(exist_ok=True,mode=0o700)
    stage=round_home/role
    stage.mkdir(mode=0o700,exist_ok=False)  # native redelivery cannot reset spent budget
    write(stage/'request.json',request)
    policy=module(config)
    if role=='intake':
        prior=previous()
        if prior:write(stage/'previous.json',prior)
        versions={'python':platform.python_version(),'temporalio':importlib.metadata.version('temporalio'),
                  'runtime_revision':config['runtime_revision'],'office_revision':config['office_revision'],
                  'active_config_sha256':config['config_sha256']}
        context=Path(config['directory'])/'context'
        result=policy.prepare(stage/'data',{'working':ROOT,'active':Path(config['directory'])/'runtime'},versions,prior,context)
        write(stage/'result.json',result)
    elif role in ('analysis','review'):
        workspace=round_home/(role+'-workspace');workspace.mkdir(mode=0o700)
        # Office prepares only frozen copies, no direct permission on original data.
        policy.workspace(workspace,round_home,Path(config['directory'])/'context',role)
        result=model(stage,workspace,policy.prompt(role),policy.schema(role),request['seconds'],os.getppid())
    else:
        result=policy.finish(round_home,request,config)
        write(stage/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('completed','needs_model','reviewed','reason','decision','reported_at','reused_from')}))


if __name__=='__main__':main(json.load(sys.stdin))
