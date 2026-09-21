"""One bounded host child per stage, serial with ordinary development activities."""
from contextlib import ExitStack
import json
import signal
import subprocess
import sys
import time
from temporalio import activity
from temporalio.exceptions import CancelledError
from .release import ROOT, CODE_ROOT, require_active_code
from .shared import process_identity
from .private_stage import check_private_processes, write, cleanup_private_run, private_size, LIMIT_BYTES, stop_private_group
from scripts.bounded import stop_group


@activity.defn(name='private_stage')
def private_stage(request: dict) -> dict:
    require_active_code()
    check_private_processes()
    logs=ROOT/'.runtime/ap10/dispatch';logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=request['run_id']+'-'+request['role']
    write(logs/(key+'.request.json'),request)
    proc=None
    with ExitStack() as stack:
        out=stack.enter_context((logs/(key+'.stdout')).open('xb'))
        err=stack.enter_context((logs/(key+'.stderr')).open('xb'))
        inp=stack.enter_context((logs/(key+'.request.json')).open('rb'))
        try:
            proc=subprocess.Popen([sys.executable,'-B','-m','runtime.private_stage'],
                cwd=CODE_ROOT,stdin=inp,stdout=out,stderr=err,start_new_session=True)
            write(logs/(key+'.launch.json'),{'stage_pid':proc.pid,'stage_identity':process_identity(proc.pid)})
            end=time.monotonic()+request['seconds']+5
            while proc.poll() is None:
                activity.heartbeat(request['role'])
                if activity.is_cancelled():raise CancelledError('Private stage cancelled')
                if time.monotonic()>end or out.tell()+err.tell()>65536 or private_size()>LIMIT_BYTES:
                    raise RuntimeError('Private stage time/log/storage limit')
                time.sleep(.25)
            out.flush();err.flush();stdout=(logs/(key+'.stdout')).read_bytes()
            if len(stdout)>65536 or proc.returncode:
                return {'completed':False,'reason':'Private stage unavailable; inspect private evidence'}
            return json.loads(stdout)
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
                    try:proc.wait(timeout=6)
                    except subprocess.TimeoutExpired:pass
                if not stop_private_group(proc):raise RuntimeError('Private stage group cleanup incomplete')
                # Also cover a SIGKILL of the guardian whose model owns another group.
                cleanup_private_run(request['run_id'])
