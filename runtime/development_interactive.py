"""One genuine interactive A-preparation session, with a bounded native handoff.

Operator launches this before the independent interval and closes the session
after A is prepared (Codex: /exit; Claude: two Ctrl-C, slash commands are disabled).
The parent is already waiting in Temporal. No command/signal is sent after the
verified session exit: its preserved result is the handoff.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import selectors
import signal
import subprocess
import sys
import termios
import time
import tty
import uuid

from . import development_host as host
from .development_model import active_scope, executors, models, QUOTA_WORDS, CLAUDE_QUOTA_WORDS
from . import claude_profile
from .development_scope import decode
from .private_stage import write, stop_private_group
from .profile import command, environment
from .release import ROOT, require_workspace_instructions
from .shared import process_identity
from .snapshot import read_regular

NONCE='interactive-start'
RETRY='interactive-retry-1'
RETRIES=(RETRY,'interactive-retry-2','interactive-retry-3')
# Further interactive starts exist ONLY as separately reviewed owner decisions bound in the active configuration
# (development.interactive_extensions, an ordered list). Each one names the start it follows and how that start really
# ended: `hold` (the third retry, 2026-09-22) or `task-refused` (the fourth retry: a task answer the frozen policy
# refused on a field the delivered text had not stated). The previous session's result and answer are bound by SHA256
# and never rewritten; the extension never fits a different ending. Not a general retry right.
EXTENSIONS=('interactive-retry-4','interactive-retry-5')
EXTENSION_KEYS={'nonce','after','previous_outcome','decision','decision_sha256','review','review_sha256'}
OUTCOMES=('hold','task-refused')
# Global Claude state that can confer authority. Everything else in that file is
# volatile bookkeeping the pinned TUI rewrites on every honest start (measured).
CLAUDE_AUTHORITY_KEYS=('hasTrustDialogAccepted','allowedTools','mcpServers','enabledMcpjsonServers',
                       'disabledMcpjsonServers','hasClaudeMdExternalIncludesApproved','mcpContextUris')
CLAUDE_GLOBAL_KEYS=('mcpServers','bypassPermissionsModeAccepted','customApiKeyResponses')


def binding_name(nonce):
    return 'interactive-retry.json' if nonce==RETRY else nonce+'.json'


def extensions(config):
    """The bound extra interactive starts of the active configuration, in order, each verified against its decision and
    review, or an empty tuple. The chain is fixed: each entry follows the previous nonce and names the outcome it follows."""
    bound=(config.get('development') or {}).get('interactive_extensions')
    if bound is None:return ()
    if not isinstance(bound,list) or not bound or len(bound)>len(EXTENSIONS):
        raise ValueError('Exact reviewed interactive extension list required')
    directory=Path(config['directory'])/'development-context';previous=RETRIES[-1]
    for index,entry in enumerate(bound):
        if (not isinstance(entry,dict) or set(entry)!=EXTENSION_KEYS or entry['nonce']!=EXTENSIONS[index] or entry['after']!=previous
                or entry['previous_outcome'] not in OUTCOMES or not all(isinstance(entry[k],str) and entry[k] for k in EXTENSION_KEYS)):
            raise ValueError('Exact reviewed interactive extension binding required')
        for name,expected in ((entry['decision'],entry['decision_sha256']),(entry['review'],entry['review_sha256'])):
            if Path(name).name!=name or host.sha(read_regular(directory,name))!=expected:
                raise ValueError('Interactive extension decision or review changed')
        review=decode(read_regular(directory,entry['review']))
        if (not isinstance(review,dict) or review.get('verdict')!='approved' or review.get('blocking_findings')!=[]
                or review.get('extends')!=entry['nonce'] or review.get('after')!=previous or review.get('previous_outcome',entry['previous_outcome'])!=entry['previous_outcome']
                or review.get('decision_sha256')!=entry['decision_sha256']):
            raise ValueError('Interactive extension is not separately approved')
        previous=entry['nonce']
    return tuple(bound)


def previous_end(scope,nonce,outcome):
    """How the start `nonce` really ended, never rewritten: `hold` = a completed session whose answer was hold;
    `task-refused` = a completed session whose answer was task and for which the host produced no draft (the frozen
    policy refused it, the refusal being the parent's recorded host diagnosis)."""
    stage=scope.directory/'calls'/nonce
    prior=read_regular(stage,'result.json');result=decode(prior)
    answer=read_regular(stage/'workspace','.scratch/answer.json');action=decode(answer).get('action')
    ended=(result.get('completed') is True and result.get('process_group_removed') is True and bool(result.get('provider',{}).get('thread_id')))
    if outcome=='hold':
        if not ended or action!='hold':raise ValueError('The extension follows only a completed interactive session that answered hold')
    elif outcome=='task-refused':
        if not ended or action!='task' or (scope.directory/'drafts'/nonce).exists():
            raise ValueError('The extension follows only a completed interactive session whose task answer the host refused (no draft exists)')
    else:raise ValueError('Unknown extension outcome')
    return prior,answer


def selected_nonce(scope,config=None):
    selected=NONCE
    for nonce in RETRIES:
        path=scope.directory/binding_name(nonce)
        if not path.exists():
            if any((scope.directory/(later+'.json')).exists() for later in (*RETRIES[RETRIES.index(nonce)+1:],*EXTENSIONS)):
                raise ValueError('Earlier interactive retry binding missing')
            return selected
        binding=decode(read_regular(scope.directory,path.name))
        if (set(binding)!={'previous','nonce','diagnosis','previous_result_sha256','input_sha256'}
                or binding['previous']!=selected or binding['nonce']!=nonce
                or not isinstance(binding['diagnosis'],str) or not binding['diagnosis'].strip()):
            raise ValueError('Exact host interactive retry binding required')
        previous=read_regular(scope.directory/'calls'/selected,'result.json')
        if (host.sha(previous)!=binding['previous_result_sha256']
                or decode(previous).get('completed') is not False
                or host.sha(read_regular(scope.directory/'calls'/nonce,'input.json'))!=binding['input_sha256']):
            raise ValueError('Interactive retry evidence changed')
        selected=nonce
    bound=extensions(config) if config is not None else None
    for index,nonce in enumerate(EXTENSIONS):
        path=scope.directory/binding_name(nonce)
        if not path.exists():
            if any((scope.directory/(later+'.json')).exists() for later in EXTENSIONS[index+1:]):
                raise ValueError('Earlier interactive extension binding missing')
            return selected
        binding=decode(read_regular(scope.directory,path.name))
        # The first extension's binding on disk was written by the release that knew only the hold ending and carries
        # no previous_outcome key; that ending IS hold. Every later binding names its ending explicitly.
        keys={'previous','nonce','diagnosis','previous_result_sha256','previous_answer_sha256','decision_sha256','review_sha256','input_sha256'}
        if index==0 and 'previous_outcome' not in binding:binding={**binding,'previous_outcome':'hold'}
        if (set(binding)!=keys|{'previous_outcome'}
                or binding['previous']!=selected or binding['nonce']!=nonce or binding['previous_outcome'] not in OUTCOMES
                or not isinstance(binding['diagnosis'],str) or not binding['diagnosis'].strip()):
            raise ValueError('Exact host interactive extension binding required')
        prior,answer=previous_end(scope,selected,binding['previous_outcome'])
        if (host.sha(prior)!=binding['previous_result_sha256'] or host.sha(answer)!=binding['previous_answer_sha256']
                or host.sha(read_regular(scope.directory/'calls'/nonce,'input.json'))!=binding['input_sha256']):
            raise ValueError('Interactive extension evidence changed')
        if bound is not None:
            entry=bound[index] if index<len(bound) else None
            if entry is None or (entry['decision_sha256'],entry['review_sha256'],entry['previous_outcome'])!=(binding['decision_sha256'],binding['review_sha256'],binding['previous_outcome']):
                raise ValueError('Interactive extension binding is not the activated one')
        selected=nonce
    return selected


def prepare_retry(expected,reason):
    scope,config=active_scope(expected);state=scope.inspect()
    previous=selected_nonce(scope,config)
    if (state['control']!='paused' or state['tasks'] or previous==EXTENSIONS[-1]
            or not isinstance(reason,str) or not reason.strip()):
        raise ValueError('Only explicit diagnosed pre-task paused interactive recovery')
    if previous in (RETRIES[-1],*EXTENSIONS[:-1]):
        return prepare_extension(scope,config,expected,reason,previous)
    nonce=RETRIES[0] if previous==NONCE else RETRIES[RETRIES.index(previous)+1]
    stage=scope.directory/'calls'/previous
    if not (stage/'result.json').exists():raise ValueError('Previous interactive attempt has not ended')
    prior=read_regular(stage,'result.json');result=decode(prior)
    ended=decode(read_regular(stage,'session-exit.json'))
    if (result.get('completed') is not False or result.get('process_group_removed') is not True
            or ended.get('process_absent') is not True or process_identity(ended['provider_pid'])):
        raise ValueError('Previous failed interactive process must be verifiably absent')
    try:os.killpg(ended['provider_pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Previous interactive process group remains')
    context,files=host.base_context(scope,config,'reconciliation',nonce,paused_interactive_recovery=True)
    request=host.prepare_call(expected,nonce,'driver','reconciliation',context,files)
    write(scope.directory/binding_name(nonce),{'previous':previous,'nonce':nonce,'diagnosis':reason,
        'previous_result_sha256':host.sha(prior),'input_sha256':request['input_sha256']})
    return request


def prepare_extension(scope,config,expected,reason,previous):
    """The next bound extra start after `previous` ended as its decision states. Nothing of that session is rewritten."""
    entry=next((e for e in extensions(config) if e['after']==previous),None)
    if entry is None:raise ValueError('No further interactive start: no reviewed extension follows '+previous)
    nonce=entry['nonce'];prior,answer=previous_end(scope,previous,entry['previous_outcome'])
    ended=decode(read_regular(scope.directory/'calls'/previous,'session-exit.json'))
    if ended.get('process_absent') is not True or process_identity(ended['provider_pid']):
        raise ValueError('Previous interactive process must be verifiably absent')
    try:os.killpg(ended['provider_pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Previous interactive process group remains')
    context,files=host.base_context(scope,config,'reconciliation',nonce,paused_interactive_recovery=True)
    request=host.prepare_call(expected,nonce,'driver','reconciliation',context,files)
    write(scope.directory/binding_name(nonce),{'previous':previous,'nonce':nonce,'previous_outcome':entry['previous_outcome'],'diagnosis':reason,
        'previous_result_sha256':host.sha(prior),'previous_answer_sha256':host.sha(answer),
        'decision_sha256':entry['decision_sha256'],'review_sha256':entry['review_sha256'],'input_sha256':request['input_sha256']})
    return request


def pending(expected):
    """The host-selected retry whose call never reached its consumed receipt, else None.

    Nothing was reserved or started for it, so delivering the same bound request
    again replays nothing; a refusal before consumption can never strand a slot.
    """
    scope,config=active_scope(expected);nonce=selected_nonce(scope,config);stage=scope.directory/'calls'/nonce
    if nonce==NONCE or (stage/'consumed.json').exists() or (stage/'result.json').exists():return None
    return {'contract_sha256':expected,'nonce':nonce,'input_sha256':host.sha(read_regular(stage,'input.json'))}


def retry_evidence(scope,nonce):
    """Every binding and every earlier attempt's actual end, for the whole selected chain."""
    chain=(NONCE,*RETRIES,*EXTENSIONS);files={}
    for index,earlier in enumerate(chain[:chain.index(nonce)]):
        files['interactive/RETRY_BINDING.json' if index==0 else 'interactive/RETRY%d_BINDING.json'%(index+1)]=read_regular(scope.directory,binding_name(chain[index+1]))
        for name in ('session-exit.json','result.json'):
            files['interactive/'+('previous-' if index==0 else 'retry%d-'%index)+name]=read_regular(scope.directory/'calls'/earlier,name)
        if chain[index+1] in EXTENSIONS:
            # The whole-goal reviewer sees the ending each extension follows (a hold, or a refused task), exactly as answered.
            files['interactive/retry%d-answer.json'%index]=read_regular(scope.directory/'calls'/earlier/'workspace','.scratch/answer.json')
    return files


ANSI=re.compile(rb'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][B0]|\x1b[=>]|\x1b\][^\x07]*\x07')
DONE=re.compile(r'done\s*\d{1,2}:\d{2}\s*(?:AM|PM)')
RESUME=re.compile(r'claude\s+--resume\s+([0-9a-f-]{36})')
ACKNOWLEDGED='Press Ctrl-C again to exit'
IDLE='❯'


def trigger_record(stage):
    """Why each Ctrl-C pair was sent, derived from the preserved bytes rather than asserted.

    Amendment section 4 requires every pair to be justified by a POSITIVELY OBSERVED idle prompt after the
    final completed turn. The operator types those bytes; the host only records them, so it cannot testify to
    the intent. What it can do is read back what its own recording contains, in the order the terminal wrote
    it, and refuse to produce a record where that order is not actually there.

    The load-bearing observation is the TUI's own answer to the FIRST 0x03. It writes 'Press Ctrl-C again to
    exit' only when there is nothing to interrupt; a busy session treats the same byte as an interrupt and says
    so instead. So that line, appearing after a completed turn and an idle prompt in an append-only stream, is
    the terminal itself reporting it was idle - not the host's account of it.
    """
    for name in ('operator-input.raw','terminal.raw','native-interactive-session.jsonl','session-exit.json'):
        if not (stage/name).is_file():
            # A missing piece is reported as one. Producing a record from the rest would justify the pair on
            # evidence that is not there.
            return {'available':False,'reason':'Preserved interactive evidence is incomplete: no '+name}
    operator=read_regular(stage,'operator-input.raw',limit=16384)
    if not operator or set(operator)!={3} or len(operator)%2:
        return {'available':False,'reason':'Preserved operator bytes are not whole Ctrl-C pairs',
                'operator_bytes_hex':operator.hex()}
    text=ANSI.sub(b'',read_regular(stage,'terminal.raw',limit=8*1024*1024)).decode('utf8','replace')
    pairs=len(operator)//2
    # EVERY pair, not the first one. Amendment section 4 asks each pair to be justified, and a record that
    # counted the pairs but checked only the first would assert justification the bytes do not carry. Each
    # pair leaves its own acknowledgement in the stream, because the terminal answers each FIRST Ctrl-C;
    # so the count of acknowledgements must equal the count of pairs, and each must follow a completed turn
    # and an idle prompt that come after the previous pair.
    acknowledgements=[]
    at=text.find(ACKNOWLEDGED)
    while at>=0:
        acknowledgements.append(at)
        at=text.find(ACKNOWLEDGED,at+len(ACKNOWLEDGED))
    if not acknowledgements:
        return {'available':False,'reason':'Terminal never acknowledged a first Ctrl-C as an idle exit request',
                'operator_bytes_hex':operator.hex(),'pairs':pairs,'verified_pairs':0}
    if len(acknowledgements)!=pairs:
        return {'available':False,'pairs':pairs,'verified_pairs':len(acknowledgements),
                'operator_bytes_hex':operator.hex(),
                'reason':'The preserved terminal acknowledges %d Ctrl-C pairs, but %d were recorded; a record '
                         'must not justify more pairs than the bytes show'%(len(acknowledgements),pairs)}
    order=[];previous=0
    for index,acknowledged in enumerate(acknowledgements,1):
        head=text[previous:acknowledged]
        completed=None
        for completed in DONE.finditer(head):pass
        if completed is None:
            return {'available':False,'pairs':pairs,'verified_pairs':index-1,
                    'operator_bytes_hex':operator.hex(),
                    'reason':'No completed turn is recorded before Ctrl-C pair %d'%index}
        idle=head.rfind(IDLE)
        if idle<completed.end():
            return {'available':False,'pairs':pairs,'verified_pairs':index-1,
                    'operator_bytes_hex':operator.hex(),
                    'reason':'No idle prompt is recorded between the completed turn and Ctrl-C pair %d'%index}
        order.append({'pair':index,
            'final completed turn, as the terminal printed it':completed.group(0),
            'offsets':{'completed_turn':previous+completed.start(),'idle_prompt':previous+idle,
                       'acknowledgement':acknowledged}})
        previous=acknowledged+len(ACKNOWLEDGED)
    # The summary block below quotes the LAST verified pair. Its offsets are taken from that pair's own
    # record, which already holds absolute positions. An earlier version re-searched a slice starting at the
    # match, which made the reported offset always 0 while the two beside it stayed absolute - an offset that
    # does not locate the text it is printed next to, in a record whose basis line invites exactly that check.
    last=order[-1]
    completed_quote=last['final completed turn, as the terminal printed it']
    completed_at=last['offsets']['completed_turn']
    idle=last['offsets']['idle_prompt'];acknowledged=last['offsets']['acknowledgement']
    rows=[decode(line) for line in read_regular(stage,'native-interactive-session.jsonl',
                                                limit=32*1024*1024).splitlines() if line.strip()]
    turns=[r for r in rows if r.get('type')=='assistant'
           and (r.get('message') or {}).get('stop_reason')=='end_turn']
    errors=[r for r in rows if r.get('type')=='error' or r.get('is_error')
            or (r.get('message') or {}).get('stop_reason')=='error']
    exit_record=decode(read_regular(stage,'session-exit.json'))
    session=exit_record.get('provider',{}).get('thread_id')
    resume=RESUME.search(text)
    final=turns[-1] if turns else None
    record={'available':bool(turns) and not errors and session is not None
                         and resume is not None and resume.group(1)==session
                         and final.get('sessionId')==session,
        'pairs':pairs,'verified_pairs':len(order),'per_pair':order,
        'operator_bytes_hex':operator.hex(),
        'session_id':session,
        'session_id_in_terminal':resume.group(1) if resume else None,
        'session_id_in_final_turn':final.get('sessionId') if final else None,
        'final_completed_turn':{'timestamp':final.get('timestamp'),'version':final.get('version'),
                                'model':(final.get('message') or {}).get('model'),
                                'stop_reason':(final.get('message') or {}).get('stop_reason')} if final else None,
        'completed_turns':len(turns),'provider_error_rows':len(errors),
        'observed_order':[
            {'what':'final completed turn, as the terminal printed it','quote':completed_quote,
             'terminal_offset':completed_at},
            {'what':'idle prompt after that turn','quote':IDLE,'terminal_offset':idle},
            {'what':'terminal acknowledging the first Ctrl-C as an idle exit request, not an interrupt',
             'quote':ACKNOWLEDGED,'terminal_offset':acknowledged}],
        'terminal_sha256':host.sha(read_regular(stage,'terminal.raw',limit=8*1024*1024)),
        'native_session_sha256':host.sha(read_regular(stage,'native-interactive-session.jsonl',limit=32*1024*1024)),
        'basis':'Offsets are into the ANSI-stripped preserved terminal, whose raw bytes hash to terminal_sha256. '
                'The stream is append-only, so a later offset was written later.'}
    if not record['available']:
        record['reason']=('No completed turn in the native session record' if not turns else
                          'The native session record contains a provider error row' if errors else
                          'The session the terminal and the final turn name is not the one the host recorded')
    return record


def claude_state():
    raw=read_regular(Path.home(),'.claude.json',limit=32*1024*1024)
    state=decode(raw)
    if not isinstance(state,dict) or not isinstance(state.get('projects',{}),dict):
        raise ValueError('Global Claude state is unreadable')
    return state


def claude_authority(state,workspace):
    """Authority that can reach THIS session: global keys and the delivered cwd's own ancestor chain.

    Other projects' entries belong to other sessions (the operator's own included)
    and honestly change meanwhile. Empty and absent are equal: an honest start may
    add a default entry for its cwd, while every grant is a non-empty value.
    """
    projects=state.get('projects',{});chain={}
    for parent in (workspace,*workspace.parents):
        entry=projects.get(str(parent))
        held={key:entry[key] for key in CLAUDE_AUTHORITY_KEYS if entry.get(key)} if isinstance(entry,dict) else {}
        if held:chain[str(parent)]=held
    held={key:state[key] for key in CLAUDE_GLOBAL_KEYS if state.get(key)}
    return host.sha(json.dumps({'global':held,'projects':chain},sort_keys=True).encode())


def claude_layers(workspace):
    # The pinned TUI shows a persistent trust dialog whose default is exit unless
    # an ancestor is already trusted. Never answer it and never write that state:
    # refuse here, before the call is consumed or any budget is reserved.
    projects=claude_state().get('projects',{})
    if not any(isinstance(projects.get(str(parent)),dict) and projects[str(parent)].get('hasTrustDialogAccepted') is True
               for parent in (workspace,*workspace.parents)):
        raise ValueError('No already trusted ancestor; the interactive trust dialog is never answered')
    for parent in (workspace,*workspace.parents):
        if parent==Path.home():break
        if (parent/'.claude').exists() or (parent/'.mcp.json').exists():
            raise ValueError('Project-local Claude layers require separate review')


def claude_interactive_command(workspace,prompt,session,model=None):
    claude_layers(workspace)
    return claude_profile.interactive_command(workspace,prompt,workspace/'.scratch/answer.json',session,model=model)


def objects(raw):
    rows=[decode(line) for line in raw.splitlines()]
    if not all(isinstance(row,dict) for row in rows):raise ValueError('Native session row is not an object')
    return rows


def claude_session(workspace,session):
    """Read only the native record named by the host-chosen session id.

    Measured: the pinned TUI honours --session-id and writes exactly
    <projects>/<directory derived from cwd>/<that id>.jsonl. Only names are
    matched; no other session's content is opened.
    """
    projects=Path.home()/'.claude/projects'
    found=sorted(projects.glob('*/'+session+'.jsonl')) if projects.is_dir() and not projects.is_symlink() else []
    if len(found)!=1 or found[0].is_symlink() or found[0].parent.is_symlink():
        raise ValueError('Exactly one actual completed interactive session required')
    raw=read_regular(found[0].parent,found[0].name,limit=8*1024*1024);rows=objects(raw)
    if ({r.get('sessionId') for r in rows if r.get('sessionId')}!={session}
            or {r.get('cwd') for r in rows if r.get('cwd')}!={str(workspace)}):
        raise ValueError('Interactive native session identity unavailable')
    return session,raw,'claude-interactive'


def claude_completed(rows, model=None):
    """(quota, reason): a completed turn is the final assistant end_turn with no API error row.

    The model is the one this session was STARTED with, so the check measures the same value the launch
    used. Verifying a selected-model session against the profile default would reject a session that did
    exactly what it was told - and an interactive start is the scarcest resource in the mission.
    """
    failed=[r for r in rows if r.get('isApiErrorMessage') is True or r.get('type')=='error']
    if failed:
        # Only the error's own wording; never usage fields, paths or earlier agent text.
        parts=[str(r.get('error') or '') for r in failed]
        for r in failed:
            content=(r.get('message') or {}).get('content') if isinstance(r.get('message'),dict) else None
            parts+=[content] if isinstance(content,str) else [str(part.get('text') or '') for part in content or [] if isinstance(part,dict)]
        text=' '.join(parts).lower()
        return any(word in text for word in CLAUDE_QUOTA_WORDS),'Interactive provider error'
    assistants=[r for r in rows if r.get('type')=='assistant']
    if not assistants or assistants[-1].get('message',{}).get('stop_reason')!='end_turn':
        return False,'Interactive session has no actual completed turn'
    if ({r.get('version') for r in rows if r.get('version')}!={claude_profile.VERSION}
            or {r.get('message',{}).get('model') for r in assistants}!={claude_profile.selected_model(model)}):
        return False,'Interactive session did not use the pinned CLI and model'
    tools={part.get('name') for r in assistants for part in (r.get('message',{}).get('content') or [])
           if isinstance(part,dict) and part.get('type')=='tool_use'}
    if tools-{'Read','Write'}:return False,'Unqualified interactive tool use'
    return False,None


def interactive_command(workspace,prompt,model=None):
    # A process-local table avoids dotted-path quoting ambiguity. Never answer
    # the TUI's persistent trust prompt or change the user's config. Refuse any
    # project-local executable/config layer that trust could newly enable.
    for parent in (workspace,*workspace.parents):
        if parent==Path.home():break
        if (parent/'.codex').exists():
            raise ValueError('Project-local Codex layers require separate review')
    argv=command(workspace,writable=False,model=model);cut=argv.index('exec')
    trust='projects={'+json.dumps(str(ROOT))+'={trust_level="trusted"}}'
    # The pinned CLI otherwise increments a global model-introduction counter.
    # Suppress that UI bookkeeping for this process; do not rebind global guards.
    return argv[:cut]+['-c',trust,'-c','tui.show_tooltips=false','--no-alt-screen','-C',str(workspace),prompt]


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


def preflight(expected):
    """Every refusal that needs no prepared call, BEFORE a slot is bound or the scope resumed."""
    if not os.isatty(sys.stdin.fileno()):
        raise ValueError('A real interactive terminal is required; exec is not this qualification')
    scope,config=active_scope(expected);provider=executors(config)['interactive']
    if provider=='claude':
        claude_profile.require_subscription();claude_layers(scope.directory/'calls')
    return provider


def prepare(expected):
    scope,config=active_scope(expected)
    context,files=host.base_context(scope,config,'reconciliation','interactive-a')
    return host.prepare_call(expected,NONCE,'driver','reconciliation',context,files)


def execute(request):
    if not os.isatty(sys.stdin.fileno()):
        raise ValueError('A real interactive terminal is required; exec is not this qualification')
    scope,config=active_scope(request['contract_sha256']);nonce=selected_nonce(scope)
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
            'Your file tools cannot list directories: CONTEXT.json delivered_files is the complete inventory of this workspace, '
            'with the exact path of the frozen recipe VERIFICATION_RECIPE.py and of the result readers under tools/; open those paths, never guess names. '
            'Read the actual inputs and frozen recipe; reason about necessity, scope and verification. '
            'Write your structured driver answer matching OUTPUT_SCHEMA.json to .scratch/answer.json. '
            'This is data, not executable acceptance. Do not prepare B, implement code, start tasks or signal Runtime. '
            'Your draft will receive fresh independent review. End your turn with your concrete rationale; '
            'the operator will close this interactive session before the native chain continues.')
    selected=executors(config)['interactive'];authority_before=None;session=None
    # One value for this session: the launch below and the completion check further down must never
    # measure different models, or a session that ran exactly what it was told would be recorded as a
    # failure and burn an interactive start.
    chosen_model=models(config)[selected]
    if selected=='claude':
        claude_profile.require_subscription();session=str(uuid.uuid4())
        prompt=prompt.replace('the operator will close this interactive session','the operator will close this interactive session (two Ctrl-C)')
        argv=claude_interactive_command(workspace,prompt,session,model=chosen_model);authority_before=claude_authority(claude_state(),workspace)
    else:
        argv=interactive_command(workspace,prompt,model=chosen_model)
    write(stage/'consumed.json',{'nonce':nonce,'input_sha256':request['input_sha256']})
    write(stage/'interactive-input.json',{'prompt':prompt,'provider':selected,'session_id':session,'command_kind':'interactive CLI without exec subcommand',
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
        identity,history,session_source=(claude_session(workspace,session) if selected=='claude'
                                         else actual_session(workspace,started,require_complete=False))
        with (stage/'native-interactive-session.jsonl').open('xb') as stream:stream.write(history)
        rows=objects(history)
        if selected=='claude':
            quota,failure=claude_completed(rows,model=chosen_model)
            if not quota and failure is None and claude_authority(claude_state(),workspace)!=authority_before:
                failure='Global Claude authority state changed during the interactive session'
        else:
            errors=json.dumps([r for r in rows if r.get('type') in ('error','turn.failed')
                or r.get('type')=='event_msg' and r.get('payload',{}).get('type') in ('error','turn_failed')]).lower()
            quota=any(word in errors for word in QUOTA_WORDS)
            failure=None if quota or any(r.get('type')=='event_msg' and r.get('payload',{}).get('type')=='task_complete' for r in rows) else 'Interactive session has no actual completed turn'
        if quota:
            if scope.inspect()['control'] in ('active','paused'):
                scope.control('quota','Native interactive provider reported quota/access failure; retain history')
            raise ValueError('Interactive provider quota/access unavailable')
        if failure:raise ValueError(failure)
        answer=decode(read_regular(workspace,'.scratch/answer.json'))
        provider={'thread_id':identity,'valid_terminal':True,'interactive':True}
        for name,expected in data['workspace_sha256'].items():
            if host.sha(read_regular(workspace,name))!=expected:raise ValueError('Bound interactive context changed')
        require_workspace_instructions(workspace)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:reason=reason or str(error)
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
