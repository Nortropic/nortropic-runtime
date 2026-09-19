import fcntl,json,subprocess,time
from pathlib import Path
from scripts.bounded import stop_group
from scripts.probe_bridge import worker_command
root=Path('.runtime/fence-prototype').resolve()
lock=(root/'writer.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
proc=None
result={'model_calls':0,'question':'Does pinned actual Codex app-server retain inherited writer lock?'}
try:
    with (root/'stderr.log').open('wb') as stderr,(root/'stdout.log').open('wb') as stdout:
        proc=subprocess.Popen(worker_command(),stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True,pass_fds=(lock.fileno(),))
        proc.stdin.write((json.dumps({'id':1,'method':'initialize','params':{'clientInfo':{'name':'nr-fd-probe','version':'0.1'},'capabilities':{'experimentalApi':True}}})+'\n').encode());proc.stdin.flush()
        time.sleep(.5);result['alive_after_start']=proc.poll() is None
        lock.close()
        with (root/'writer.lock').open('a') as contender:
            try:fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB);result['inherited_lock_blocks_contender']=False
            except BlockingIOError:result['inherited_lock_blocks_contender']=True
finally:
    result['process_group_removed']=proc is None or stop_group(proc)
    lock.close()
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
