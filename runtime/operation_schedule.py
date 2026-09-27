"""Explicit controls for release-bound operations; no AP10 schedule mutations."""
import argparse
import asyncio
from datetime import timedelta
import json
import sys

from temporalio.client import (Schedule, ScheduleActionStartWorkflow, ScheduleIntervalSpec,
    ScheduleSpec, SchedulePolicy, ScheduleOverlapPolicy, ScheduleState, ScheduleUpdate)
from temporalio.common import RetryPolicy
from .release import require_active_code, delegate
from .shared import SharedService
from .scheduled_operation import ScheduledOperation, operation


def definition(config, identifier):
    request = {'operation': identifier, 'config_sha256': config['config_sha256']}
    operation(config, request)
    every = config['scheduled_operations'][identifier]['interval_seconds']
    return Schedule(action=ScheduleActionStartWorkflow(ScheduledOperation.run, request,
        id='operation-' + identifier, task_queue='office-operations',
        execution_timeout=timedelta(seconds=240), retry_policy=RetryPolicy(maximum_attempts=1,
            maximum_interval=timedelta(seconds=100))),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=every))]),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP,
            catchup_window=timedelta(seconds=min(60, every)), pause_on_failure=False),
        state=ScheduleState(paused=True, note='Prepared from reviewed release; explicit resume required'))


async def validate(client, described, config, identifier, prior=False):
    current, expected = described.schedule, definition(config, identifier)
    args = await client.data_converter.decode(current.action.args)
    if (len(args) != 1 or set(args[0]) != {'operation', 'config_sha256'}
            or args[0]['operation'] != identifier
            or (not prior and args[0]['config_sha256'] != config['config_sha256'])
            or current.action.workflow != 'ScheduledOperation'
            or current.action.id != expected.action.id or current.action.task_queue != 'office-operations'
            or current.action.execution_timeout != expected.action.execution_timeout
            or current.action.retry_policy != expected.action.retry_policy
            or current.policy != expected.policy):
        raise ValueError('Native schedule differs from the accepted operation')
    spec = current.spec
    if (spec.calendars or spec.cron_expressions or spec.skip or spec.start_at or spec.end_at
            or spec.jitter or spec.time_zone_name
            or (not prior and spec.intervals != expected.spec.intervals)):
        raise ValueError('Native schedule scope differs')


async def execution_status(client, described):
    recent = []
    for item in described.info.recent_actions:
        handle = client.get_workflow_handle(item.action.workflow_id,
            run_id=item.action.first_execution_run_id)
        execution = await handle.describe()
        row = {'workflow_id': execution.id, 'status': execution.status.name,
               'scheduled_at': item.scheduled_at.isoformat(), 'started_at': item.started_at.isoformat()}
        if execution.status.name == 'COMPLETED':
            outcome = await asyncio.wait_for(handle.result(), timeout=5)
            row['business_completed'] = outcome.get('result', {}).get('completed') is True
        recent.append(row)
    return recent


async def operate(action, identifier):
    config = require_active_code()
    expected = definition(config, identifier)
    name = 'office-operation-' + identifier
    async with SharedService() as client:
        handle = client.get_schedule_handle(name)
        if action == 'install':
            await client.create_schedule(name, expected)  # duplicate refuses, never resets
        current = await handle.describe()
        await validate(client, current, config, identifier, prior=action == 'rebind')
        if action == 'resume':
            if (current.schedule.state.note or '').startswith('STOPPED'):
                raise ValueError('Stopped operation requires reviewed rebind before resume')
            await handle.unpause(note='Explicit resume of release-bound operation')
        elif action in ('pause', 'stop'):
            # Stop pauses future runs; in-flight bounded operation completes and records
            # effects. It never force-terminates a process in another commitment.
            note = 'STOPPED: future starts disabled' if action == 'stop' or (current.schedule.state.note or '').startswith('STOPPED') else 'PAUSED: bounded run may finish'
            await handle.pause(note=note)
        elif action == 'rebind':
            if not current.schedule.state.paused or current.info.running_actions:
                raise ValueError('Pause and finish in-flight operation before release rebind')
            async def update(inp):
                await validate(client, inp.description, config, identifier, prior=True)
                if not inp.description.schedule.state.paused or inp.description.info.running_actions:
                    raise ValueError('Schedule changed during rebind')
                return ScheduleUpdate(schedule=expected)
            await handle.update(update)
        elif action not in ('install', 'status'):
            raise ValueError('Unknown action')
        after = await handle.describe()
        await validate(client, after, config, identifier)
        recent = await execution_status(client, after)
        return {'operation': identifier, 'config_sha256': config['config_sha256'],
                'paused': after.schedule.state.paused, 'note': after.schedule.state.note,
                'actions': after.info.num_actions,
                'missed_catchup': after.info.num_actions_missed_catchup_window,
                'skipped_overlap': after.info.num_actions_skipped_overlap,
                'running': len(after.info.running_actions),
                'recent_executions': recent,
                'next_times': [d.isoformat() for d in after.info.next_action_times],
                'scope': 'Native schedule observation; inspect operation results for actual business outcome'}


def main():
    delegated = delegate('runtime.operation_schedule', sys.argv[1:])
    if delegated is not None:
        return delegated
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'status', 'resume', 'pause', 'stop', 'rebind'])
    parser.add_argument('operation')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(operate(args.action, args.operation)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
