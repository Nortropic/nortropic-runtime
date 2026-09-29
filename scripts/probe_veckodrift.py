"""Real Temporal schedule + real Office handler + Digitala's real frozen tools.

What this establishes: the weekly management operation is due-based, so a period
missed while the host slept is performed by the first wakeup that becomes possible;
a wakeup inside the period reads nothing; a site incident is found, receipted in the
customer path and delivered once to Office's private inbox; and the frozen consumer
is actually started over real HTTP with the case's own lock and persistent state.

What this does not establish: the site and the Kundstart signals endpoint are isolated
loopback fixtures on this machine, never a customer address and never Kundstart's
production or its local prov service. Only active-release loading is injected. No
candidate code is activated, no AP-10 schedule or worker is touched, and the uniquely
named test schedule and queue are created, paused and removed again.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import threading
import uuid
from unittest.mock import patch
from temporalio.client import Client, ScheduleIntervalSpec, ScheduleSpec
from temporalio.worker import Worker
from runtime.scheduled_operation import (ScheduledOperation, scheduled_operation,
                                         ACTIVITY_BOUND, SCHEDULE_TO_CLOSE_BOUND,
                                         EXECUTION_BOUND)
from runtime.operation_schedule import definition, validate, execution_status

WAKEUP_SECONDS = 3600      # the ordinary hourly wakeup that the release would bind
PERIOD_SECONDS = 3600      # the accepted floor, standing in for the weekly period
TICK_SECONDS = 10          # only the isolated accelerated schedule uses this


def handler_bound(handler):
    """Read Office's own declared ceiling from the exact handler bytes under test."""
    spec = importlib.util.spec_from_file_location('probe_office_handler', handler)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BOUND_SECONDS


class Fixtures:
    """One loopback server for the customer's site, one for the signals contract."""

    def __init__(self):
        self.site_status, self.site_calls, self.signal_calls = 200, 0, 0
        self.body = 'Välkommen till provsajten'
        owner = self

        class Site(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                owner.site_calls += 1
                sitemap = self.path.endswith('/sitemap.xml')
                self.send_response(200 if sitemap else owner.site_status); self.end_headers()
                self.wfile.write(('<urlset/>' if sitemap else owner.body).encode())

        class Signals(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                # The documented contract shape, with a real second page so the
                # consumer's full scan and cursor handling are actually exercised.
                owner.signal_calls += 1
                if self.headers.get('Authorization', '') != 'Bearer ' + owner.key:
                    self.send_response(401); self.end_headers(); self.wfile.write(b'{}'); return
                first = '?' not in self.path
                body = {'schema': 'kundstart-signaler/1', 'signaler': [],
                        'cursor': 'sida-2' if first else None}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(body).encode())

        self.site = ThreadingHTTPServer(('127.0.0.1', 0), Site)
        self.signals = ThreadingHTTPServer(('127.0.0.1', 0), Signals)
        self.key = 'probe-' + uuid.uuid4().hex
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True)
                        for s in (self.site, self.signals)]
        for thread in self.threads:
            thread.start()

    @property
    def site_url(self):
        return 'http://127.0.0.1:%s/' % self.site.server_port

    @property
    def signals_url(self):
        return 'http://127.0.0.1:%s' % self.signals.server_port

    def close(self):
        for server in (self.site, self.signals):
            server.shutdown(); server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)


def freeze_digitala(source, dest):
    """Copy Digitala's whole verktyg tree so no unbound module can load at run time."""
    files = {}
    for path in sorted((source / 'verktyg').rglob('*.py')):
        relative = path.relative_to(source)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes()); target.chmod(0o444)
        files[str(relative)] = sha256(target.read_bytes()).hexdigest()
    for required in ('verktyg/drift_kontroll.py', 'verktyg/kundstart.py'):
        if required not in files:
            raise RuntimeError('Digitala checkout lacks ' + required)
    return files


