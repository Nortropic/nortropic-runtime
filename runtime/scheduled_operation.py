"""Bounded scheduled host operations on the existing Temporal engine.

The activated release chooses Office's handler and all inputs. A schedule supplies
only an operation id and the release hash; neither models nor events select code.
Business state and idempotency stay with Office/the ordinary customer tools.

The interval here is a wakeup, not the work's period. Office's handler decides from
its own durable state whether the period has elapsed, so a period missed because the
host slept is performed by the first wakeup that becomes possible rather than being
skipped, and Temporal's catch-up window is not what has to carry that guarantee.
"""
import asyncio
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import re

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

# One place for the whole bound, so the schedule, the workflow and the activity can
# not drift apart. Every value must exceed Office's own BOUND_SECONDS, which sums its
# intake, drift and monitor ceilings; scripts/probe_veckodrift.py asserts that against
# the release's actual handler bytes rather than against a number repeated here.
# Office's ceilings are wall clock: each frozen tool runs as a process group that is
# killed at its bound, and the monitor carries its own deadline because a urlopen
# timeout bounds one socket operation, not a whole attempt.
ACTIVITY_BOUND = 300
SCHEDULE_TO_CLOSE_BOUND = ACTIVITY_BOUND + 30
EXECUTION_BOUND = SCHEDULE_TO_CLOSE_BOUND + 30
HEARTBEAT_BOUND = 15


def operation(config, request):
    from .release import sha
    if (set(request) != {'operation', 'config_sha256'}
            or request['config_sha256'] != config['config_sha256']
            or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', request['operation'])):
        raise ValueError('Scheduled operation identity or release differs')
    selected = config.get('scheduled_operations', {}).get(request['operation'])
    if not isinstance(selected, dict) or set(selected) != {'input', 'interval_seconds'}:
        raise ValueError('Operation is not in the activated mandate')
    if type(selected['interval_seconds']) is not int or not 60 <= selected['interval_seconds'] <= 86400:
        raise ValueError('Invalid bounded schedule interval')
    relative = selected['input']
    if not isinstance(relative, str) or not re.fullmatch(r'operations/[a-z0-9-]+\.json', relative):
        raise ValueError('Unbound operation input')
    home = Path(config['directory'])
    for name in (relative, 'office/tools/driftoperation.py'):
        path = home / name
        if path.is_symlink() or not path.is_file() or sha(path) != config['files'].get(name):
            raise ValueError('Scheduled operation bytes differ')
    return home / relative, home / 'office/tools/driftoperation.py'


@activity.defn(name='scheduled_operation')
async def scheduled_operation(request: dict) -> dict:
    from .release import require_active_code
    config = require_active_code()
    input_path, handler = operation(config, request)
    spec = importlib.util.spec_from_file_location('office_scheduled_operation', handler)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Office bounds network/process time and serializes its durable business state.
    # Shield from worker cancellation until the bounded thread records its result.
    task = asyncio.create_task(asyncio.to_thread(module.run, json.loads(input_path.read_text()),
                                                activity.info().workflow_run_id))
    try:
        while not task.done():
            activity.heartbeat(request['operation'])
            await asyncio.wait({task}, timeout=1)
        result = task.result()
    except asyncio.CancelledError:
        # Repeated cancellation must not interrupt durable cleanup or replace
        # cancellation with the handler's exception. The handler carries its own
        # per-channel ceilings (BOUND_SECONDS); keep this extra wait bounded too.
        deadline = asyncio.get_running_loop().time() + ACTIVITY_BOUND
        while not task.done() and asyncio.get_running_loop().time() < deadline:
            try:
                await asyncio.wait({task}, timeout=1)
            except asyncio.CancelledError:
                continue
        if task.done() and not task.cancelled():
            task.exception()
        elif not task.done():
            activity.logger.error('Office operation cleanup exceeded its bound')
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        raise
    return {'operation': request['operation'], 'config_sha256': config['config_sha256'],
            'result': result}


@workflow.defn
class ScheduledOperation:
    @workflow.run
    async def run(self, request: dict) -> dict:
        return await workflow.execute_activity('scheduled_operation', request,
            start_to_close_timeout=timedelta(seconds=ACTIVITY_BOUND),
            schedule_to_close_timeout=timedelta(seconds=SCHEDULE_TO_CLOSE_BOUND),
            heartbeat_timeout=timedelta(seconds=HEARTBEAT_BOUND),
            retry_policy=RetryPolicy(maximum_attempts=1),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED)
