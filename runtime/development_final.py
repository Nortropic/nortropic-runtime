"""Independent whole-goal examination from actual saved/native evidence.

Qualification evidence is host-selected, private and outside candidate writes.
Its presence is not approval. A fresh counted agent compares it with G1–G10;
only a separate approval allows the host to close this one finite scope.
"""
import asyncio
import base64
from datetime import datetime, timezone
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from temporalio.client import Client

from .candidate import git
from . import development_host as host
from .development_scope import decode, identifier
from .inspection import inspect
from .integration import Publisher, digest
from .obligation import NAME, status
from .private_stage import write
from .release import ROOT
from .snapshot import read_regular
from . import development_assessment as assessment
from .targets import OFFICE, RUNTIME, repository
from .task import load, task_directory


# A delivered file is read back with read_regular's 262144 byte bound, and prepare_call refuses a bundle over
# 2 MiB. The native history is larger than one file may be but smaller than the bundle allows, so it is SPLIT
# rather than shortened: the criteria that rest on it - the ordered chain, the parent's untimed waits, the
# interruptions survived, and the absence of any signal inside the interval whose independence is claimed -
# need the events themselves. Measured 2026-09-22: 1320445 bytes over 2040 events, largest single event 46690.
# Deliberately well under the per-file bound. A part is claimed whole or not at all, so the part size is
# also the granularity of any shortfall: at 240 KB a package three kilobytes short lost six hundred events,
# which is a bad way to spend a rounding error.
HISTORY_PART_BYTES = 200*1024
BUNDLE_BYTES = 2*1024*1024
# Held back from the room the parts may claim, because the index is delivered too. An ESTIMATE, not a limit:
# measured on the real material the index is about 3 KB, and it grows with each part and each recorded gap. If it
# ever outgrows this, the package simply eats into the reserve the caller keeps; only the reader's own bound can
# fail a delivery.
# Measured at about 8 KB for this package. Kept close to that: a generous allowance is not free, because
# every byte held back here is a byte the events cannot have, and a part is claimed whole or not at all.
INDEX_BYTES = 10*1024
# Measured with the whole-goal reviewer's own file reader on this goal's own history: it refused a single line
# of 81837 bytes as "79468 tokens exceeds maximum allowed tokens (25000)". Offset and limit are LINE based, so a
# line above that bound cannot be sliced at all - splitting the file does not help, because the event is the
# line. An event over this threshold therefore also gets a readable companion; the part keeps it verbatim.
# 22000 bytes is about 21400 tokens by the ratio that refusal measured (79468 tokens for 81837 bytes), a
# margin of roughly one seventh against the reader's 25000. Set closer to the bound and a denser line could
# cross it; set lower and companions eat room the events themselves need.
READER_LINE_BYTES = 22000
# read_regular's own per-file bound, the one that refused the first whole-history delivery. Named here
# so the companion check and the part check cannot drift apart.
READ_BOUND = 262144
# The release revision's own isolated proofs, delivered as source so a reviewer holds the exact text whose recorded
# run the selected qualification evidence reports. Source alone is not a run: each one's run record, against this
# same revision, is a qualification record. Read from the ACTIVE release's runtime revision, never a working copy.
PROOFS = ('scripts/test_development_scope.py', 'scripts/test_development_control.py',
          'scripts/test_development_workflow.py', 'scripts/test_development_final.py',
          'scripts/test_development_host.py', 'scripts/test_development_model.py',
          'scripts/test_development_binding.py', 'scripts/test_goal_amendment.py',
          'scripts/test_shared_service.py', 'scripts/test_claude_roles.py', 'scripts/test_claude_driver.py',
          'scripts/test_model_binding.py', 'scripts/test_delivery_gates.py', 'scripts/test_assessment_path.py',
          'scripts/test_development_assessment.py')


