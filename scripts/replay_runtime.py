"""Replay preserved native histories without starting activities or calling models."""
import asyncio
import json
from pathlib import Path
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer
from runtime.workflow import DevelopmentTask


async def main():
    sources=[('runtime-run-report-1','evidence/accepted-task/observations/cac8d5c56d044ea7a65f20180fee0252/history.json'),
             ('runtime-evidence-index-1','evidence/runs/runtime-evidence-index-1/history.json'),
             ('fixture-abrupt-worker','evidence/recovery-probe/history.json')]
    results=[]
    for task,path in sources:
        events=json.loads(Path(path).read_text())
        history=WorkflowHistory.from_json(task,{'events':events})
        await Replayer(workflows=[DevelopmentTask]).replay_workflow(history)
        results.append({'workflow':task,'history':path,'events':len(events),'replay_passed':True})
    print(json.dumps({'passed':True,'model_calls':0,'histories':results},indent=2))

if __name__=='__main__':asyncio.run(main())
