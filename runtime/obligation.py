"""Explicit operator control of one native Temporal Schedule; status only reads."""
import argparse
import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone
import json
import sys
from temporalio.client import (Schedule, ScheduleActionStartWorkflow, ScheduleSpec,
    ScheduleCalendarSpec, ScheduleRange, SchedulePolicy, ScheduleOverlapPolicy,
    ScheduleState, ScheduleUpdate)
from temporalio.common import RetryPolicy
from temporalio.client import WorkflowFailureError
from .release import require_active_code, delegate
from .shared import SharedService
from .private_workflow import PrivateAssessment
from .private_stage import cleanup_private_run, check_private_processes

NAME='office-python-temporal'


def daily():
    return ScheduleSpec(calendars=[ScheduleCalendarSpec(hour=[ScheduleRange(9)],
        minute=[ScheduleRange(0)],second=[ScheduleRange(0)])],time_zone_name='Europe/Stockholm')


def once(at):
    return ScheduleSpec(calendars=[ScheduleCalendarSpec(year=[ScheduleRange(at.year)],
        month=[ScheduleRange(at.month)],day_of_month=[ScheduleRange(at.day)],
        hour=[ScheduleRange(at.hour)],minute=[ScheduleRange(at.minute)],
        second=[ScheduleRange(at.second)])],time_zone_name='UTC')


def definition(config, test_at=None):
    return Schedule(action=ScheduleActionStartWorkflow(PrivateAssessment.run,
        {'obligation':NAME,'config_sha256':config['config_sha256'],'mode':'test' if test_at else 'daily'},
        id='ap10-'+NAME,task_queue='development',execution_timeout=timedelta(seconds=1200),
        run_timeout=timedelta(seconds=1200),retry_policy=RetryPolicy(maximum_attempts=1)),
        spec=once(test_at) if test_at else daily(),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.BUFFER_ONE,
            catchup_window=timedelta(days=1),pause_on_failure=False),
        state=ScheduleState(paused=True,note='AP10 explicitly installed paused',
            limited_actions=bool(test_at),remaining_actions=1 if test_at else 0))


def status(description):
    s=description.schedule
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'obligation':NAME,
        'paused':s.state.paused,'note':s.state.note,
        'limited_actions':s.state.limited_actions,'remaining_actions':s.state.remaining_actions,
        'schedule':dataclasses.asdict(s.spec),'policy':dataclasses.asdict(s.policy),
        'next_action_times':[x.isoformat() for x in description.info.next_action_times],
        'actions':description.info.num_actions,
        'missed_catchup':description.info.num_actions_missed_catchup_window,
        'skipped_overlap':description.info.num_actions_skipped_overlap,
        'running':[dataclasses.asdict(x) for x in description.info.running_actions],
        'recent':[dataclasses.asdict(x) for x in description.info.recent_actions],
        'meaning':'Dated native schedule observation, not a successful source intake or reviewed judgment'}


async def operate(action, after_seconds=None):
    config=require_active_code()
    async with SharedService() as client:
        handle=client.get_schedule_handle(NAME)
        if action=='install':
            # Duplicate installation fails; it never resets a paused/stopped schedule.
            await client.create_schedule(NAME,definition(config))
        elif action in ('daily','test'):
            current=await handle.describe()
            if not current.schedule.state.paused or current.info.running_actions:
                raise ValueError('Pause and finish own in-flight work before schedule/config replacement')
            at=None
            if action=='test':
                if type(after_seconds) is not int or not 30<=after_seconds<=600:
                    raise ValueError('Explicit one-shot qualification delay30..600 required')
                at=datetime.now(timezone.utc)+timedelta(seconds=after_seconds)
            await handle.update(lambda _:ScheduleUpdate(schedule=definition(config,at)))
        elif action=='resume':
            current=await handle.describe()
            # Stopped is distinct from paused. Explicit daily/test reconfiguration
            # is required before resuming a terminated obligation.
            if current.schedule.state.note.startswith('STOPPED'):
                raise ValueError('Stopped obligation requires explicit reviewed reactivation')
            await handle.unpause(note='AP10 explicit operator resume; no automatic login unpause')
        elif action in ('pause','stop'):
            prior=await handle.describe()
            note='STOPPED: AP10 explicit stop' if action=='stop' or prior.schedule.state.note.startswith('STOPPED') else 'PAUSED: in-flight round may finish'
            await handle.pause(note=note)
            if action=='stop':
                current=await handle.describe()
                for execution in current.info.running_actions:
                    # These IDs come from THIS native schedule, never list all builds.
                    run=client.get_workflow_handle(execution.workflow_id,
                        first_execution_run_id=execution.first_execution_run_id)
                    await run.cancel()
                    try:await asyncio.wait_for(run.result(),30)
                    except WorkflowFailureError:pass
                    cleanup_private_run(execution.first_execution_run_id)
                check_private_processes()  # Also refuse false clean stop after an older failed round.
        elif action!='status':raise ValueError('Unknown control action')
        return status(await handle.describe())


def main():
    delegated=delegate('runtime.obligation',sys.argv[1:])
    if delegated is not None:return delegated
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['install','daily','test','resume','pause','stop','status'])
    p.add_argument('--after-seconds',type=int)
    args=p.parse_args()
    result=asyncio.run(operate(args.action,args.after_seconds))
    print(json.dumps(result,indent=2,default=str))
    return 0


if __name__=='__main__':raise SystemExit(main())