def readable_json(value):
    """A derived JSON delivery printed over short lines.

    The recurring defect behind two whole-goal findings was not any one file: host-derived JSON was written with
    json.dumps on ONE line, which every byte check passes and the reviewer's line-based reader cannot open once the
    line is past its bound. Every derived JSON file therefore goes out through this, and readable_delivery() refuses
    a package in which any delivered line is still past that bound.
    """
    return json.dumps(value, indent=1, ensure_ascii=False, default=str).encode()


def readable_delivery(files):
    """Refuse a package the reviewer could not actually read, instead of handing it over.

    Every line of every delivered file must be within READER_LINE_BYTES, and every file within READ_BOUND. The one
    exception is a verbatim native history part: an event past the bound stays in its part verbatim, and is
    accepted only where the index records it as an unreadable line with its readable companion or its stated gap.
    """
    index = json.loads(files.get('NATIVE_HISTORY_INDEX.json', b'{"workflows": {}}'))
    parts = {part['file']: part for entry in index.get('workflows', {}).values() for part in entry.get('parts', [])}
    for name, body in files.items():
        if len(body) > READ_BOUND:
            raise ValueError('Delivered file %s is %d bytes, past the per-file bound %d' % (name, len(body), READ_BOUND))
        covered = {u.get('line') for u in parts[name].get('unreadable_lines', [])} if name in parts else set()
        for number, line in enumerate(body.split(b'\n'), 1):
            if len(line.rstrip(b',')) > READER_LINE_BYTES and number not in covered:
                raise ValueError('Delivered file %s has a line of %d bytes at line %d, past what the reviewer can '
                                 'open' % (name, len(line), number))
    return files


def owner_of(nonce, identities):
    """The run identity whose counted-key namespace this nonce is in: the longest matching prefix."""
    from .development_workflow import key_prefix
    matches = [name for name in identities if nonce.startswith(key_prefix(name))]
    return max(matches, key=len) if matches else None


def whole_goal_reviews(scope, config, records):
    """Every whole-goal review this commitment has had, in journal order, from the host's own preserved records.

    A completed review is delivered with its answer verbatim, so a later assessment holds the verdicts it follows
    rather than a description of them. A review that did not complete is delivered as what the host measured about
    it - its result record's scalars and the size and hash of the stream it left - and never with that stream's
    content: an interrupted reviewer's partial reading is not evidence for, and must not steer, the next one.
    """
    sequences = {}
    for row in records:
        event = row['event']
        if event.get('kind') in ('call', 'launch', 'started') and event.get('nonce'):
            sequences.setdefault(event['nonce'], {})[event['kind']] = row['sequence']
    identities = assessment.identities(config)
    reviews = []
    for call in scope.inspect()['calls']:
        if call.get('role') != 'final-review':
            continue
        nonce = call['nonce']; stage = scope.directory / 'calls' / identifier(nonce)
        entry = {'nonce': nonce, 'identity': owner_of(nonce, identities), 'journal': sequences.get(nonce, {})}
        if (stage / 'result.json').is_file():
            result = decode(read_regular(stage, 'result.json'))
            entry['result'] = {key: result.get(key) for key in ('completed', 'reason', 'process_group_removed',
                                                                'model_started', 'elapsed_seconds')}
            entry['session'] = (result.get('provider') or {}).get('thread_id')
            if result.get('completed') is True:
                entry['answer'] = result.get('answer')
        else:
            entry['result'] = None
            entry['note'] = 'No preserved result for this reservation; it stays consumed and is not a verdict.'
        if (stage / 'events.jsonl').is_file():
            stream = read_regular(stage, 'events.jsonl', limit=1024*1024)
            entry['stream'] = {'bytes': len(stream), 'lines': stream.count(b'\n'), 'sha256': host.sha(stream)}
        reviews.append(entry)
    return {'note': 'Every whole-goal review of this commitment in journal order, read from the host\'s own preserved '
                    'stage records. journal gives the scope journal sequence of its reservation, launch and start. A '
                    'completed review carries its answer verbatim; one that did not complete carries only what the '
                    'host measured about it, never its partial stream.', 'reviews': reviews}


