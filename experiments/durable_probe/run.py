"""One bounded real-service compatibility test; no model/provider calls."""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from google.protobuf.json_format import MessageToDict
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from scripts.bounded import stop_group
from .workflow import ContinuityProbe

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.runtime/durable-probe'
OUTPUT = ROOT / 'evidence/durable-probe/run'


async def main():
    for port in (7339, 7340, 7341):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))  # Fail before disturbing another service.
    STATE.mkdir(exist_ok=False)
    OUTPUT.mkdir(exist_ok=False)
    processes, streams, observations = [], [], []
    started = time.monotonic()

    def spawn(command, name):
        stream = (OUTPUT / (name + '.log')).open('wb')
        streams.append(stream)
        proc = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(proc)
        observations.append({'event': 'spawn', 'name': name, 'pid': proc.pid, 'command': command})
        return proc

    def server(name):
        return spawn([str(ROOT / '.runtime/bin/temporal-1.9.1'), '--disable-config-env',
                      '--disable-config-file', 'server', 'start-dev', '--ip', '127.0.0.1',
                      '--port', '7339', '--http-port', '7340', '--metrics-port', '7341',
                      '--namespace', 'runtime-probe', '--headless',
                      '--db-filename', str(STATE / 'temporal.sqlite')], name)

    def worker(name):
        return spawn([sys.executable, '-m', 'experiments.durable_probe.worker'], name)

    async def connect():
        end = time.monotonic() + 15
        while time.monotonic() < end:
            try:
                return await asyncio.wait_for(Client.connect('127.0.0.1:7339', namespace='runtime-probe'), 1)
            except (Exception, asyncio.TimeoutError):
                await asyncio.sleep(.2)
        raise TimeoutError('Local service did not become ready within 15 seconds')

    async def wait_for_state(handle, expected):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            try:
                state = await asyncio.wait_for(handle.query(ContinuityProbe.state), 2)
                if state == expected:
                    return state
            except (Exception, asyncio.TimeoutError):
                pass
            await asyncio.sleep(.2)
        raise AssertionError('Expected workflow state not observed: ' + repr(expected))

    passed = False
    try:
        service = server('server-before')
        client = await connect()
        process = worker('worker-before')
        handle = await client.start_workflow(ContinuityProbe.run, id='nr-durable-compat-1', task_queue='nr-compat')
        expected = {'phase': 'waiting', 'executions': 1, 'continuation_requested': False}
        observations.append({'event': 'before_restart', 'state': await wait_for_state(handle, expected)})
        try:
            await client.start_workflow(ContinuityProbe.run, id='nr-durable-compat-1', task_queue='nr-compat')
            raise AssertionError('Duplicate workflow unexpectedly started')
        except WorkflowAlreadyStartedError:
            observations.append({'event': 'duplicate_start', 'rejected': True})
        # Genuine abrupt stops, not graceful in-memory handoff.
        for proc in (process, service):
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
            assert stop_group(proc)
        observations.append({'event': 'abrupt_worker_and_server_stop', 'effects': (STATE / 'effects.jsonl').read_text()})
        service = server('server-after')
        client = await connect()
        process = worker('worker-after')
        handle = client.get_workflow_handle('nr-durable-compat-1')
        observations.append({'event': 'after_restart', 'state': await wait_for_state(handle, expected)})
        before = (STATE / 'effects.jsonl').read_text().splitlines()
        assert [json.loads(x)['label'] for x in before] == ['first']
        await handle.signal(ContinuityProbe.continue_work)
        result = await asyncio.wait_for(handle.result(), 15)
        assert result == {'phase': 'done', 'executions': 2, 'continuation_requested': True}
        effects = [json.loads(x) for x in (STATE / 'effects.jsonl').read_text().splitlines()]
        assert effects == [{'label': 'first', 'activity_attempt': 1}, {'label': 'second', 'activity_attempt': 1}]
        history = await handle.fetch_history()
        (OUTPUT / 'history.json').write_text(json.dumps([MessageToDict(x) for x in history.events], indent=2) + '\n')
        (OUTPUT / 'effects.json').write_text(json.dumps(effects, indent=2) + '\n')
        observations.append({'event': 'completed', 'result': result})
        passed = True
    finally:
        cleanup = [stop_group(proc) for proc in reversed(processes)]
        for stream in streams:
            stream.close()
        report = {'passed': passed and all(cleanup), 'elapsed_seconds': round(time.monotonic() - started, 3),
                  'model_calls': 0, 'cleanup': cleanup, 'observations': observations}
        (OUTPUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    return 0 if report['passed'] else 1


async def bounded_main():
    task = asyncio.create_task(main())
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        return await asyncio.wait_for(task, 90)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(bounded_main()))
