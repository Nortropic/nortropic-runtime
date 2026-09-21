"""Independent whole-goal examination from actual saved/native evidence.

Qualification evidence is host-selected, private and outside candidate writes.
Its presence is not approval. A fresh counted agent compares it with G1–G10;
only a separate approval allows the host to close this one finite scope.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from temporalio.client import Client

from . import development_host as host
from .development_scope import decode, identifier
from .inspection import inspect
from .integration import Publisher, digest
from .obligation import NAME, status
from .private_stage import write
from .snapshot import read_regular
from .task import load, task_directory
from .targets import OFFICE


async def native_evidence(task_ids):
    client=await Client.connect('127.0.0.1:7339',namespace='nortropic-runtime')
    histories={}
    for name in ['office-ap11',*task_ids]:
        history=await client.get_workflow_handle(name).fetch_history()
        histories[name]=[MessageToDict(event) for event in history.events]
    watch=await client.get_schedule_handle(NAME).describe()
    return histories,status(watch)


def prepare(scope,config,key):
    directory=scope.directory/'qualification'
    if not (directory/'index.json').is_file():
        return {'proof_wait':True,'reason':'Whole-goal qualification evidence not yet preserved'}
    index=decode(read_regular(directory,'index.json'))
    if (set(index)!={'observed_at','files','scope'} or index['scope']!='G1-G10'
            or not isinstance(index['files'],dict) or not index['files']):
        raise ValueError('Bound selected whole-goal evidence required')
    files={}
    for name,expected in index['files'].items():
        if Path(name).name!=name or not name.endswith(('.md','.json')):
            raise ValueError('Only bounded selected qualification text')
        content=read_regular(directory,name)
        if host.sha(content)!=expected:raise ValueError('Qualification evidence changed')
        files['qualification/'+name]=content
    files['qualification/index.json']=read_regular(directory,'index.json')
    state=scope.inspect()
    if set(state['integrated'])!={'reconciliation','handoff'}:
        raise ValueError('Both actual named integrations are required before whole-goal review')
    reports={};receipts={};task_ids=[]
    for work,event in state['integrated'].items():
        task=load(event['task']);task_ids.append(task['id']);report=inspect(task['id']);receipt=event['receipt']
        if report.get('verified_delivery') is not True or report.get('integration')!=receipt:
            raise ValueError('Actual saved task delivery is inconsistent')
        workspace=task_directory(task['id'])/report['state']['results'][-1]['workspace_name']
        publisher=Publisher(workspace,OFFICE)
        actual=publisher.reconcile(publisher.api('pulls/'+receipt['url'].rsplit('/',1)[1]),
            {'candidate':receipt['candidate'],'base':task['base']},receipt['tree'])
        if actual!=receipt:raise ValueError('Actual remote integration differs')
        reports[work]=report;receipts[work]=receipt
    histories,watch=asyncio.run(asyncio.wait_for(native_evidence(task_ids),20))
    # Actual full histories stay private. The model receives them when bounded;
    # excess is unavailable, never silently truncated into a positive review.
    files['NATIVE_HISTORY.json']=json.dumps(histories).encode()
    files['ACTUAL_REPORTS.json']=json.dumps(reports).encode()
    files['ACTUAL_REMOTE.json']=json.dumps(receipts).encode()
    files['ACTUAL_AP10.json']=json.dumps(watch,default=str).encode()
    files['SCOPE.json']=json.dumps(state).encode()
    files['SCOPE_JOURNAL.json']=json.dumps([decode(line) for line in read_regular(scope.directory,'journal.jsonl').splitlines()]).encode()
    from .development_interactive import selected_nonce, NONCE
    nonce=selected_nonce(scope);stage=scope.directory/'calls'/nonce
    if nonce!=NONCE:
        files['interactive/RETRY_BINDING.json']=read_regular(scope.directory,'interactive-retry.json')
        for name in ('session-exit.json','result.json'):
            files['interactive/previous-'+name]=read_regular(scope.directory/'calls'/NONCE,name)
    for name in ('input.json','interactive-input.json','session-exit.json','result.json'):
        files['interactive/'+name]=read_regular(stage,name)
    files['interactive/OPERATOR_INPUT.json']=json.dumps({'bytes_hex':read_regular(stage,'operator-input.raw',limit=16384).hex()}).encode()
    for name in ('authority.md','goal.md'):
        files[name]=read_regular(Path(config['directory'])/'development-context',name)
    files['AGENTS.md']=read_regular(Path(config['directory'])/'office','AGENTS.md')
    context={'remaining_action':'Independently examine entire actual G1-G10 chain and approve closure or identify exact gaps',
        'observed_at':datetime.now(timezone.utc).isoformat(),'runtime_revision':config['runtime_revision'],
        'office_revision':config['office_revision'],'config_sha256':config['config_sha256'],
        'qualification_index_sha256':host.sha(read_regular(directory,'index.json')),
        'closure_condition':'Approval permits only stopping office-ap11 after this review. Host must read back stopped scope; AP10 stays active. No next goal.'}
    return host.prepare_call(scope.expected,key,'final-review','goal',context,files)


def close(scope,config,nonce):
    result=host.call_result(scope,nonce,'final-review')
    if not host.policy(config).review(result['answer']):
        scope.control('paused','Whole-goal review not approved; preserve specific evidence gaps')
        return {'approved':False,'review':nonce,'decision':result['answer'],'whole_goal_complete':False}
    reviewer=result['provider']['thread_id']
    reports=decode(read_regular(scope.directory/'calls'/identifier(nonce)/'workspace','ACTUAL_REPORTS.json'))
    prior_runs=set()
    for report in reports.values():
        state=report.get('state',{})
        prior_runs.update(r['thread_id'] for r in state.get('results',[]) if r.get('thread_id'))
        for review in [state.get('review',{}),*(r.get('result',{}) for r in state.get('reviews',[]))]:
            if isinstance(review,dict) and review.get('reviewer_run'):prior_runs.add(review['reviewer_run'])
        if report.get('review_run'):prior_runs.add(report['review_run'])
    if reviewer in prior_runs:
        raise ValueError('Whole-goal reviewer participated in an actual child implementation/review')
    for call in scope.inspect()['calls']:
        if call['nonce']==nonce:continue
        path=scope.directory/'calls'/identifier(call['nonce'])/'result.json'
        if path.is_file() and decode(read_regular(path.parent,path.name)).get('provider',{}).get('thread_id')==reviewer:
            raise ValueError('Whole-goal review must use a fresh independent session')
    # The model does not control this state transition or modify its mandate.
    scope.control('stopped','Independent whole-goal review approved; AP11 finite application closed')
    final={'approved':True,'whole_goal_complete':True,'review':nonce,'reviewer':reviewer,
           'observed_at':datetime.now(timezone.utc).isoformat(),'config_sha256':config['config_sha256'],
           'runtime_revision':config['runtime_revision'],'office_revision':config['office_revision'],
           'scope':scope.inspect(),'ap10_action':'unchanged; no stop, pause or schema mutation called'}
    if final['scope']['control']!='stopped':raise ValueError('Finite scope did not close')
    write(scope.directory/'final.json',final)
    return final