def readable_event(event):
    """The same event, re-serialised so a line-based reader can page through it.

    Temporal carries payloads as base64 of json/plain, which is what makes these lines enormous and opaque: the
    bytes are there and none of them can be read. Here the payload is decoded into real structure and printed
    over many short lines, and the base64 it came from is recorded by hash so the copy stays tied to the
    original. This is a RE-SERIALISATION for reading. It is not byte-identical to the event and is never offered
    as the original; the verbatim event stays in its part.
    """
    def convert(value):
        if isinstance(value, dict):
            out = {}
            for key, inner in value.items():
                if key == 'data' and isinstance(inner, str):
                    try:
                        out['data_decoded'] = json.loads(base64.b64decode(inner))
                        out['data_base64_sha256'] = host.sha(inner.encode())
                        continue
                    except Exception:                     # noqa: BLE001 - anything undecodable stays as it was
                        pass
                out[key] = convert(inner)
            return out
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value
    return json.dumps(convert(event), indent=1, ensure_ascii=False).encode()

def map_allowance(histories):
    """Exactly how much room the location maps need, computed rather than guessed.

    A guessed per-row bound is wrong in the direction that matters: too generous, and the parts lose room
    they actually had, which is how a delivery ends up incomplete for no reason. Every row holds the event's
    id, type and time - all known here - plus the part file name and a line number, which are not known
    until the parts are allocated but are bounded by the longest name this workflow can produce and a line
    number no larger than its own event count.
    """
    total = 0
    for name, events in histories.items():
        for event in events:
            row = {'id': event.get('eventId'), 'type': event.get('eventType'), 'time': event.get('eventTime'),
                   'line': len(events) + 2}
            total += len(json.dumps(row, separators=(',', ':')).encode()) + 1
        total += len('[\n]\n')
    return total


