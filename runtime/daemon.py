"""User-owned pinned local lifecycle; Temporal alone owns task scheduling/state."""
import asyncio
import base64
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import uuid

from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from .release import ROOT, CODE_ROOT, require_active_code, sha
from .shared import ServiceIdentity, process_identity
from .service import LocalService
from .run import check_unfinished_writers
from .workflow import DevelopmentTask
from .private_stage import check_private_processes
from scripts.bounded import stop_group


HISTORICAL = ('office-result-1', 'office-assignment-core-1', 'office-owner-view-1')


def archived_delivery(config, name):
    """A delivered execution that the engine no longer holds is evidenced ONLY by an archive this release binds.

    The engine removes a closed execution after its namespace retention (one day here, measured), so a daemon that
    insists on asking the engine cannot start a day after the last delivery closed. The pinned configuration names the
    run id and SHA256, the bytes lie inside the release under its file map, and the archived history itself must show
    that execution by name, that run of the task workflow, closing with the completed phase the live query would have returned. No binding,
    other bytes, another run or another outcome is missing evidence, never a pass.
    """
    bound = (config.get('historical_archives') or {}).get(name)
    if (not isinstance(bound, dict) or set(bound) != {'file', 'run_id', 'sha256'} or not all(isinstance(v, str) for v in bound.values())
            or Path(bound['file']).parent != Path('history') or config.get('files', {}).get(bound['file']) != bound['sha256']):
        raise ValueError('Required delivered native history is unavailable and no verified archive is bound: ' + name)
    path = Path(config['directory']) / bound['file']
    if path.is_symlink() or not path.is_file() or sha(path) != bound['sha256']:
        raise ValueError('Bound archive of delivered native history changed: ' + name)
    try:
        events = json.loads(path.read_text())['events']
        started = events[0]['workflowExecutionStartedEventAttributes']
        result = json.loads(base64.b64decode(events[-1]['workflowExecutionCompletedEventAttributes']['result']['payloads'][0]['data']))
        shown = (started['workflowId'], started['originalExecutionRunId'], started['workflowType']['name'], result['phase'])
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise ValueError('Bound archive does not show a completed delivery: ' + name) from error
    if shown != (name, bound['run_id'], 'DevelopmentTask', 'completed'):
        raise ValueError('Bound archive does not show that run completing its delivery: ' + name)
    return {'source': 'archive bound by the release', 'run_id': bound['run_id'], 'sha256': bound['sha256']}


async def delivered_histories(client, config):
    """What a daemon start requires of the delivered native histories, stated ONCE.

    The daemon calls it at every start. A controlled release transition calls the same function against the running
    engine BEFORE it stops the service, so a release whose daemon could not start is never selected. The engine is
    always asked first; an archive is consulted only for an execution the engine answers NOT_FOUND for.
    """
    observed = {}
    for name in HISTORICAL:
        try:
            state = await asyncio.wait_for(client.get_workflow_handle(name).query(DevelopmentTask.state), 10)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
            observed[name] = archived_delivery(config, name)
            continue
        if state.get('phase') != 'completed':
            raise ValueError('Required delivered native history is unavailable or changed: ' + name)
        observed[name] = {'source': 'engine'}
    return observed


async def main():
    os.umask(0o077)
    config = require_active_code()
    database = ROOT / '.runtime/runtime.sqlite'
    if not database.is_file() or database.is_symlink():
        raise ValueError('Established canonical database missing; restoration requires diagnosis')
    with sqlite3.connect('file:'+str(database)+'?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Canonical database integrity failure')
        if not connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            raise ValueError('Canonical database is empty')
    check_unfinished_writers()
    check_private_processes()
    home = ROOT / '.runtime/ap10'
    output = home / 'service-launches' / uuid.uuid4().hex
    output.mkdir(parents=True)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)
    service = LocalService(database, output / 'engine')
    async with service as client:
        with (output / 'worker.log').open('wb') as log:
            worker = subprocess.Popen([sys.executable, '-B', '-m', 'runtime.worker'], cwd=CODE_ROOT,
                                      stdout=log, stderr=log, start_new_session=True)
            try:
                identity = {'config_sha256': config['config_sha256'], 'database': config['database'],
                            'runtime_revision': config['runtime_revision'], 'office_revision': config['office_revision']}
                identity_id = 'ap10-service-' + config['config_sha256']
                try:
                    await client.start_workflow(ServiceIdentity.run, identity, id=identity_id,
                        task_queue='development', id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
                except WorkflowAlreadyStartedError:
                    pass
                live = await asyncio.wait_for(client.get_workflow_handle(identity_id).query(ServiceIdentity.describe), 20)
                if live != identity:
                    raise ValueError('Existing native service identity mismatch')
                (output / 'delivered-histories.json').write_text(json.dumps(await delivered_histories(client, config), indent=2)+'\n')
                receipt = dict(config_sha256=config['config_sha256'], native_identity=identity,
                               identity_workflow=identity_id)
                for role, pid in [('daemon', os.getpid()), ('engine', service.proc.pid), ('worker', worker.pid)]:
                    receipt[role] = {'pid': pid, 'identity': process_identity(pid)}
                (output / 'service.json').write_text(json.dumps(receipt, indent=2)+'\n')
                temp = home / 'service.json.tmp'
                temp.write_text(json.dumps(receipt, indent=2)+'\n'); temp.replace(home / 'service.json')
                while not stopping.is_set():
                    if worker.poll() is not None or service.proc.poll() is not None:
                        raise RuntimeError('Owned process ended; inspect retained evidence, no blind restart')
                    try:
                        await asyncio.wait_for(stopping.wait(), 2)
                    except TimeoutError:
                        pass
            finally:
                removed = stop_group(worker)
                (output / 'worker-cleanup.json').write_text(json.dumps({'process_group_removed': removed})+'\n')
                if not removed:
                    raise RuntimeError('Shared worker cleanup incomplete')


if __name__ == '__main__':
    asyncio.run(main())
