"""Owner-side observations. Candidate assertions/events remain reviewed semantics.

Only this process timestamps received events and writes primary data. The fixed
runner executes as the distinct test UID; it receives pipes, never primary-file
handles. Event intervals include transport/scheduling, not just test body time.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
from .failure_ledger import clean_cases, acl_entry, require_acl as ledger_acl, Refused as LedgerRefused

SCHEMA = 'nortropic-owner-observation/3'
EVENT_SCHEMA = 'nortropic-test-event/1'
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}')
FILE = re.compile(r'[A-Za-z0-9_./-]+')
STATUSES = {'success','failure','error','skipped','unknown'}


class Refused(ValueError):
    pass


class ObservationInterrupted(Refused):
    """Trusted owner observations survive a later recording/transport failure."""
    def __init__(self,observation):
        super().__init__('Owner observation interrupted after observed cases')
        self.observation=observation


def canonical(value):
    return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()


def manifest(rows):
    if not isinstance(rows,list) or not rows or len(rows)>100000:
        raise Refused('Invalid test inventory')
    seen=set();result=[]
    for index,row in enumerate(rows,1):
        if (not isinstance(row,dict) or set(row)!={'name','file'}
            or not isinstance(row['name'],str) or not NAME.fullmatch(row['name']) or len(row['name'])>512
            or row['name'] in seen or not isinstance(row['file'],str) or not FILE.fullmatch(row['file'])
            or row['file'].startswith('/') or '..' in Path(row['file']).parts):
            raise Refused('Invalid or duplicate test inventory member')
        seen.add(row['name']);result.append({'id':index,**row})
    return result


class Receiver:
    """Numeric identity first; masking is only a parent-side display operation.

    Invalid input permanently refuses the run but never freezes subsequent valid
    failure collection. Missing intervals remain None and unknown.
    """
    def __init__(self, rows, sink, clock=time.monotonic):
        self.rows=manifest(rows);self.sink=sink;self.clock=clock
        self.starts={};self.stops={};self.next_start=1;self.active=None
        self.invalid=False;self.terminals=[];self.fixture_errors=[];self.events=0

    def reject(self,reason):
        self.invalid=True
        self.sink({'event':'protocol-refused','reason':reason})

    def feed(self,event):
        at=self.clock();self.events+=1
        if self.events>2*len(self.rows)+10000:
            raise Refused('Protocol event limit exceeded')
        if not isinstance(event,dict) or event.get('schema')!=EVENT_SCHEMA:
            self.reject('invalid event schema');return
        kind=event.get('event')
        if kind=='terminal':
            if (set(event)!={'schema','event','count','successful','manifest_sha256'}
                or type(event['count']) is not int or type(event['successful']) is not bool
                or event['manifest_sha256']!=hashlib.sha256(canonical(self.rows)).hexdigest()):
                self.reject('invalid terminal');return
            self.terminals.append(event)
            if len(self.terminals)>1:self.reject('duplicate terminal')
            self.sink({'event':'terminal','received_at':at,'count':event['count'],'successful':event['successful']})
            return
        if kind=='fixture-error':
            if set(event)!={'schema','event','before_id','status'} or event['status'] not in ('error','skipped'):
                self.reject('invalid fixture event');return
            number=event['before_id']
            if type(number) is not int or not 1<=number<=len(self.rows)+1:
                self.reject('invalid fixture binding');return
            self.fixture_errors.append({'before_id':number,'status':event['status'],'received_at':at})
            self.sink({'event':'fixture-error',**self.fixture_errors[-1]});return
        allowed={'schema','event','id'} if kind=='start' else {'schema','event','id','status'}
        if kind not in ('start','stop') or set(event)!=allowed:
            self.reject('invalid event fields');return
        number=event['id']
        if type(number) is not int or not 1<=number<=len(self.rows):
            self.reject('invalid numeric case id');return
        if self.terminals:self.reject('case event after terminal')
        if kind=='start':
            if number in self.starts or number in self.stops:
                self.reject('duplicate start');return
            if number!=self.next_start or self.active is not None:self.reject('unexpected case order')
            self.starts[number]=at;self.active=number;self.next_start=number+1
            self.sink({'event':'start','id':number,'received_at':at})
        else:
            if event['status'] not in STATUSES:
                self.reject('invalid case status');return
            if number in self.stops:self.reject('duplicate stop');return
            if self.active!=number or number not in self.starts:self.reject('stop without active start')
            began=self.starts.get(number)
            elapsed=at-began if began is not None else None
            if elapsed is not None and (not math.isfinite(elapsed) or elapsed<0):
                self.reject('invalid observer clock');elapsed=None
            self.stops[number]={'status':event['status'],'seconds':round(elapsed,6) if elapsed is not None else None}
            if self.active==number:self.active=None
            self.sink({'event':'stop','id':number,'received_at':at,**self.stops[number]})

    def finish(self, returncode, *, cleaned, timed_out=False, overflow=False):
        cases=[]
        for row in self.rows:
            state=self.stops.get(row['id'],{'status':'unknown','seconds':None})
            cases.append({'order':row['id'],'name':row['name'],'file':row['file'],**state})
        complete=(not self.invalid and not timed_out and not overflow and cleaned
                  and len(self.terminals)==1 and self.terminals[0]['count']==len(self.rows)
                  and len(self.starts)==len(self.rows) and len(self.stops)==len(self.rows)
                  and self.active is None and not self.fixture_errors)
        passed=(complete and type(returncode) is int and returncode==0
                and self.terminals[0]['successful'] is True
                and all(c['status']=='success' and c['seconds'] is not None for c in cases))
        return {'schema':SCHEMA,'case_timing_schema':3,'observation_kind':'owner-received-events/1',
                'timing_definition':'parent monotonic intervals between received numeric start/stop events; includes transport and scheduling',
                'shared_interpreter_state':True,'protected_primary_files':True,
                'cases':cases,'complete':bool(complete),'passed':bool(passed),
                'terminal_successful':self.terminals[0]['successful'] if len(self.terminals)==1 else None,
                'returncode':returncode,'timed_out':timed_out,'overflow':overflow,
                'cleanup_verified':bool(cleaned),'manifest_sha256':hashlib.sha256(canonical(self.rows)).hexdigest(),
                'fixture_errors':self.fixture_errors}


def receive_process(argv, cwd, env, rows, destination, timeout, cleanup, verify_cleanup,
                    *, popen=subprocess.Popen, clock=time.monotonic):
    retained={}
    try:
        return _receive_process(argv,cwd,env,rows,destination,timeout,cleanup,verify_cleanup,
                                popen=popen,clock=clock,retained=retained)
    except BaseException as error:
        report=retained.get('report')
        if report is None and 'receiver' in retained:
            child=retained.get('child');code=child.poll() if child is not None else None
            report=retained['receiver'].finish(code if type(code) is int else 124,cleaned=False)
        if report is not None:raise ObservationInterrupted(report) from error
        raise


def _receive_process(argv, cwd, env, rows, destination, timeout, cleanup, verify_cleanup,
                     *, popen, clock, retained):
    """Drain distinct protocol/stdout and test/stderr pipes; only parent owns files.

    cleanup and verify_cleanup are fixed owner-side functions, never request
    fields. Cross-UID signaling belongs to the fixed helper; no killpg here.
    Caller must verify distinct owner/test UIDs before using this as authority.
    """
    target=Path(destination);target.mkdir(mode=0o700,parents=True,exist_ok=False);private_directory(target)
    started=clock();deadline=started+timeout;timed_out=False;overflow=False;invalid=False
    protocol_bytes=log_bytes=bad_lines=0;buffer=b''
    with private_output(target/'events.jsonl') as journal,private_output(target/'suite.log') as log:
        def sink(event):
            journal.write(canonical(event));journal.flush()
        receiver=Receiver(rows,sink,clock=clock)
        retained['receiver']=receiver
        selector=None
        child=popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,close_fds=True,start_new_session=True)
        try:
            retained['child']=child
            selector=selectors.DefaultSelector()
            selector.register(child.stdout,selectors.EVENT_READ,'protocol')
            selector.register(child.stderr,selectors.EVENT_READ,'log')
            while selector.get_map():
                remaining=deadline-clock()
                if remaining<=0:timed_out=True;break
                for key,_ in selector.select(min(.2,remaining)):
                    raw=os.read(key.fileobj.fileno(),65536)
                    if not raw:selector.unregister(key.fileobj);continue
                    if key.data=='log':
                        log_bytes+=len(raw)
                        if log_bytes>8*1024*1024:overflow=True;break
                        log.write(raw);log.flush();continue
                    protocol_bytes+=len(raw)
                    if protocol_bytes>16*1024*1024:overflow=True;break
                    buffer+=raw
                    if len(buffer)>256*1024:overflow=True;break
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1)
                        try:receiver.feed(json.loads(line))
                        except (ValueError,TypeError,KeyError,UnicodeError):
                            receiver.reject('malformed protocol line');invalid=True;bad_lines+=1
                            if bad_lines>100:overflow=True;break
                if overflow:break
            if buffer:receiver.reject('partial protocol terminal');invalid=True
            try:child.wait(timeout=max(.05,deadline-clock()))
            except subprocess.TimeoutExpired:timed_out=True
        finally:
            try:
                try:cleanup(child)
                except Exception:
                    invalid=True
                    receiver.reject('fixed cleanup failed')
                finally:
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:invalid=True
            finally:
                from contextlib import ExitStack
                with ExitStack() as handles:
                    handles.callback(child.stdout.close);handles.callback(child.stderr.close)
                    if selector is not None:handles.callback(selector.close)
        try:
            cleaned=bool(verify_cleanup(child))
        except Exception:
            cleaned=False
        if invalid:receiver.invalid=True
        report=receiver.finish(child.returncode,cleaned=cleaned,timed_out=timed_out,overflow=overflow)
        retained['report']=report
        report.update(wall_seconds=round(clock()-started,6),
                      log_sha256=hashlib.sha256((target/'suite.log').read_bytes()).hexdigest(),
                      case_observation_sha256=hashlib.sha256((target/'events.jsonl').read_bytes()).hexdigest())
    for path in target.iterdir():path.chmod(0o600)
    return report


def time_left(deadline, cap):
    remaining=cap if deadline is None else min(cap,deadline-time.monotonic())
    if remaining<=0:raise Refused('Owner measurement deadline exceeded')
    return remaining


def owner_node(path, uid, *, directory=False, allow_link=False, deadline=None, private=False):
    """Conservative Darwin mode/ACL check; a write ACL is never silently ignored."""
    import stat
    path=Path(path);info=path.lstat()
    if (info.st_uid!=uid or info.st_mode & (0o077 if private else 0o022) or
        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
             or allow_link and stat.S_ISLNK(info.st_mode))):
        raise Refused('Owner-bound path is writable or has the wrong type/owner')
    result=subprocess.run(['/bin/ls','-lde',str(path)],capture_output=True,
                          env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=time_left(deadline,10))
    if result.returncode:raise Refused('ACL observation unavailable')
    for line in result.stdout.decode('utf-8','strict').splitlines()[1:]:
        try:acl_entry(line,private=private)
        except LedgerRefused:raise Refused('Unqualified ACL on protected path') from None
    return info


def private_directory(path):
    path=Path(path)
    owner_node(path,os.getuid(),directory=True,private=True)
    for parent in path.parents:
        info=parent.lstat()
        import stat
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid())
                or info.st_mode&0o022 and not (info.st_uid==0 and info.st_mode&stat.S_ISVTX)):
            raise Refused('Unsafe private result ancestor')
        # Ancestors may be searchable. The private boundary itself never is.
        if not info.st_mode&0o022:owner_node(parent,info.st_uid,directory=True)
        else:
            try:ledger_acl(parent)
            except LedgerRefused:raise Refused('Unqualified ACL on sticky ancestor') from None


@contextmanager
def private_output(path):
    path=Path(path);private_directory(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),0o600)
        info=owner_node(path,os.getuid(),private=True)
        opened=os.fstat(stream.fileno())
        if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise Refused('Private output identity changed')
        yield stream


def process_table(test_uid):
    """Host ps, numeric identity only. Never collect arbitrary command arguments."""
    result=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,uid=,lstart='],capture_output=True,
                          env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=10)
    if result.returncode or len(result.stdout)>4*1024*1024:raise Refused('Process table unavailable')
    rows={}
    for line in result.stdout.decode('utf-8','strict').splitlines():
        parts=line.split(None,4)
        if len(parts)!=5 or any(not x.isdigit() for x in parts[:4]):raise Refused('Unknown process identity')
        pid,ppid,pgid,uid=map(int,parts[:4])
        if uid==test_uid:
            rows[pid]={'pid':pid,'ppid':ppid,'pgid':pgid,'uid':uid,'started':parts[4]}
    return rows


def protected_tools(plats, profile, *, deadline=None):
    """Check the fixed host tool trees and every link/parent before test imports.

    These are host dependencies, not candidate code. Root/owner may maintain
    them; the test UID must not be able to change a target or replace its link.
    A write ACL or an unbounded/unknown tree refuses preparation.
    """
    import stat,pwd
    from scripts import matning_provanvandare as fast
    roots=[plats.runtime/'.runtime'/name for name in profile['lankar']]
    roots.append(plats.runtime/'.runtime/temporal-venv' if profile['python']==fast.VENV else Path(profile['python']))
    account=pwd.getpwnam(plats.prov)
    groups=set(os.getgrouplist(account.pw_name,account.pw_gid))|{account.pw_gid}
    if 80 in groups:raise Refused('Test account belongs to admin')
    pending=list(roots);checked=set();acl=[];owners={0,os.getuid()}
    def unsafe(info):
        return info.st_uid not in owners or (not stat.S_ISLNK(info.st_mode) and
            test_can_write(info,account.pw_uid,groups))
    while pending:
        time_left(deadline,1)
        path=Path(pending.pop()).absolute()
        if path in checked:continue
        checked.add(path)
        if len(checked)>100000:raise Refused('Fixed host tool tree exceeds limit')
        info=path.lstat()
        if unsafe(info):
            raise Refused('Fixed tool or parent can be changed by another account')
        if path.parent!=path:pending.append(path.parent)
        if stat.S_ISLNK(info.st_mode):
            # Symlink permission bits do not govern writes; its verified parent
            # does. Verify its target and target ancestors as well.
            pending.append(path.resolve(strict=True))
        elif stat.S_ISDIR(info.st_mode):
            # Ancestors are checked, not recursively explored. Recurse only
            # inside an explicitly selected tree (including linked subtrees).
            pass
        elif not stat.S_ISREG(info.st_mode):raise Refused('Unknown fixed host tool type')
        acl.append(path)
    pending=list(roots);walked=set()
    while pending:
        time_left(deadline,1)
        root=Path(pending.pop()).resolve(strict=True)
        if root in walked:continue
        walked.add(root)
        members=[root]
        if root.is_dir():
            for directory,dirs,files in os.walk(root,followlinks=False):
                members.extend(Path(directory)/name for name in dirs+files)
        for path in members:
            time_left(deadline,1)
            if path in checked:continue
            checked.add(path)
            if len(checked)>100000:raise Refused('Fixed host tool tree exceeds limit')
            info=path.lstat()
            if unsafe(info):
                raise Refused('Fixed host dependency is writable by another account')
            if stat.S_ISLNK(info.st_mode):
                target=path.resolve(strict=True);pending.append(target)
                # Targets outside the selected tree need the same parent check.
                for parent in target.parents:
                    if parent not in checked:
                        parent_info=parent.lstat()
                        if unsafe(parent_info) or not stat.S_ISDIR(parent_info.st_mode):raise Refused('Untrusted linked tool parent')
                        checked.add(parent);acl.append(parent)
            elif not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise Refused('Unknown fixed host dependency type')
            acl.append(path)
    for start in range(0,len(acl),128):
        result=subprocess.run(['/bin/ls','-lde',*[str(p) for p in acl[start:start+128]]],capture_output=True,
                              env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=time_left(deadline,30))
        if result.returncode:
            raise Refused('Fixed host tool ACL is unqualified')
        for line in result.stdout.decode('utf-8','strict').splitlines():
            if re.match(r'\s*\d+:',line):
                try:acl_entry(line)
                except LedgerRefused:raise Refused('Fixed host tool ACL is unqualified') from None
    return sorted(groups)


def test_can_write(info, test_uid, groups):
    """Unix mode selection for the actual test account, before ACL checks.

    Homebrew's root/owner admin-group write permission does not grant the
    non-admin test account write access. Its own groups remain disallowed.
    """
    bit=0o200 if info.st_uid==test_uid else 0o020 if info.st_gid in groups else 0o002
    return bool(info.st_mode&bit)


def materialize_snapshot(plats, identifier, request, bundle, *, deadline=None):
    """Owner Git checkout. Only explicit disposable symlinks lead to test writes."""
    import stat
    import tempfile
    owner=os.getuid();base=plats.inkorg/identifier
    for path in (plats.inkorg.parent,plats.inkorg,base):owner_node(path,owner,directory=True,deadline=deadline)
    owner_node(base/'begaran.json',owner,deadline=deadline);owner_node(bundle,owner,deadline=deadline)
    source=base/'source'
    if source.exists() or source.is_symlink():raise Refused('Snapshot already exists')
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_TERMINAL_PROMPT':'0','GIT_LITERAL_PATHSPECS':'1','LANG':'C','LC_ALL':'C'}
    def git(cwd,*args):
        result=subprocess.run(['git','--no-replace-objects','-c','core.hooksPath=/dev/null',
              '-c','core.fsmonitor=false','-C',str(cwd),*args],env=env,capture_output=True,timeout=time_left(deadline,600))
        if result.returncode:raise Refused('Snapshot Git operation failed')
        return result.stdout
    git(base,'clone','--quiet','--no-checkout',str(bundle),str(source))
    members=[]
    for item in git(source,'ls-tree','-r','-z',request['candidate']).split(b'\0'):
        if not item:continue
        fields,rawpath=item.split(b'\t',1);mode,kind,oid=fields.decode().split();name=rawpath.decode()
        if (mode not in ('100644','100755') or kind!='blob' or name.startswith('/')
            or any(x in ('','.','..') for x in name.split('/')) or name.split('/')[0] in ('.scratch','.runtime')):
            raise Refused('Unsupported snapshot member')
        members.append((name,mode))
    if len(members)>10000:raise Refused('Too many snapshot files')
    git(source,'checkout','--quiet','--detach',request['candidate'])
    if git(source,'rev-parse','HEAD','HEAD^{tree}').decode().split()!=[request['candidate'],request['tree']]:
        raise Refused('Snapshot identity differs')
    tracked={};total=0
    for name,mode in members:
        path=source/name
        total+=path.lstat().st_size
        if total>512*1024*1024:raise Refused('Snapshot byte limit exceeded')
        path.chmod(0o755 if mode=='100755' else 0o644);owner_node(path,owner,deadline=deadline)
        tracked[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (source,*[p for p in source.rglob('*') if p.is_dir() and not p.is_symlink()]):
        path.chmod(0o755);owner_node(path,owner,directory=True,deadline=deadline)
    # The agent deliberately runs with umask 077. Git's metadata must still be
    # readable by the distinct test UID, without granting it any write access.
    for path in (source/'.git').rglob('*'):
        if path.is_symlink():raise Refused('Linked Git metadata is unsupported')
        if path.is_dir():continue  # already explicitly chmod'ed above
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode):raise Refused('Nonregular Git metadata')
        path.chmod(0o755 if info.st_mode & 0o111 else 0o644)
        owner_node(path,owner,deadline=deadline)
    work=plats.arbete/identifier
    (source/'.scratch').symlink_to(work/'scratch',target_is_directory=True)
    with (source/'.git/info/exclude').open('a') as exclusions:
        exclusions.write('\n/.scratch\n')
    profile=__import__('scripts.matning_provanvandare',fromlist=['PROFILER']).PROFILER[request['repo']]
    if profile['lankar']:
        runtime=source/'.runtime';runtime.mkdir(mode=0o755);runtime.chmod(0o755)
        if stat.S_IMODE(owner_node(runtime,owner,directory=True,deadline=deadline).st_mode)!=0o755:
            raise Refused('Shared runtime tool directory mode differs')
        for name in profile['lankar']:
            host=plats.runtime/'.runtime'/name
            if not host.exists():raise Refused('Required fixed host tool is absent')
            (runtime/name).symlink_to(host,target_is_directory=host.is_dir())
    if profile['npm']:
        modules=source/profile['npm']/'node_modules'
        if modules.exists() or modules.is_symlink():raise Refused('Candidate supplies dependency write surface')
        modules.symlink_to(work/'npm/node_modules',target_is_directory=True)
        with (source/'.git/info/exclude').open('a') as exclusions:
            exclusions.write('/'+profile['npm']+'/node_modules\n')
    return source,tracked


def write_owner(path, value, *, replace=False, public=False):
    """Owner-generated descriptor or private result; never inherit an open path."""
    path=Path(path)
    temporary=path.with_name(path.name+'.new') if replace else path
    import stat
    mode=0o644 if public else 0o600
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as out:
        os.fchmod(out.fileno(),mode)
        info=os.fstat(out.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=mode:
            raise Refused('Owner descriptor mode or identity differs')
        checked=owner_node(temporary,os.getuid(),private=not public)
        if (checked.st_dev,checked.st_ino)!=(info.st_dev,info.st_ino):raise Refused('Owner file identity changed')
        if not public:private_directory(path.parent)
        out.write(canonical(value));out.flush();os.fsync(out.fileno())
    if replace:os.replace(temporary,path)


def output_directory(plats, identifier):
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}',identifier):raise Refused('Invalid measurement identity')
    return plats.agarhem/'Library/Application Support/Nortropic/measurement-results'/identifier


def capture_stage(argv, destination, timeout, cleanup, verify_cleanup):
    """Open both private streams before transport can import any candidate."""
    target=Path(destination);target.mkdir(mode=0o700);private_directory(target)
    raw_protocol=bytearray();count=0;deadline=time.monotonic()+timeout;refused=False
    with private_output(target/'preparation.log') as log,private_output(target/'protocol.jsonl') as protocol:
        poll=None
        child=subprocess.Popen(argv,cwd='/',stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               close_fds=True,start_new_session=True)
        try:
            poll=selectors.DefaultSelector()
            poll.register(child.stdout,selectors.EVENT_READ,'protocol');poll.register(child.stderr,selectors.EVENT_READ,'log')
            while poll.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:refused=True;break
                for key,_ in poll.select(min(.2,remaining)):
                    raw=os.read(key.fileobj.fileno(),65536)
                    if not raw:poll.unregister(key.fileobj);continue
                    if key.data=='protocol':
                        if len(raw_protocol)+len(raw)>4*1024*1024:refused=True;break
                        raw_protocol.extend(raw);protocol.write(raw);protocol.flush()
                    else:
                        count+=len(raw)
                        if count>8*1024*1024:refused=True;break
                        log.write(raw);log.flush()
                if refused:break
            if not refused:
                try:child.wait(timeout=max(.05,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:refused=True
        finally:
            try:
                try:cleanup(child)
                except Exception:refused=True
                finally:
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:refused=True
            finally:
                from contextlib import ExitStack
                with ExitStack() as handles:
                    handles.callback(child.stdout.close);handles.callback(child.stderr.close)
                    if poll is not None:handles.callback(poll.close)
        for stream in (log,protocol):stream.flush();os.fsync(stream.fileno())
    try:cleaned=verify_cleanup(child)
    except Exception:cleaned=False
    if refused or child.returncode!=0 or not cleaned:raise Refused('Fixed preparation failed or left processes')
    lines=raw_protocol.splitlines()
    if len(lines)!=2:raise Refused('Preparation must emit one probe and one inventory')
    return [json.loads(line) for line in lines]


def clean_boundary_probe(probe):
    """The named-key flag alone does not clear unresolved filename-sweep hits."""
    if not isinstance(probe,dict):return False
    sweep=probe.get('svep')
    return (probe.get('kredentialfri') is True and probe.get('nycklar_lasbara')==[]
            and isinstance(sweep,dict) and type(sweep.get('antal')) is int and sweep['antal']==0
            and sweep.get('lasbara_med_nyckelnamn')==[] and 'avbrutet' in sweep and sweep['avbrutet'] is None)


def process_snapshot(test_uid,stage,child=None):
    """Record actual process identities used by start/cleanup checks, no argv."""
    rows=process_table(test_uid)
    transport=None
    if child is not None:
        transport=process_table(os.getuid()).get(child.pid)
    return {'stage':stage,'observed_at':time.monotonic(),'test_uid':test_uid,
            'processes':list(rows.values()),'transport':transport}


def retain_process_snapshot(target,observations,snapshot):
    # Persist before returning to a transport/parser that may raise. A failed
    # prepare must retain the same identity evidence as a completed suite.
    write_owner(target/('process-%04d.json'%(len(observations)+1)),snapshot)
    observations.append(snapshot)


def save_suite(target,report,identifier):
    try:
        write_owner(target/'suite.json',report)
        write_owner(target/'klar.json',{'id':identifier,'candidate':report['candidate'],'returncode':report['returncode'],
                    'test_count':report['test_count'],'last_line':report['last_line'],'measurement_passed':report['passed'],
                    'suite_sha256':hashlib.sha256(canonical(report)).hexdigest()})
    except BaseException as error:
        raise ObservationInterrupted(report) from error


def measure(plats, identifier, request, bundle, run_id, fixed_program, *, selection=None):
    """Called only by the adopted owner agent after reserving the ledger attempt.

    No session invokes its privileged transport. It uses the existing exact
    fixed-program rule as the existing test account, never as root.
    """
    import pwd,stat
    from datetime import datetime, timezone
    from scripts import matning_provanvandare as fast
    began=time.monotonic();deadline=began+5040  # 5400-second quiet window, 360 reserved for fixed cleanup
    started_at=datetime.now(timezone.utc).isoformat()
    owner=os.getuid();test_uid=pwd.getpwnam(plats.prov).pw_uid
    if (owner==0 or owner!=os.geteuid() or owner!=pwd.getpwnam(plats.agare).pw_uid
        or test_uid in (0,owner)):raise Refused('Distinct actual owner/test UIDs required')
    fixed=Path(fixed_program);info=fixed.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise Refused('Installed fixed program must be an immutable regular root file')
    program_hash=hashlib.sha256(fixed.read_bytes()).hexdigest()
    if program_hash!=hashlib.sha256(Path(fast.__file__).read_bytes()).hexdigest():
        raise Refused('Installed fixed program differs from adopted source')
    owner_node(fixed,0,deadline=deadline)
    test_groups=protected_tools(plats,fast.PROFILER[request['repo']],deadline=deadline)
    initial_processes=process_snapshot(test_uid,'before')
    if initial_processes['processes']:raise Refused('Test account already has processes; no run started')
    target=output_directory(plats,identifier)
    if any(p.is_symlink() or (p/'.git').exists() for p in (target,*target.parents)):
        raise Refused('Primary observations must be outside repositories and links')
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);target.mkdir(mode=0o700)
    for parent in (target,*target.parents):
        info=parent.lstat()
        if info.st_uid not in (0,owner):raise Refused('Untrusted primary result ancestor')
        owner_node(parent,info.st_uid,directory=True,deadline=deadline)
    private_directory(target.parent);private_directory(target)
    process_observations=[]
    retain_process_snapshot(target,process_observations,initial_processes)
    source,files=materialize_snapshot(plats,identifier,request,bundle,deadline=deadline)
    observer_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    queue_hash=hashlib.sha256((Path(__file__).resolve().parents[1]/'scripts/measurement_queue.py').read_bytes()).hexdigest()
    base=plats.inkorg/identifier
    plan={'schema':'nortropic-observed-request/1','id':identifier,'run':run_id,
          'candidate':request['candidate'],'tree':request['tree'],'files':files,
          'names':[] if selection is None else selection['names'],'manifest':None,
          'program_sha256':program_hash,'observer_sha256':observer_hash,'queue_sha256':queue_hash}
    write_owner(base/'observation.json',plan,public=True)
    transport=['/usr/bin/sudo','-n','-u',plats.prov,str(fixed)]
    cleanup_status={'verified':False,'attempts':0,'observations':process_observations}
    def cleanup(child):
        # No other test-account process existed before this locked request.
        # Only the owner can write these exact identities; no PID CLI argument.
        for _ in range(2):
            observed=process_snapshot(test_uid,'cleanup-before',child)
            retain_process_snapshot(target,process_observations,observed)
            rows={row['pid']:row for row in observed['processes']}
            if not rows:break
            if len(rows)>1000:raise Refused('Too many test processes; explicit owner cleanup required')
            stop={'schema':'nortropic-measurement-stop/1','id':identifier,'run':run_id,
                  'candidate':request['candidate'],'processes':list(rows.values())}
            write_owner(target/('stop-%02d.json'%(cleanup_status['attempts']+1)),stop)
            write_owner(base/'stop.json',stop,replace=(base/'stop.json').exists(),public=True)
            cleanup_status['attempts']+=1
            subprocess.run(transport+['stop',identifier],cwd='/',stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
        deadline=time.monotonic()+5
        while process_table(test_uid) and time.monotonic()<deadline:time.sleep(.1)
        observed=process_snapshot(test_uid,'cleanup-after',child)
        retain_process_snapshot(target,process_observations,observed)
        cleanup_status['verified']=not observed['processes']
    def verified(child):
        observed=process_snapshot(test_uid,'verified',child)
        retain_process_snapshot(target,process_observations,observed)
        return cleanup_status['verified'] and child.poll() is not None and not observed['processes']
    report=None
    def bind_observation(value):
        report=value
        report.update(schema=fast.SVIT,request_id=identifier,candidate=request['candidate'],tree=request['tree'],
              command=(['python','-B','-m','unittest',*plan['names'],'-v'] if plan['names'] else
                       ['python','-B','-m','unittest','discover','-s',profile['katalog'],'-p','test_*.py','-v']),
              test_count=len(rows),expected_test_count=request['expected_test_count'],
              last_line='OK' if report['passed'] else 'FAILED (owner observations)',
              credential_free_execution=True,credential_boundary={'kind':'distinct owner and test UIDs; fixed D042 helper',
                  'owner_uid':owner,'test_uid':test_uid,'script_sha256':program_hash,
                  'observer_sha256':observer_hash,'queue_sha256':queue_hash,
                  'probe_sha256':hashlib.sha256(canonical(probe['probe'])).hexdigest()},
              whole_operation_seconds=round(time.monotonic()-began,6),cleanup=cleanup_status,
              ledger_run=run_id,planned_regression=selection is not None,
              started_at=started_at,finished_at=datetime.now(timezone.utc).isoformat())
        return report
    try:
        probe,inventory=capture_stage(transport+['prepare',identifier],target/'prepare',time_left(deadline,2400),cleanup,verified)
        if (set(probe)!={'schema','id','run','probe'} or probe['schema']!='nortropic-owner-probe/1'
            or probe['id']!=identifier or probe['run']!=run_id
            or not clean_boundary_probe(probe['probe'])
            or probe['probe'].get('skript_sha256')!=program_hash
            or probe['probe'].get('identitet',{}).get('uid')!=test_uid
            or probe['probe'].get('identitet',{}).get('groups')!=test_groups
            or inventory.get('schema')!='nortropic-test-inventory/1'):
            raise Refused('Probe or inventory binding differs')
        rows=inventory.get('rows')
        if not isinstance(rows,list):raise Refused('Missing test inventory')
        normalized=manifest([{'name':r.get('name'),'file':r.get('file')} for r in rows if isinstance(r,dict)])
        if (rows!=normalized or inventory.get('manifest_sha256')!=hashlib.sha256(canonical(normalized)).hexdigest()
            or request['expected_test_count'] is not None and len(rows)!=request['expected_test_count']
            or any(row['file'] not in files for row in rows)):
            raise Refused('Inventory is not the expected source-bound manifest')
        plan['manifest']=normalized;write_owner(base/'observation.json',plan,replace=True,public=True)
        write_owner(target/'manifest.json',normalized);write_owner(target/'gransprob.json',probe['probe'])
        profile=fast.PROFILER[request['repo']]
        report=receive_process(transport+['run',identifier],'/',None,
                    [{'name':r['name'],'file':r['file']} for r in rows],target/'run',time_left(deadline,profile['tid']),cleanup,verified)
        bind_observation(report)
        # Re-read actual protected source bytes. Fixture symlinks are not source.
        try:
            for name,digest in files.items():
                path=source/name
                for parent in (source,*list(path.parents)[:len(Path(name).parts)-1]):
                    owner_node(parent,owner,directory=True,deadline=deadline)
                owner_node(path,owner,deadline=deadline)
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise Refused('Snapshot changed during measurement')
        except (Refused,OSError):
            report.update(complete=False,passed=False,source_recheck=False,cleanup_verified=False)
        log=(target/'run/suite.log').read_bytes();events=(target/'run/events.jsonl').read_bytes()
        for name,raw in (('suite.log',log),('cases.jsonl',events)):
            with private_output(target/name) as f:f.write(raw)
        save_suite(target,report,identifier)
        return report
    except BaseException as error:
        if isinstance(error,ObservationInterrupted):report=error.observation
        if report is not None:
            raise ObservationInterrupted(bind_observation(report)) from error
        raise