def history_parts(histories, room):
    """The ACTUAL native history as ordered, hash-bound parts a reader can open, plus an index.

    Never a summary and never a silent shortening. Anything that cannot be delivered stays an explicit gap in
    the index, named by event id, so a reader sees the hole instead of reading a part as the whole. The full
    original is not delivered; its hash is recorded so every part ties back to it.

    `room` is the bytes the rest of the bundle leaves. Parts are built oldest-first and dropped oldest-first if
    they do not fit, because the criteria that depend on this material concern the most recent stretch.
    """
    ordered, index = [], {
        'note': 'The complete native history of each workflow, split into ordered parts. The full original '
                'stays private and is never delivered shortened - see gaps.',
        'how_to_read': 'Each part is a JSON array printed with ONE WHOLE EVENT PER LINE, so a line-based '
                       'reader can page through it with an offset and a limit instead of having to open the '
                       'file at once. Line 1 is "[" and the last line is "]"; event N of a part is on line '
                       'N+1. NATIVE_HISTORY_MAP_<workflow>.json lists every event id with its type, its time '
                       'and the part file and line it is on, so an event can be found without opening every '
                       'part. The map is a LOCATION index, derived mechanically from the same events; it is '
                       'not a summary and it never replaces reading the event itself. Map rows write the '
                       'event type WITHOUT its EVENT_TYPE_ prefix, which every type carries; the events '
                       'themselves keep the full type verbatim.',
        'part_bytes_bound': HISTORY_PART_BYTES, 'workflows': {}}
    entry_events = dict(histories)
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
            # A JSON array printed with one whole event per line: still one valid JSON document, but a
            # line-based reader can page through it. The previous delivery was a single line, which passed the
            # host's byte check and left the whole-goal reviewer unable to open a single event.
            body = ('[\n' + ',\n'.join(json.dumps(e, separators=(',', ':')) for e in part) + '\n]\n').encode()
            # Types are written without their EVENT_TYPE_ prefix: every Temporal event type carries it, so it
            # is eleven bytes of nothing on every row, and the map is the one file whose size is a pure tax on
            # the events themselves. The convention is stated in the index so a reader is never guessing.
            rows = [{'id': e.get('eventId'), 'type': (e.get('eventType') or '').replace('EVENT_TYPE_', '', 1),
                     'time': e.get('eventTime'), 'line': line}
                    for line, e in enumerate(part, 2)]          # line 1 of the part is the opening bracket
            ordered.append({'workflow': name, 'file': 'NATIVE_HISTORY_%s_%d.json' % (label, number), 'body': body,
                            'map_body': ('[\n' + ',\n'.join(json.dumps(r, separators=(',', ':')) for r in rows)
                                         + '\n]\n').encode(), 'map_rows': len(rows),
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
    # The location maps are held back the same way, for the same reason: they are delivered files too. The
    # allowance is computed from the events themselves, so it cannot quietly take room the parts needed.
    # Every other delivered file is held back from the room the parts may claim. The maps are now EXACT: the
    # batching depends only on event sizes, never on the room, so their bytes are known here. An allowance that
    # guessed high cost the parts thirty kilobytes they had, and a part is claimed whole or not at all.
    room -= INDEX_BYTES + sum(len(item['map_body']) for item in ordered) + sum(
        len(readable_event(e)) for evs in histories.values() for e in evs
        if len(json.dumps(e, separators=(',', ':')).encode()) > READER_LINE_BYTES)
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
             'sha256': host.sha(item['body']),
             'map_body': item['map_body'], 'map_rows': item['map_rows']})
        item['delivered'] = True
    files = {item['file']: item['body'] for item in ordered if item.get('delivered')}
    for entry in index['workflows'].values():
        entry['parts'].sort(key=lambda p: p['part'])
        entry['gaps'].sort(key=lambda g: g.get('part') or 0)
    # Where every DELIVERED event is: its id, type, time and the line it is on. Derived mechanically from the
    # same events, so it can be checked against them; it says where to look, never what the event means. Without
    # it a reader holding only a file reader would have to open every part to answer a question about one
    # interval. One map PER PART, so a map is bounded by its own part and can never itself become a file the
    # reader cannot open - which is what a single map over a whole workflow turned into.
    for name, entry in index['workflows'].items():
        for part in entry['parts']:
            name_map = part['file'].replace('NATIVE_HISTORY_', 'NATIVE_HISTORY_MAP_', 1)
            files[name_map] = part.pop('map_body')
            if len(files[name_map]) > HISTORY_PART_BYTES:
                # Refuse rather than hand the reader a navigation aid it cannot open.
                raise ValueError('Native history map %s exceeds the reader bound: %d bytes'
                                 % (name_map, len(files[name_map])))
            part['map'] = {'file': name_map, 'rows': part.pop('map_rows'), 'sha256': host.sha(files[name_map]),
                           'meaning': 'one line per event in this part: id, type, time, and the line the whole '
                                      'event is on in ' + part['file']}
            # An event whose own line is past what the reader can open gets a readable companion. The part
            # still carries it verbatim; the companion is a re-serialisation and says so.
            for line, event in enumerate(json.loads(files[part['file']]), 2):
                verbatim = json.dumps(event, separators=(',', ':')).encode()
                if len(verbatim) <= READER_LINE_BYTES:
                    continue
                # From THIS part's own file name, never from a loop variable left over from the batching
                # above: a companion named for another workflow states an identity it does not have.
                copy_name = part['file'].replace('NATIVE_HISTORY_', 'NATIVE_HISTORY_EVENT_', 1)[:-5] \
                    + '_%s.json' % event.get('eventId')
                readable = readable_event(event)
                record = {'event_id': event.get('eventId'), 'event_type': event.get('eventType'),
                          'line': line, 'verbatim_bytes': len(verbatim),
                          'verbatim_sha256': host.sha(verbatim)}
                # Measured on this goal's own history: decoding the base64 payload SHRINKS the event, to
                # between 0.85 and 0.93 of its verbatim bytes, largest companion 69399 against the reader's
                # 262144. So no bound is introduced for its own sake. But an event is delivered whenever it
                # fits a part, up to HISTORY_PART_BYTES, and one that is mostly structure rather than base64
                # would grow under indent instead of shrinking. A companion the reader cannot open is the
                # same failure this whole split exists to correct, so it is named as a gap rather than
                # written: the verbatim event stays in its part either way.
                # The same holds for a companion that would still carry a line the reader cannot open - a payload
                # that is not base64 JSON stays one long string under indent. Found by the gate's own test.
                longest = max(len(line) for line in readable.split(b'\n'))
                if len(readable) > READ_BOUND or longest > READER_LINE_BYTES:
                    record['readable_copy'] = None
                    record['readable_copy_bytes'] = len(readable)
                    record['readable_copy_longest_line'] = longest
                    record['note'] = ('This line is too long for a line-based reader to open, and its '
                                      'readable companion would ALSO be past what that reader can open (the '
                                      'per-file bound of %d bytes or a line over %d bytes), so none was '
                                      'written. The event is still in the part verbatim and the part still '
                                      'hashes to what the index records. Treat this event as delivered but '
                                      'not readable in place.' % (READ_BOUND, READER_LINE_BYTES))
                    part.setdefault('unreadable_lines', []).append(record)
                    continue
                files[copy_name] = readable
                record.update({'readable_copy': copy_name, 'readable_copy_sha256': host.sha(readable)})
                part.setdefault('unreadable_lines', []).append(
                    {**record,
                     'note': 'This line is too long for a line-based reader to open. The event is still in '
                             'the part verbatim and the part still hashes to what the index records; the '
                             'companion is the SAME event re-serialised for reading, with its base64 json/plain payload decoded. It is not byte-identical to the event.'})
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