def build(output, office_handler, digitala, interpreter, fixtures):
    release = output / 'release'
    frozen = output / 'frozen-digitala'
    digitala_files = freeze_digitala(digitala, frozen)

    customer = output / 'kund'; customer.mkdir(parents=True)
    arende = 'PROV-' + uuid.uuid4().hex[:12]
    (customer / 'KUNDSTART.json').write_text(json.dumps(
        {'arende_id': arende, 'bas_url': fixtures.signals_url, 'kund': 'Provkund'},
        ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    key_file = output / 'intern-nyckel.secret'
    key_file.write_text(fixtures.key); key_file.chmod(0o600)

    plan = output / 'DRIFT.json'
    plan.write_bytes((json.dumps({'schema': 1, 'kund': 'Provkund', 'sajter': [
        {'adress': fixtures.site_url, 'forvantat': 'provsajten', 'max_ms': 30000,
         'sitemap': True}]}, ensure_ascii=False) + '\n').encode())

    state = output / 'privat-driftlage'
    inputs = {'schema': 'office-drift/1', 'state': str(state), 'period_seconds': PERIOD_SECONDS,
              'drift': {'digitala_root': str(frozen), 'digitala_files': digitala_files,
                        'python_path': str(interpreter),
                        'python_sha256': sha256(interpreter.read_bytes()).hexdigest(),
                        'plan': str(plan), 'plan_sha256': sha256(plan.read_bytes()).hexdigest(),
                        'receipts': str(customer), 'isolated_test': True},
              'intake': {'digitala_root': str(frozen), 'digitala_files': digitala_files,
                         'python_path': str(interpreter),
                         'python_sha256': sha256(interpreter.read_bytes()).hexdigest(),
                         'base_url': fixtures.signals_url, 'key_file': str(key_file),
                         'customer': str(customer), 'executor': 'isolerad-provkorning'}}

    name = 'veckodrift-probe-' + uuid.uuid4().hex
    config = {'directory': str(release), 'config_sha256': 'f' * 64, 'files': {},
              'scheduled_operations': {name: {'input': 'operations/' + name + '.json',
                                              'interval_seconds': WAKEUP_SECONDS}}}
    for relative, raw in [('office/tools/driftoperation.py', office_handler.read_bytes()),
                          ('operations/' + name + '.json',
                           json.dumps(inputs, ensure_ascii=False, indent=2).encode())]:
        target = release / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw); config['files'][relative] = sha256(raw).hexdigest()
    (output / 'qualification-config.json').write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    return name, config, state, customer, plan


def rewind(state, seconds):
    """Stand in for a host that slept past the due time: move the record backwards.

    Everything except the timestamp is preserved, including the closing run's id, so
    the record stays a valid one and the wakeup answers period_elapsed rather than
    quarantining malformed state.
    """
    path = state / 'period.json'
    value = json.loads(path.read_text())
    stamp = datetime.fromisoformat(value['completed_at']) - timedelta(seconds=seconds)
    path.write_text(json.dumps({**value, 'completed_at': stamp.isoformat()}, indent=2) + '\n')
    return stamp.isoformat()


async def next_result(client, handle, seen, deadline=90):
    end = asyncio.get_running_loop().time() + deadline
    while True:
        described = await handle.describe()
        fresh = [a for a in described.info.recent_actions if a.action.workflow_id not in seen]
        if fresh:
            workflow_id = fresh[0].action.workflow_id
            seen.add(workflow_id)
            value = await asyncio.wait_for(client.get_workflow_handle(workflow_id).result(), 30)
            return workflow_id, value['result']
        if asyncio.get_running_loop().time() > end:
            raise TimeoutError('Native schedule did not fire in time')
        await asyncio.sleep(.2)


async def probe(output, office_handler, digitala, interpreter):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    fixtures = Fixtures()
    name, config, state, customer, plan = build(output, office_handler, digitala,
                                                interpreter, fixtures)
    # The only place the two repositories' bounds are compared, against the exact
    # handler bytes under test rather than a number copied into a Runtime test.
    bound = handler_bound(office_handler)
    if not bound < ACTIVITY_BOUND < SCHEDULE_TO_CLOSE_BOUND < EXECUTION_BOUND:
        raise RuntimeError('Office bound %s does not fit inside Runtime %s/%s/%s'
                           % (bound, ACTIVITY_BOUND, SCHEDULE_TO_CLOSE_BOUND, EXECUTION_BOUND))
    client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
    handle, runs, seen = None, [], set()
    try:
        with patch('runtime.release.require_active_code', return_value=config):
            async with Worker(client, task_queue=name, workflows=[ScheduledOperation],
                              activities=[scheduled_operation], max_concurrent_activities=1):
                schedule = definition(config, name)
                # The ordinary hourly definition must survive real native
                # serialization before the accelerated isolated queue is used.
                ordinary = await client.create_schedule(name + '-definition', schedule)
                try:
                    native = await ordinary.describe()
                    await validate(client, native, config, name)
                    if not native.schedule.state.paused or native.info.num_actions:
                        raise RuntimeError('Ordinary definition must remain paused')
                    if native.schedule.spec.intervals[0].every != timedelta(seconds=WAKEUP_SECONDS):
                        raise RuntimeError('Ordinary wakeup interval differs')
                finally:
                    await ordinary.delete()

                schedule.action.task_queue = name
                schedule.spec = ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=timedelta(seconds=TICK_SECONDS))])
                schedule.state.limited_actions = True; schedule.state.remaining_actions = 3
                handle = await client.create_schedule(name, schedule)
                await asyncio.sleep(1)
                if (await handle.describe()).info.num_actions:
                    raise RuntimeError('Paused schedule started')
                await handle.unpause(note='Three isolated qualification wakeups; no model or provider')

                # 1. First wakeup: the period has never run, so the work is due.
                site_before, signal_before = fixtures.site_calls, fixtures.signal_calls
                workflow_id, first = await next_result(client, handle, seen)
                runs.append({'wakeup': 1, 'workflow_id': workflow_id, 'result': first})
                if not (first['performed'] and first['completed']
                        and first['period']['reason'] == 'no_period_recorded'
                        and first['drift']['ran'] and first['drift']['healthy']
                        and first['drift']['incidents'] == 0
                        and first['intake']['completed']
                        and first['period_recorded']['sequence'] == 1
                        and first['period_recorded']['run_id'] == first['run_id']):
                    raise RuntimeError('First due wakeup did not perform a clean check: ' + json.dumps(first))
                if fixtures.site_calls <= site_before or fixtures.signal_calls - signal_before < 2:
                    raise RuntimeError('The frozen tools did not actually reach the fixtures')

                # 2. Second wakeup, inside the same period: it must read nothing.
                site_before, signal_before = fixtures.site_calls, fixtures.signal_calls
                workflow_id, inside = await next_result(client, handle, seen)
                runs.append({'wakeup': 2, 'workflow_id': workflow_id, 'result': inside})
                if not (inside.get('skipped') == 'not_due' and inside['performed'] is False
                        and inside['completed'] is True
                        and inside['period']['reason'] == 'not_due'):
                    raise RuntimeError('Wakeup inside the period was not a no-op: ' + json.dumps(inside))
                if (fixtures.site_calls, fixtures.signal_calls) != (site_before, signal_before):
                    raise RuntimeError('A wakeup inside the period made a request')
                if (state / inside['run_id']).exists():
                    raise RuntimeError('A wakeup that read nothing wrote a run record')

                # 3. The host slept past the due time and the site went down: the
                #    overdue period is performed by the next possible wakeup.
                rewound = rewind(state, 2 * PERIOD_SECONDS)
                fixtures.site_status = 503
                workflow_id, late = await next_result(client, handle, seen)
                runs.append({'wakeup': 3, 'workflow_id': workflow_id, 'result': late})
                if not (late['performed'] and not late['completed']
                        and late['period']['reason'] == 'period_elapsed'
                        and late['period']['overdue_seconds'] >= PERIOD_SECONDS
                        and late['drift']['ran'] and late['drift']['healthy'] is False
                        and late['drift']['incidents'] == 1
                        and late['drift']['reason'] == 'site_incident'
                        and late['period_recorded']['sequence'] == 2):
                    raise RuntimeError('Overdue period was not performed as an incident: ' + json.dumps(late))
                if late['deliveries']['drift']['receipts'][0]['recipient'] != 'kontorets-privata-driftyta':
                    raise RuntimeError('Incident was not acknowledged by the private recipient')

                await handle.pause(note='Isolated qualification finished')
                after = await handle.describe()
                native_status = await execution_status(client, after)
                if after.info.num_actions != 3 or after.schedule.state.remaining_actions != 0:
                    raise RuntimeError('Native wakeup budget differs')

        receipts = sorted(customer.glob('DRIFT-*.json'))
        inbox = [json.loads(p.read_text()) for p in sorted((state / 'inbox').glob('*.json'))]
        if [(r['event']['channel'], r['event']['kind']) for r in inbox] != [('drift', 'incident')]:
            raise RuntimeError('Private inbox does not hold exactly the drift incident')
        if not receipts:
            raise RuntimeError('No DRIFT receipt reached the customer path')
        summary = {
            'passed': True, 'schedule': name,
            'office_bound_seconds': bound, 'runtime_activity_bound': ACTIVITY_BOUND,
            'runtime_schedule_to_close_bound': SCHEDULE_TO_CLOSE_BOUND,
            'runtime_execution_bound': EXECUTION_BOUND,
            'ordinary_wakeup_seconds': WAKEUP_SECONDS, 'period_seconds': PERIOD_SECONDS,
            'accelerated_tick_seconds': TICK_SECONDS,
            'rewound_period_to': rewound,
            'site_requests': fixtures.site_calls, 'signal_requests': fixtures.signal_calls,
            'runs': runs, 'native_status_readback': native_status,
            'customer_receipts': [{'name': p.name, 'sha256': sha256(p.read_bytes()).hexdigest(),
                                   'incidenter': json.loads(p.read_text(encoding='utf-8'))['incidenter']}
                                  for p in receipts],
            'recipient_receipts': inbox,
            'period_state': json.loads((state / 'period.json').read_text()),
            'plan_sha256': sha256(plan.read_bytes()).hexdigest(),
            'scope': ('Real existing Temporal engine, isolated queue and schedule, the candidate '
                      'Office handler and Digitala\'s real frozen drift_kontroll.py and kundstart.py '
                      'started as real subprocesses over loopback HTTP. Only active-release config '
                      'loading is injected.'),
            'not_shown': ('The site and the signals endpoint are loopback fixtures, not a customer '
                          'address and not Kundstart production or its local prov service. The '
                          'overdue period was produced by rewinding Office\'s own durable record, '
                          'which is the mechanism dueness uses; macOS sleep itself is not exercised. '
                          'No release was staged, selected or activated.')}
        (output / 'RESULTAT.json').write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': True, 'output': str(output), 'wakeups': 3,
                          'due_runs': 2, 'no_op_wakeups': 1,
                          'office_bound_seconds': bound}))
    finally:
        if handle:
            await handle.pause(note='Qualification cleanup; no further wakeups')
            await handle.delete()
        fixtures.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--office-handler', type=Path, required=True)
    parser.add_argument('--digitala', type=Path, required=True)
    parser.add_argument('--interpreter', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(probe(args.output.resolve(), args.office_handler.resolve(),
                      args.digitala.resolve(), args.interpreter.resolve()))
