"""User-owned pinned local lifecycle; Temporal alone owns task scheduling/state."""
import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import sys
import uuid

from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from .release import ROOT, CODE_ROOT, require_active_code
from .shared import ServiceIdentity, process_identity
from .service import LocalService
from .run import check_unfinished_writers
from .workflow import DevelopmentTask
from scripts.bounded import stop_group


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
                for historical in ('office-result-1', 'office-assignment-core-1', 'office-owner-view-1'):
                    state = await asyncio.wait_for(client.get_workflow_handle(historical).query(DevelopmentTask.state), 10)
                    if state.get('phase') != 'completed':
                        raise ValueError('Required delivered native history is unavailable or changed: '+historical)
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