ARCHIVES = 'transition'


def archived_history(name):
    """A verified private archive of a closed execution the engine no longer holds.

    Identity is read from inside the bytes as far as the bytes can carry it. A Temporal history states its
    workflow id and its CHAIN's first run id; it never names the run it was taken from. Measured on this goal's
    own parent, which is a RESET execution whose chain origin is already outside retention: requiring the index
    to equal the id inside the bytes would reject a completely valid archive, while accepting whatever the index
    says would let an index assert an identity the bytes do not support. So both are bound: the workflow id and
    the chain origin come from the bytes, the run id the archive was taken from comes from the index, the hash
    binds the content, and a history offered as complete must end in a terminal event.

    Archives that disagree about any of these are a disagreement, never a choice. An archive evidences past
    events; it is never an observation of the current scope, budget, service or AP10.
    """
    base = ROOT / '.runtime/ap11' / ARCHIVES
    found = []
    for index in sorted(base.glob('closed-histories-preserved-*/index.json')):
        try:
            for entry in json.loads(index.read_text())['executions']:
                if entry['workflow_id'] != name:
                    continue
                path = index.parent / entry['file']
                if path.is_symlink() or not path.is_file():
                    continue
                body = path.read_bytes()
                if host.sha(body) != entry['sha256']:
                    continue
                events = json.loads(body)['events']
                start = events[0]['workflowExecutionStartedEventAttributes']
                if (start.get('workflowId') != name or len(events) != entry['events']
                        or not str(events[-1].get('eventType', '')).endswith(
                            ('_COMPLETED', '_FAILED', '_TIMED_OUT', '_CANCELED', '_TERMINATED', '_CONTINUED_AS_NEW'))):
                    continue
                found.append({'source': 'archive', 'archive': index.parent.name, 'events': events,
                              'run_id': entry['run_id'], 'chain_origin': start.get('firstExecutionRunId'),
                              'sha256': entry['sha256'], 'closed': entry.get('close_time'),
                              'terminal_event': events[-1].get('eventType')})
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
    if not found:
        return None
    agreed = {(f['run_id'], f['chain_origin'], f['sha256']) for f in found}
    if len(agreed) != 1:
        raise ValueError('archives of %s disagree about identity or content; no evidence' % name)
    return {**found[0], 'verified_archives': len(found)}


