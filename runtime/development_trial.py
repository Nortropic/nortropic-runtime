"""One named synthetic native capacity trial for AP11 qualification only.

No supplier intake, model, publication, schedule mutation or business result.
The real admission reader and the actual shared activity slot are exercised.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import time
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
with workflow.unsafe.imports_passed_through():
    from .development_model import active_scope
    from .development_capacity import inspect_capacity
    from .private_stage import write
    from .release import ROOT

TRIAL = 'ap11-capacity-watch'
STAGES = [('intake',90),('analysis',480),('review',240),('report',60)]


@activity.defn
def capacity_trial_stage(request: dict) -> dict:
    scope,config=active_scope(request['contract_sha256'])
    if config['development'].get('capacity_trial') != TRIAL:
        raise ValueError('The active release does not allow this named synthetic trial')
    info=activity.info();role=request['role'];mode=request['mode']
    if (mode not in ('build','watch') or info.task_queue!='development'
            or mode=='build' and (info.workflow_id!='ap11-capacity-build' or role not in ('first','following'))
            or mode=='watch' and (not info.workflow_id.startswith(TRIAL+'-') or role not in dict(STAGES))):
        raise ValueError('Unrelated qualification work refused')
    if mode=='build':
        # First occupies the real slot for2s. Following requests the real
        # parent envelope and must yield to the forthcoming watch-shaped work.
        capacity=asyncio.run(inspect_capacity(3 if role=='first' else 1500))
        if not capacity['available']:
            return {'capacity_wait':True,'reason':capacity['reason']}
    dest=ROOT/'.runtime/ap11/capacity';dest.mkdir(parents=True,exist_ok=True,mode=0o700)
    name=mode+'-'+role
    record={'synthetic':True,'workflow_id':info.workflow_id,'run_id':info.workflow_run_id,
            'role':role,'scheduled_at':info.scheduled_time.isoformat(),'started_at':info.started_time.isoformat(),
            'host_started_at':datetime.now(timezone.utc).isoformat(),
            'queue_seconds':(info.started_time-info.current_attempt_scheduled_time).total_seconds(),
            'start_to_close_seconds':info.start_to_close_timeout.total_seconds(),
            'schedule_to_close_seconds':info.schedule_to_close_timeout.total_seconds() if info.schedule_to_close_timeout else None,
            'heartbeat_seconds':info.heartbeat_timeout.total_seconds() if info.heartbeat_timeout else None}
    # Exclusive role claim: this exact trial cannot be run again to replace a
    # failed result with a nicer one. Native redelivery also fails closed.
    write(dest/(name+'-start.json'),record)
    until=time.monotonic()+2
    while time.monotonic()<until:
        activity.heartbeat(name)
        if activity.is_cancelled():raise RuntimeError('Synthetic trial cancelled')
        time.sleep(.1)
    record.update(completed=True,finished_at=datetime.now(timezone.utc).isoformat(),supplier_intake=False,model=False)
    write(dest/(name+'-result.json'),record)
    return record


@workflow.defn
class CapacityTrial:
    @workflow.run
    async def run(self, request: dict) -> dict:
        self.current={'phase':'running','synthetic':True,'stages':[],'waits':[]}
        stages=STAGES if request['mode']=='watch' else [('first',3),('following',1500)]
        for role,seconds in stages:
            while True:
                # Same four AP10 native stage bounds/cancellation/heartbeat.
                result=await workflow.execute_activity(capacity_trial_stage,{**request,'role':role},
                    start_to_close_timeout=timedelta(seconds=seconds+10),
                    schedule_to_close_timeout=timedelta(seconds=seconds+15),
                    heartbeat_timeout=timedelta(seconds=10),retry_policy=RetryPolicy(maximum_attempts=1),
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED)
                if result.get('capacity_wait'):
                    self.current['waits'].append({'at':workflow.now().isoformat(),'role':role,'result':result})
                    await workflow.sleep(30)
                    continue
                self.current['stages'].append(result);break
        self.current['phase']='completed'
        return self.current

    @workflow.query
    def state(self) -> dict:return self.current
