"""One genuine interactive A-preparation session, with a bounded native handoff.

Operator launches this before the independent interval and may send /exit after
A is prepared. The parent is already waiting in Temporal. No command/signal is
sent after the verified session exit: its preserved result is the handoff.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import pty
import selectors
import signal
import subprocess
import sys
import termios
import time
import tty

from . import development_host as host
from .development_model import active_scope
from .development_scope import decode
from .private_stage import write, stop_private_group
from .profile import command, environment
from .release import ROOT, require_workspace_instructions
from .shared import process_identity
from .snapshot import read_regular

NONCE='interactive-start'
RETRY='interactive-retry-1'


def selected_nonce(scope):
    path=scope.directory/'interactive-retry.json'
    if not path.exists():return NONCE
    binding=decode(read_regular(scope.directory,path.name))
    if (set(binding)!={'previous','nonce','diagnosis','previous_result_sha256','input_sha256'}
            or binding['previous']!=NONCE or binding['nonce']!=RETRY
            or not isinstance(binding['diagnosis'],str) or not binding['diagnosis'].strip()):
        raise ValueError('Exact host interactive retry binding required')
    previous=read_regular(scope.directory/'calls'/NONCE,'result.json')
    if (host.sha(previous)!=binding['previous_result_sha256']
            or decode(previous).get('completed') is not False
            or host.sha(read_regular(scope.directory/'calls'/RETRY,'input.json'))!=binding['input_sha256']):
        raise ValueError('Interactive retry evidence changed')
    return RETRY


def prepare_retry(expected,reason):
    scope,config=active_scope(expected);state=scope.inspect()
    if (state['control']!='paused' or state['tasks'] or selected_nonce(scope)!=NONCE
            or not isinstance(reason,str) or not reason.strip()):
        raise ValueError('Only explicit diagnosed pre-task paused interactive recovery')
    stage=scope.directory/'calls'/NONCE
    prior=read_regular(stage,'result.json');result=decode(prior)
    ended=decode(read_regular(stage,'session-exit.json'))
    if (result.get('completed') is not False or result.get('process_group_removed') is not True
            or ended.get('process_absent') is not True or process_identity(ended['provider_pid'])):
        raise ValueError('Previous failed interactive process must be verifiably absent')
    try:os.killpg(ended['provider_pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Previous interactive process group remains')
    context,files=host.base_context(scope,config,'reconciliation',RETRY,paused_interactive_recovery=True)
    request=host.prepare_call(expected,RETRY,'driver','reconciliation',context,files)
    write(scope.directory/'interactive-retry.json',{'previous':NONCE,'nonce':RETRY,'diagnosis':reason,
        'previous_result_sha256':host.sha(prior),'input_sha256':request['input_sha256']})
    return request


def interactive_command(workspace,prompt):
    # A process-local table avoids dotted-path quoting ambiguity. Never answer
    # the TUI's persistent trust prompt or change the user's config. Refuse any
    # project-local executable/config layer that trust could newly enable.
    for parent in (workspace,*workspace.parents):
        if parent==Path.home():break
        if (parent/'.codex').exists():
            raise ValueError('Project-local Codex layers require separate review')
    argv=command(workspace,writable=False);cut=argv.index('exec')
    trust='projects={'+json.dumps(str(ROOT))+'={trust_level="trusted"}}'
    return argv[:cut]+['-c',trust,'--no-alt-screen','-C',str(workspace),prompt]


def actual_session(workspace, started, require_complete=True):
    """Read only newly created CLI history selected by exact delivered cwd."""
    selected=[]; sessions=Path.home()/'.codex/sessions'
    now=datetime.now(timezone.utc)
    for offset in (-1,0,1):
        folder=sessions/(now+timedelta(days=offset)).strftime('%Y/%m/%d')
        for path in folder.glob('rollout-*.jsonl'):
            if path.is_symlink() or path.stat().st_mtime < started:
                continue
            with path.open('rb') as stream:
                first=stream.readline(1048576)
            meta=decode(first)
            if meta.get('type')!='session_meta' or meta.get('payload',{}).get('cwd')!=str(workspace):
                continue
            raw=read_regular(sessions,str(path.relative_to(sessions)),limit=8*1024*1024)
            rows=[decode(line) for line in raw.splitlines()]
            if require_complete and not any(r.get('type')=='event_msg' and r.get('payload',{}).get('type')=='task_complete' for r in rows):
                raise ValueError('Interactive session has no actual completed turn')
            identity=meta['payload'].get('id') or meta['payload'].get('session_id')
            if not identity:raise ValueError('Interactive native session identity unavailable')
            selected.append((identity,raw,meta['payload'].get('source')))
    if len(selected)!=1:raise ValueError('Exactly one actual completed interactive session required')
    return selected[0]


def prepare(expected):
    scope,config=active_scope(expected)
    context,files=host.base_context(scope,config,'reconciliation','interactive-a')
    return host.prepare_call(expected,NONCE,'driver','reconciliation',context,files)


def execute(request):
    if not os.isatty(sys.stdin.fileno()):
        raise ValueError('A real interactive terminal is required; exec is not this qualification')
    scope,_=active_scope(request['contract_sha256']);nonce=selected_nonce(scope)
    if request['nonce']!=nonce:raise ValueError('Interactive call is not the host-selected attempt')
    stage=scope.directory/'calls'/nonce
    raw=read_regular(stage,'input.json')
    if host.sha(raw)!=request['input_sha256']:raise ValueError('Delivered interactive input changed')
    data=decode(raw);workspace=stage/'workspace'
    if data['role']!='driver' or data['work']!='reconciliation':raise ValueError('Only the remaining A preparation')
    for name,expected in data['workspace_sha256'].items():
        if host.sha(read_regular(workspace,name))!=expected:raise ValueError('Delivered interactive context changed')
    require_workspace_instructions(workspace)
    prompt=(data['prompt']+'\nYou are now the sole interactive chain driver for the remaining A preparation. '
            'Independently derive the concrete A draft; none has been prepared for you. '
            'Read the actual inputs and frozen recipe; reason about necessity, scope and verification. '
            'Write your structured driver answer matching OUTPUT_SCHEMA.json to .scratch/answer.json. '
            'This is data, not executable acceptance. Do not prepare B, implement code, start tasks or signal Runtime. '
            'Your draft will receive fresh independent review. End your turn with your concrete rationale; '
            'the operator will close this interactive session before the native chain continues.')
    argv=interactive_command(workspace,prompt)
    write(stage/'consumed.json',{'nonce':nonce,'input_sha256':request['input_sha256']})
    write(stage/'interactive-input.json',{'prompt':prompt,'command_kind':'interactive CLI without exec subcommand',
        'handover':'Root relinquishes technical drafting to this session; only terminal closure is an operator action before independent interval',
        'workspace_sha256':data['workspace_sha256']})
    master,slave=pty.openpty();proc=None;reason=None;removed=False;started=time.time();monotonic=time.monotonic()
    # The native TUI obtains its real terminal size without inheriting host tools.
    import fcntl, struct
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,140,0,0))
    old=termios.tcgetattr(sys.stdin.fileno())
    def interrupt(sig,frame):raise InterruptedError('Interactive guardian interrupted')
    handlers={sig:signal.signal(sig,interrupt) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        scope.reserve('reconciliation','driver',nonce)
        def launch():
            nonlocal proc
            proc=subprocess.Popen(argv,cwd=workspace,env={**environment(),'TERM':'xterm-256color'},
                                  stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
            write(stage/'launch.json',{'provider_pid':proc.pid,'provider_identity':process_identity(proc.pid),
                'started_epoch':started,'native_interactive':True,'nonce':nonce})
            return proc
        scope.launch(nonce,launch);os.close(slave);slave=None
        tty.setraw(sys.stdin.fileno())
        with (stage/'terminal.raw').open('xb') as output,(stage/'operator-input.raw').open('xb') as inputs,selectors.DefaultSelector() as streams:
            streams.register(master,selectors.EVENT_READ,'output');streams.register(sys.stdin,selectors.EVENT_READ,'input')
            while proc.poll() is None:
                if time.monotonic()-monotonic>480:raise TimeoutError('Bounded interactive preparation ended')
                if scope.inspect()['control'] not in ('active','paused'):raise ValueError('Finite goal closed during interactive preparation')
                for key,_ in streams.select(.25):
                    try:content=os.read(key.fd,65536)
                    except OSError:
                        if key.data=='output':streams.unregister(master);continue
                        raise
                    if not content:continue
                    if key.data=='output':
                        output.write(content);output.flush();os.write(sys.stdout.fileno(),content)
                        if output.tell()>4*1024*1024:raise ValueError('Bounded terminal evidence exceeded')
                    else:
                        inputs.write(content);inputs.flush();os.write(master,content)
    except (OSError,ValueError,TimeoutError,InterruptedError) as error:reason=str(error)
    finally:
        termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,old)
        for sig in handlers:signal.signal(sig,signal.SIG_IGN)
        try:removed=proc is None or stop_private_group(proc)
        finally:
            os.close(master)
            if slave is not None:os.close(slave)
            for sig,handler in handlers.items():signal.signal(sig,handler)
    answer=None;provider={};session_source=None
    try:
        if proc is None or proc.returncode!=0 or not removed:raise ValueError('Interactive process exit/cleanup is unavailable')
        identity,history,session_source=actual_session(workspace,started,require_complete=False)
        with (stage/'native-interactive-session.jsonl').open('xb') as stream:stream.write(history)
        rows=[decode(line) for line in history.splitlines()]
        errors=json.dumps([r for r in rows if r.get('type') in ('error','turn.failed')
            or r.get('type')=='event_msg' and r.get('payload',{}).get('type') in ('error','turn_failed')]).lower()
        if any(word in errors for word in ('usage limit','quota','rate limit','rate_limit','unauthorized','authentication')):
            if scope.inspect()['control'] in ('active','paused'):
                scope.control('quota','Native interactive provider reported quota/access failure; retain history')
            raise ValueError('Interactive provider quota/access unavailable')
        if not any(r.get('type')=='event_msg' and r.get('payload',{}).get('type')=='task_complete' for r in rows):
            raise ValueError('Interactive session has no actual completed turn')
        answer=decode(read_regular(workspace,'.scratch/answer.json'))
        provider={'thread_id':identity,'valid_terminal':True,'interactive':True}
        for name,expected in data['workspace_sha256'].items():
            if host.sha(read_regular(workspace,name))!=expected:raise ValueError('Bound interactive context changed')
        require_workspace_instructions(workspace)
    except (OSError,ValueError,KeyError) as error:reason=reason or str(error)
    if reason is not None and scope.inspect()['control']=='active':
        scope.control('paused','Interactive handoff unavailable; preserve actual failure, no automatic new call')
    write(stage/'session-exit.json',{'observed_at':datetime.now(timezone.utc).isoformat(),'provider':provider,
        'provider_pid':proc.pid if proc else None,'process_group_removed':removed,
        'process_absent':not process_identity(proc.pid) if proc else True,'exit_code':proc.returncode if proc else None,
        'reason':reason,'session_source':session_source,'operator_input':'operator-input.raw',
        'interval':'Independent continuation begins only if completed=true and actual session exit verified; a failed call starts no G2 interval'})
    result={'completed':reason is None,'reason':reason,'answer':answer,'provider':provider,
            'process_group_removed':removed,'model_started':proc is not None,'nonce':nonce,
            'elapsed_seconds':round(time.monotonic()-monotonic,3)}
    write(stage/'result.json',result)
    return result
