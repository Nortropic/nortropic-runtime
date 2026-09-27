"""Real Temporal schedule + real Office handler against an isolated HTTP fixture.

Active-release loading alone is injected with a frozen test configuration. This
does not activate candidate code or establish hosted-provider/production proof.
Only the uniquely named test schedule/queue is created, paused and removed.
"""
import argparse
import asyncio
from datetime import timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import uuid
from unittest.mock import patch
from temporalio import activity, workflow
from temporalio.client import Client, ScheduleIntervalSpec, ScheduleSpec
from temporalio.worker import Worker
from runtime.scheduled_operation import ScheduledOperation, scheduled_operation
with workflow.unsafe.imports_passed_through():
    # Host-only probe orchestration; never called by OccupiedQueue.run.
    from runtime.operation_schedule import definition, validate, execution_status


blocked_started = None
blocked_release = None


@activity.defn
async def occupied_slot():
    blocked_started.set()
    await asyncio.wait_for(blocked_release.wait(), timeout=50)
    return 'released'


@workflow.defn
class OccupiedQueue:
    @workflow.run
    async def run(self):
        return await workflow.execute_activity(occupied_slot,
            start_to_close_timeout=timedelta(seconds=55))


async def probe(output, office):
    global blocked_started, blocked_release
    blocked_started, blocked_release = asyncio.Event(), asyncio.Event()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    status = {'http': 200}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(status['http']); self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'candidate': 'a'*40, 'storage': 'available'}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    name = 'operation-probe-' + uuid.uuid4().hex
    client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
    config = {'directory': str(output / 'release'), 'config_sha256': 'f'*64, 'files': {},
        'scheduled_operations': {name: {'input': 'operations/'+name+'.json', 'interval_seconds': 60}}}
    inputs = {'schema': 'office-drift/1', 'state': str(output / 'private-state'),
              'monitor': {'url': 'http://127.0.0.1:%s/health' % server.server_port,
                          'candidate': 'a'*40, 'isolated_test': True}}
    for relative, raw in [('office/tools/driftoperation.py', office.read_bytes()),
                           ('operations/'+name+'.json', json.dumps(inputs).encode())]:
        target = Path(config['directory']) / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw); config['files'][relative] = sha256(raw).hexdigest()
    (output / 'qualification-config.json').write_text(json.dumps(config, indent=2)+'\n')
    handle = None; runs = []
    try:
        with patch('runtime.release.require_active_code', return_value=config):
            async with Worker(client, task_queue=name, workflows=[ScheduledOperation],
                              activities=[scheduled_operation], max_concurrent_activities=1), Worker(
                    client, task_queue=name+'-occupied', workflows=[OccupiedQueue],
                    activities=[occupied_slot], max_concurrent_activities=1):
                occupied = await client.start_workflow(OccupiedQueue.run, id=name+'-occupied',
                    task_queue=name+'-occupied')
                await asyncio.wait_for(blocked_started.wait(), timeout=10)
                schedule = definition(config, name)
                # Verify the ordinary paused definition survives real native
                # serialization before using the accelerated isolated queue.
                ordinary = await client.create_schedule(name + '-definition', schedule)
                try:
                    native = await ordinary.describe()
                    await validate(client, native, config, name)
                    if not native.schedule.state.paused or native.info.num_actions:
                        raise RuntimeError('Ordinary definition must remain paused')
                finally:
                    await ordinary.delete()
                schedule.action.task_queue = name
                schedule.spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=3))])
                schedule.state.limited_actions = True; schedule.state.remaining_actions = 3
                handle = await client.create_schedule(name, schedule)
                await asyncio.sleep(1)
                if (await handle.describe()).info.num_actions != 0:
                    raise RuntimeError('Paused schedule started')
                await handle.unpause(note='Three isolated qualification starts; no model/provider')
                for index, next_status in enumerate((503, 200, 200)):
                    end = asyncio.get_running_loop().time()+25
                    while True:
                        described = await handle.describe()
                        completed = [a for a in described.info.recent_actions if a.action.workflow_id not in {r['workflow_id'] for r in runs}]
                        if completed:
                            wid = completed[0].action.workflow_id
                            value = await asyncio.wait_for(client.get_workflow_handle(wid).result(), 10)
                            runs.append({'workflow_id': wid, 'result': value}); status['http'] = next_status
                            break
                        if asyncio.get_running_loop().time() > end:
                            raise TimeoutError('Native schedule did not fire')
                        await asyncio.sleep(.1)
                await handle.pause(note='Isolated qualification finished')
                after = await handle.describe()
                actual_status = await execution_status(client, after)
                if not blocked_started.is_set() or blocked_release.is_set():
                    raise RuntimeError('Other queue was not occupied throughout monitor runs')
                blocked_release.set()
                if await occupied.result() != 'released':
                    raise RuntimeError('Occupied worker failed to finish')
                if after.info.num_actions != 3 or after.schedule.state.remaining_actions != 0:
                    raise RuntimeError('Native schedule action budget differs')
        actual = [r['result']['result']['completed'] for r in runs]
        if actual != [True, False, True]:
            raise RuntimeError('Expected healthy, detected incident, verified recovery: '+str(actual))
        receipts = [json.loads(p.read_text()) for p in sorted((output/'private-state/inbox').glob('*.json'))]
        if sorted(r['event']['kind'] for r in receipts) != ['incident', 'recovered']:
            raise RuntimeError('Actual recipient lacks incident/recovery')
        summary = {'passed': True, 'schedule': name, 'independent_activity_slot': True,
            'native_status_readback': actual_status, 'runs': runs, 'recipient_receipts': receipts,
            'scope': 'Real existing Temporal engine, isolated queue, actual candidate Office monitor/receiver and loopback HTTP. Only active-release config loading injected; no production activation or external provider proof.',
            'host_availability': 'Local Mac must be awake and Runtime worker available; no claim of always-on monitoring'}
        (output/'RESULTAT.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps({'passed': True, 'output': str(output), 'scheduled_starts': 3, 'native_definition_readback': True}))
    finally:
        blocked_release.set()
        if handle:
            await handle.pause(note='Qualification cleanup; no further starts')
            await handle.delete()
        server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--office-handler', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(probe(args.output.resolve(), args.office_handler.resolve()))
