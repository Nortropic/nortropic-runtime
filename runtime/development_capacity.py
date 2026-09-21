"""Read-only admission from the existing native watch schedule.

This returns a wait instruction, never sleeps while holding an activity slot.
Temporal owns that wait. No schedule or AP10 resource policy is changed.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from temporalio import activity
from temporalio.client import Client
from .obligation import NAME, status
from .shared import ServiceIdentity
from .release import ROOT, require_active_code
from .snapshot import read_regular


def admission(observation, now, occupied_seconds):
    if (not isinstance(now, datetime) or now.utcoffset() is None or
            type(occupied_seconds) is not int or not 1 <= occupied_seconds <= 3900):
        raise ValueError('Bound the full activity occupancy')
    denied = {'available': False, 'wait_seconds': 30, 'reason': 'Watch capacity unavailable'}
    try:
        if (not isinstance(observation, dict) or observation['obligation'] != NAME
                or type(observation['paused']) is not bool
                or not isinstance(observation['running'], list)):
            return denied
        observed = datetime.fromisoformat(observation['observed_at'])
        if observed.utcoffset() is None or not -1 <= (now - observed).total_seconds() <= 5:
            return denied
        if observation['running']:
            return {**denied, 'reason': 'Native watch work is already running or queued'}
        if observation['paused']:
            return {'available': True, 'wait_seconds': 0, 'reason': 'Watch explicitly paused, no own work running'}
        times = observation['next_action_times']
        if not isinstance(times, list) or not times:
            return denied
        times = [datetime.fromisoformat(t) for t in times]
        if any(t.utcoffset() is None or t <= now for t in times):
            return denied
        due = min(times)
        # Full activity bound plus60s coordination margin, not just model time.
        if now + timedelta(seconds=occupied_seconds + 60) >= due:
            return {**denied, 'reason': 'Reserve capacity before the next native watch occurrence'}
        return {'available': True, 'wait_seconds': 0, 'reason': 'Full bounded activity fits before native watch'}
    except (KeyError, TypeError, ValueError, OverflowError):
        return denied


async def inspect_capacity(seconds):
    # This is already running inside the activated worker, not attaching an
    # operator process. Avoid SharedService's OS process probes in the one slot.
    # Its entire native observation must fit within AP10's shortest queue margin.
    config = require_active_code()
    receipt = json.loads(read_regular(ROOT, '.runtime/ap10/service.json'))
    expected = {key: config[key] for key in
                ('config_sha256', 'database', 'runtime_revision', 'office_revision')}
    if receipt.get('native_identity') != expected:
        raise ValueError('Different shared service binding')
    async def observe():
        client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
        identity = await client.get_workflow_handle(receipt['identity_workflow']).query(ServiceIdentity.describe)
        if identity != expected:
            raise ValueError('Native identity differs')
        description = await client.get_schedule_handle(NAME).describe()
        return admission(status(description), datetime.now(timezone.utc), seconds)
    return await asyncio.wait_for(observe(), 1)


def before_activity(task, seconds):
    """Recheck at actual slot entry, including after queue delay/redelivery."""
    if 'development' not in task:
        return None
    from .development_binding import for_task
    for_task(task)  # Reject an unactivated/changed binding before doing anything.
    try:
        observed = asyncio.run(inspect_capacity(seconds))
    except Exception as error:
        # A read failure cannot become spare capacity. No retries in this slot.
        observed = {'available': False, 'wait_seconds': 30,
                    'reason': 'Native capacity unavailable: ' + type(error).__name__}
    if observed['available']:
        return None
    return {'capacity_wait': True, 'capacity': observed}


@activity.defn
def development_capacity(request: dict) -> dict:
    """Short read-only activity; caller waits in native workflow, not here."""
    try:
        return asyncio.run(inspect_capacity(request['seconds']))
    except (OSError, ValueError, RuntimeError, TimeoutError):
        return {'available': False, 'wait_seconds': 30, 'reason': 'Native capacity observation unavailable'}
