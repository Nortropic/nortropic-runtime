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


# A delivered file is read back with read_regular's 262144 byte bound, and prepare_call refuses a bundle over
# 2 MiB. The native history is larger than one file may be but smaller than the bundle allows, so it is SPLIT
# rather than shortened: the criteria that rest on it - the ordered chain, the parent's untimed waits, the
# interruptions survived, and the absence of any signal inside the interval whose independence is claimed -
# need the events themselves. Measured 2026-09-22: 1320445 bytes over 2040 events, largest single event 46690.
HISTORY_PART_BYTES = 240*1024
BUNDLE_BYTES = 2*1024*1024
# Held back from the room the parts may claim, because the index is delivered too. An ESTIMATE, not a limit:
# measured on the real material the index is about 3 KB, and it grows with each part and each recorded gap. If it
# ever outgrows this, the package simply eats into the reserve the caller keeps; only the reader's own bound can
# fail a delivery.
INDEX_BYTES = 32*1024


def history_parts(histories, room):
    """The ACTUAL native history as ordered, hash-bound parts a reader can open, plus an index.

    Never a summary and never a silent shortening. Anything that cannot be delivered stays an explicit gap in
    the index, named by event id, so a reader sees the hole instead of reading a part as the whole. The full
    original is not delivered; its hash is recorded so every part ties back to it.

    `room` is the bytes the rest of the bundle leaves. Parts are built oldest-first and dropped oldest-first if
    they do not fit, because the criteria that depend on this material concern the most recent stretch.
    """
    ordered, index = [], {
        'note': 'The complete native history of each workflow, split into ordered parts. Each part is a whole '
                'JSON object with its own events; read them in the order given. The full original stays '
                'private and is never delivered shortened - see gaps.',
        'part_bytes_bound': HISTORY_PART_BYTES, 'workflows': {}}
    for name, events in histories.items():
        whole = json.dumps(events).encode()
        entry = {'events': len(events), 'bytes': len(whole), 'complete_sha256': host.sha(whole),
                 'parts': [], 'gaps': []}
        batches, batch, size = [], [], 0
        for event in events:
            one = len(json.dumps(event).encode())
            if one > HISTORY_PART_BYTES:
                # Delivered as a hole, never shortened into something that could read as complete.
                if batch:
                    batches.append(batch); batch, size = [], 0
                entry['gaps'].append({'event_id': event.get('eventId'), 'event_type': event.get('eventType'),
                                      'bytes': one, 'delivered': False,
                                      'reason': 'one event exceeds the per-file delivery bound; it is not '
                                                'delivered and not shortened'})
                continue
            if size + one > HISTORY_PART_BYTES:
                batches.append(batch); batch, size = [], 0
            batch.append(event); size += one
        if batch:
            batches.append(batch)
        label = ''.join(c if c.isalnum() else '-' for c in name)
        for number, part in enumerate(batches, 1):
            body = json.dumps({'workflow': name, 'part': number, 'of': len(batches),
                               'first_event_id': part[0].get('eventId'), 'last_event_id': part[-1].get('eventId'),
                               'events': part}).encode()
            ordered.append({'workflow': name, 'file': 'NATIVE_HISTORY_%s_%d.json' % (label, number), 'body': body,
                            'part': number, 'of': len(batches), 'events': len(part),
                            'first_event_id': part[0].get('eventId'), 'last_event_id': part[-1].get('eventId'),
                            # The criteria are stated in TIME - untimed waits, and the absence of a signal inside a
                            # named interval - so a reader must be able to find the right part without opening each.
                            'first_event_time': part[0].get('eventTime'), 'last_event_time': part[-1].get('eventTime')})
        index['workflows'][name] = entry
    # Room is claimed NEWEST first, so a shortfall costs the earliest events and keeps the latest: the criteria
    # that rest on this material - the interval whose independence is claimed, and the integrations that closed
    # it - are at the end of the history. The index still lists what was delivered in original order.
    #
    # Every workflow's newest part is claimed before any workflow's second-newest, so a shortfall tends to shorten
    # each of them from its own start rather than serving one at another's expense. Relying on the order
    # `histories` happens to have would make the LAST workflow the best served and the parent the worst - the
    # opposite of this policy, since the parent is the one whose waits, interruptions and absent signals the
    # criteria rest on. This is a priority, not a guarantee: a workflow whose newest part alone is larger than
    # what is left still gets nothing, and the index then says so as a gap like any other.
    priority = list(histories)
    ordered.sort(key=lambda item: (item['of'] - item['part'], priority.index(item['workflow'])))
    # The index is a delivered file like any other: it is held back from the room the parts may claim, and it is
    # checked against the same per-file bound below. Exempting it would reproduce the very defect this corrects.
    room -= INDEX_BYTES
    used = 0
    for item in ordered:
        if used + len(item['body']) > room:
            index['workflows'][item['workflow']]['gaps'].append(
                {'part': item['part'], 'of': item['of'], 'events': item['events'], 'delivered': False,
                 'first_event_id': item['first_event_id'], 'last_event_id': item['last_event_id'],
                 'reason': 'the bundle had no room left for this part; it is a REVIEW GAP, not an absence of events'})
            continue
        used += len(item['body'])
        index['workflows'][item['workflow']]['parts'].append(
            {'file': item['file'], 'part': item['part'], 'of': item['of'], 'events': item['events'],
             'first_event_id': item['first_event_id'], 'last_event_id': item['last_event_id'],
             'first_event_time': item['first_event_time'], 'last_event_time': item['last_event_time'],
             'sha256': host.sha(item['body'])})
        item['delivered'] = True
    files = {item['file']: item['body'] for item in ordered if item.get('delivered')}
    for entry in index['workflows'].values():
        entry['parts'].sort(key=lambda p: p['part'])
        entry['gaps'].sort(key=lambda g: g.get('part') or 0)
    for name, entry in index['workflows'].items():
        entry['delivered_events'] = sum(p['events'] for p in entry['parts'])
        entry['complete'] = entry['delivered_events'] == entry['events'] and not entry['gaps']
        if not entry['complete']:
            entry['warning'] = ('This workflow is NOT completely delivered. Treat the missing events as an '
                                'explicit review gap; do not read the delivered parts as the whole history.')
    index['complete'] = all(e['complete'] for e in index['workflows'].values())
    body = json.dumps(index, indent=1).encode()
    if len(body) > HISTORY_PART_BYTES:
        # An index a reader cannot open is worse than no split at all: the parts would be unnavigable and their
        # coverage unstated. This bound is the READER's, not the allowance above: the allowance is a budget
        # estimate held back from the parts, and an index that outgrows it only eats into the caller's reserve,
        # which is not a reason to fail a preparation whose index the receiver would have accepted.
        raise ValueError('Native history index exceeds its delivery bound: %d bytes' % len(body))
    files['NATIVE_HISTORY_INDEX.json'] = body
    return files


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
    # The actual full histories stay private. They are delivered SPLIT into ordered hash-bound parts, built last
    # so the room they get is measured against everything else rather than guessed; one file may not exceed
    # read_regular's bound and the bundle may not exceed prepare_call's. Marking oversized history unavailable
    # would be correct error handling but would not be a reviewable basis, so the events themselves go out.
    files['ACTUAL_REPORTS.json']=json.dumps(reports).encode()
    files['ACTUAL_REMOTE.json']=json.dumps(receipts).encode()
    files['ACTUAL_AP10.json']=json.dumps(watch,default=str).encode()
    files['SCOPE.json']=json.dumps(state).encode()
    files['SCOPE_JOURNAL.json']=json.dumps([decode(line) for line in read_regular(scope.directory,'journal.jsonl').splitlines()]).encode()
    # Every answer the HOST itself gave to a diagnosis. These are operator interventions, and one of them can let a
    # host-interrupted review be re-run, so the whole-goal review must see them as such and not have to infer them
    # from signal payloads in the native history.
    files['HOST_ANSWERS.json']=json.dumps(host.host_answers(scope)).encode()
    from .development_interactive import selected_nonce, retry_evidence
    nonce=selected_nonce(scope,config);stage=scope.directory/'calls'/nonce
    files.update(retry_evidence(scope,nonce))
    for name in ('input.json','interactive-input.json','session-exit.json','result.json'):
        files['interactive/'+name]=read_regular(stage,name)
    files['interactive/OPERATOR_INPUT.json']=json.dumps({'bytes_hex':read_regular(stage,'operator-input.raw',limit=16384).hex()}).encode()
    for name in ('authority.md','goal.md'):
        files[name]=read_regular(Path(config['directory'])/'development-context',name)
    files['AGENTS.md']=read_regular(Path(config['directory'])/'office','AGENTS.md')
    amended=host.goal_amendments(config,decode(read_regular(scope.directory,'contract.json')));files.update(amended)
    # Last, against the real remaining room. The reserve covers what prepare_call adds after this point: the
    # output schema and CONTEXT.json, whose delivered-file inventory grows with every part named here.
    files.update(history_parts(histories,BUNDLE_BYTES-sum(len(v) for v in files.values())-64*1024))
    context={'goal_amendments':host.amendment_notice(amended),'remaining_action':'Independently examine entire actual G1-G10 chain and approve closure or identify exact gaps',
        'observed_at':datetime.now(timezone.utc).isoformat(),'runtime_revision':config['runtime_revision'],
        'office_revision':config['office_revision'],'config_sha256':config['config_sha256'],
        'qualification_index_sha256':host.sha(read_regular(directory,'index.json')),
        'native_history':'Delivered SPLIT across NATIVE_HISTORY_<workflow>_<n>.json files. Read '
            'NATIVE_HISTORY_INDEX.json first: it gives each workflow its event count, the hash of the complete '
            'original, the parts in order with their own hashes and event-id ranges, and any gap. A part is a '
            'slice, never a summary; where the index reports a gap, treat it as missing evidence rather than '
            'reading the delivered parts as the whole history.',
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