async def native_evidence(applications,task_ids):
    from temporalio.service import RPCError, RPCStatusCode
    client=await Client.connect('127.0.0.1:7339',namespace='nortropic-runtime')
    histories={};sources={}
    # Every run identity this one commitment has had, then its children. A further assessment runs under
    # its own identity, so the application it follows stays readable as the evidence of the examined work
    # rather than being replaced by the run that is examining it.
    for name in [*applications,*task_ids]:
        try:
            described=await client.get_workflow_handle(name).describe()
            history=await client.get_workflow_handle(name,run_id=described.run_id).fetch_history()
            histories[name]=[MessageToDict(event) for event in history.events]
            sources[name]={'source':'engine','run_id':described.run_id,'status':described.status.name,
                           'events':len(histories[name])}
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
            # The engine removes a closed execution one day after it closed. The evidence still exists; it is
            # simply no longer a live observation, and it is delivered as an archive saying so.
            kept=archived_history(name)
            if kept is None:
                raise ValueError('%s is gone from the engine and no verified archive of it exists' % name)
            histories[name]=kept['events']
            sources[name]={k:kept[k] for k in ('source','archive','run_id','chain_origin','sha256','closed',
                                               'terminal_event','verified_archives')}
            sources[name]['events']=len(kept['events'])
    watch=await client.get_schedule_handle(NAME).describe()
    return histories,status(watch),sources


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
    histories,watch,sources=asyncio.run(asyncio.wait_for(
        native_evidence(assessment.identities(config),task_ids),60))
    # Which executions were read live and which came from a verified archive, with the identity each was
    # bound by. An archive evidences past events; it is never a current observation, and the reviewer is
    # told which it is holding rather than having to assume.
    files['NATIVE_HISTORY_SOURCES.json']=readable_json(sources)
    # The actual full histories stay private. They are delivered SPLIT into ordered hash-bound parts, built last
    # so the room they get is measured against everything else rather than guessed; one file may not exceed
    # read_regular's bound and the bundle may not exceed prepare_call's. Marking oversized history unavailable
    # would be correct error handling but would not be a reviewable basis, so the events themselves go out.
    files['ACTUAL_REPORTS.json']=readable_json(reports)
    files['ACTUAL_REMOTE.json']=readable_json(receipts)
    files['ACTUAL_AP10.json']=readable_json(watch)
    files['SCOPE.json']=readable_json(state)
    # The journal itself, row for row, as a derived read copy tied to the original bytes by their hash. The rows
    # keep their own sequence, previous and sha256, so the chain order is readable in place.
    journal=read_regular(scope.directory,'journal.jsonl',limit=1024*1024);records=[decode(line) for line in journal.splitlines()]
    files['SCOPE_JOURNAL.json']=readable_json({'source':'journal.jsonl of this scope','source_sha256':host.sha(journal),
        'rows':len(records),'head':decode(read_regular(scope.directory,'head.json')),
        'how_to_read':'journal is every row of the scope journal in order, verbatim as decoded JSON. Each row carries '
                      'its sequence, the sha256 of the row before it and its own sha256, which is the chain. This '
                      'file is a re-serialisation for reading, bound to the original bytes by source_sha256.',
        'journal':records})
    # Every whole-goal review this commitment has had: the verdicts a further assessment follows, verbatim.
    files['WHOLE_GOAL_REVIEWS.json']=readable_json(whole_goal_reviews(scope,config,records))
    # The separately reviewed decision binding each further assessment, and its review, as the release holds them.
    for entry in assessment.assessments(config):
        for name in (entry['decision'],entry['review']):
            files['assessments/'+name]=read_regular(Path(config['directory'])/'development-context',name)
    # Every answer the HOST itself gave to a diagnosis. These are operator interventions, and one of them can let a
    # host-interrupted review be re-run, so the whole-goal review must see them as such and not have to infer them
    # from signal payloads in the native history.
    files['HOST_ANSWERS.json']=readable_json(host.host_answers(scope))
    from .development_interactive import (selected_nonce, retry_evidence, trigger_record,
                                          NONCE, RETRIES, EXTENSIONS)
    nonce=selected_nonce(scope,config);stage=scope.directory/'calls'/nonce
    files.update(retry_evidence(scope,nonce))
    for name in ('input.json','interactive-input.json','session-exit.json','result.json'):
        files['interactive/'+name]=read_regular(stage,name)
    files['interactive/OPERATOR_INPUT.json']=readable_json({'bytes_hex':read_regular(stage,'operator-input.raw',limit=16384).hex()})
    # Why each Ctrl-C pair was sent, for EVERY preserved interactive session and not only the selected one.
    # The first whole-goal review had the operator bytes without a session to bind them to and without the
    # justification amendment section 4 requires. The host cannot testify to what the operator intended, so
    # each record is derived from the preserved terminal and native session, and a session whose bytes or
    # order do not support a record is delivered as an explicit refusal with its reason rather than omitted.
    triggers={}
    for name in (NONCE,*RETRIES,*EXTENSIONS):
        earlier=scope.directory/'calls'/name
        if (earlier/'session-exit.json').is_file():
            triggers[name]=trigger_record(earlier)
        if name==nonce:break
    files['interactive/TRIGGER_RECORDS.json']=json.dumps(triggers,indent=1).encode()
    for name in ('authority.md','goal.md'):
        files[name]=read_regular(Path(config['directory'])/'development-context',name)
    files['AGENTS.md']=read_regular(Path(config['directory'])/'office','AGENTS.md')
    amended=host.goal_amendments(config,decode(read_regular(scope.directory,'contract.json')));files.update(amended)
    # Last, against the real remaining room. The reserve covers what prepare_call adds after this point: the
    # output schema and CONTEXT.json, whose delivered-file inventory grows with every part named here.
    # The reserve covers what prepare_call adds after this point: the output schema and CONTEXT.json, whose
    # delivered-file inventory grows with every part, map and companion named here. Measured at about 20 KB
    # for this package; 40 KB is the margin, not a guess that would quietly take room the evidence needed.
    # The artefacts the first whole-goal review named as missing. Each one was referred to as present and was
    # not in the inventory, which left the criteria that rest on it supported only by descriptions of it.
    #
    # The frozen acceptance recipes: G3 turns on these living outside candidate write access and producing the
    # acceptance, rather than the candidate's own test doing it. Read from the RELEASE's own office copy, which
    # is the code that actually ran. The policy names each recipe relative to the Office root
    # ('acceptance/ap11_reconciliation.py'), exactly as the build read it (development_host), so it is read and
    # delivered under that same path - reading it below office/acceptance doubled the directory and refused the
    # second assessment's preparation before any model ran.
    active=host.policy(config)
    for recipe in sorted(active.RECIPES.values()):
        files[recipe]=read_regular(Path(config['directory'])/'office',recipe)
    # The reused reader and the two delivered candidates: G1 turns on reuse of an existing component rather
    # than a new engine, and that is only checkable against the modules themselves.
    files['office/kontor_result.py']=read_regular(Path(config['directory'])/'office/tools','kontor_result.py')
    for work,event in state['integrated'].items():
        for name in sorted(load(event['task'])['allowed_paths']):
            if name.startswith('tools/') and not Path(name).name.startswith('test_'):
                files['office/'+Path(name).name]=git(repository(OFFICE),'show',
                                                     event['receipt']['merge_commit']+':'+name,raw=True)
    # The frozen tasks and the preparation reviews that approved them. Without these, the link the acceptance
    # requires - draft, independent scope and verification review, frozen task - can only be taken on trust,
    # and a difference between what the accepted answer asked for and what the candidate delivered cannot be
    # told apart from an unreviewed divergence.
    for draft in sorted((scope.directory/'drafts').iterdir()):
        if (draft/'frozen.json').is_file():
            files['frozen/'+draft.name+'.json']=read_regular(draft,'frozen.json')
    reviews={}
    for call in scope.inspect()['calls']:
        stage=scope.directory/'calls'/identifier(call['nonce'])
        if call.get('role')!='preparation-review' or not (stage/'result.json').is_file():
            continue
        result=decode(read_regular(stage,'result.json'))
        reviews[call['nonce']]={'work':call.get('work'),'answer':result.get('answer'),
                                'completed':result.get('completed')}
    files['PREPARATION_REVIEWS.json']=json.dumps(reviews,indent=1,ensure_ascii=False).encode()
    # The frozen selection itself, verbatim. The amendment's own review record makes an ACTIVE configuration
    # binding its hashes a precondition, and that cannot be checked against a hash alone. Only the selection is
    # delivered: the rest of the configuration is the file integrity map, whose whole point is that it names
    # host paths.
    files['ACTIVE_SELECTION.json']=json.dumps(
        {'config_sha256':config['config_sha256'],'runtime_revision':config['runtime_revision'],
         'office_revision':config['office_revision'],'development':config.get('development'),
         'note':'The development selection of the ACTIVE frozen release configuration, verbatim. The rest of '
                'that file is its integrity map over host paths and is deliberately not delivered.'},
        indent=1,ensure_ascii=False).encode()
    # G8's isolated boundary proofs. The first whole-goal review was right that the 49th model process and the
    # seventh implementation attempt are never reached by this application, so their refusal has no live evidence
    # here; the proofs for them exist in isolation and were described rather than delivered. Read from the ACTIVE
    # release's own runtime revision, so the reviewer holds the text that belongs to the running release and not
    # whatever a working copy happens to contain.
    for path in PROOFS:
        files['proofs/'+Path(path).name]=git(repository(RUNTIME),'show',config['runtime_revision']+':'+path,raw=True)
    files.update(history_parts(histories,host.CONTEXT_BYTES['final-review']-sum(len(v) for v in files.values())-40*1024))
    readable_delivery(files)
    context={'goal_amendments':host.amendment_notice(amended),'remaining_action':'Independently examine entire actual G1-G10 chain and approve closure or identify exact gaps',
        'observed_at':datetime.now(timezone.utc).isoformat(),'runtime_revision':config['runtime_revision'],
        'office_revision':config['office_revision'],'config_sha256':config['config_sha256'],
        'qualification_index_sha256':host.sha(read_regular(directory,'index.json')),
        'native_history':'Delivered SPLIT across NATIVE_HISTORY_<workflow>_<n>.json files. Read '
            'NATIVE_HISTORY_INDEX.json first: it gives each workflow its event count, the hash of the complete '
            'original, the parts in order with their own hashes and event-id ranges, and any gap. A part is a '
            'slice, never a summary; where the index reports a gap, treat it as missing evidence rather than '
            'reading the delivered parts as the whole history.',
        'earlier_reviews':'WHOLE_GOAL_REVIEWS.json holds every earlier whole-goal review of this commitment in journal '
            'order: a completed one with its answer verbatim, one that did not complete with only what the host '
            'measured about it. assessments/ holds the separately reviewed decision binding each further assessment '
            'and its review. proofs/ holds the release revision\'s own isolated proof sources; their recorded runs '
            'are qualification records, and a source file alone is not a run.',
        'closure_condition':'Approval permits only stopping office-ap11 after this review. Host must read back stopped scope; AP10 stays active. No next goal.'}
    return host.prepare_call(scope.expected,key,'final-review','goal',context,files)


def close(scope,config,nonce):
    result=host.call_result(scope,nonce,'final-review')
    if not host.policy(config).review(result['answer']):
        scope.control('paused','Whole-goal review not approved; preserve specific evidence gaps')
        return {'approved':False,'review':nonce,'decision':result['answer'],'whole_goal_complete':False}
    # The continued half of an interruption in its own run cannot be the independent examination of that interruption
    # (G6, amendment section 5: no self-approval). Its approval is recorded as given and the closure is withheld for a
    # separate assessment; nothing is stopped.
    if assessment.continues_an_interruption(scope,nonce):
        scope.control('paused','Whole-goal review approved as the continuation of an interrupted review in its own run; '
                               'closure waits for a separate examination')
        return {'approved':True,'closure_withheld':'continuation of an interrupted review in the same run',
                'review':nonce,'decision':result['answer'],'whole_goal_complete':False}
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
