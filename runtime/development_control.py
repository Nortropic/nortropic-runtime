"""Explicit operator controls for the one finite goal, never a second engine."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys

from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode
from .development_model import active_scope
from .development_workflow import FiniteDevelopment
from .release import delegate, require_active_code
from .shared import SharedService

NAME = 'office-ap11'


async def operate(action, reason=None):
    config = require_active_code()
    scope, _ = active_scope(config.get('development', {}).get('contract_sha256'))
    if action in ('pause','resume','stop'):
        if not isinstance(reason,str) or not reason.strip():
            raise ValueError('Explicit scoped reason required')
        if not (action=='stop' and scope.inspect()['control'] in ('stopped','revoked','exhausted')):
            scope.control({'pause':'paused','resume':'active','stop':'stopped'}[action],reason)
    async with SharedService() as client:
        handle = client.get_workflow_handle(NAME)
        if action in ('start','interactive-start'):
            if scope.inspect()['control'] != 'active':
                raise ValueError('The finite goal is not active')
            await client.start_workflow(FiniteDevelopment.run,scope.expected,id=NAME,task_queue='development',
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        elif action == 'stop':
            # Scope is closed before cancellation, so queued task starts and
            # new publication effects remain denied even if cancellation lags.
            errors=[]
            for task_id in [*scope.inspect()['tasks'],NAME]:
                try:
                    await asyncio.wait_for(client.get_workflow_handle(task_id).cancel(),10)
                except RPCError as error:
                    if error.status != RPCStatusCode.NOT_FOUND:
                        errors.append({'workflow':task_id,'status':str(error.status)})
                except TimeoutError:
                    errors.append({'workflow':task_id,'status':'cancellation readback timeout'})
            if errors:
                raise RuntimeError('Scope is stopped; native cancellation requires inspection: '+json.dumps(errors))
        elif action not in ('status','pause','resume'):
            raise ValueError('Unknown finite-goal action')
        try:
            native = await handle.query(FiniteDevelopment.state)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:raise
            native = {'available':False,'reason':'Named native workflow has not been found; no execution or success inferred'}
        return {'observed_at':datetime.now(timezone.utc).isoformat(),'scope':scope.inspect(),
                'native':native,'config_sha256':config['config_sha256'],
                'meaning':'Dated native observation, not whole-goal approval; status starts no work'}


def main():
    delegated=delegate('runtime.development_control',sys.argv[1:])
    if delegated is not None:return delegated
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['interactive-start','status','pause','resume','stop']);parser.add_argument('--reason')
    args=parser.parse_args()
    if args.action=='interactive-start':
        from .development_interactive import prepare,execute
        config=require_active_code();request=prepare(config['development']['contract_sha256'])
        # Start the waiting native parent BEFORE the interactive handover.
        asyncio.run(operate('interactive-start'))
        result=execute(request);print(json.dumps(result,indent=2));return 0 if result['completed'] else 1
    print(json.dumps(asyncio.run(operate(args.action,args.reason)),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
