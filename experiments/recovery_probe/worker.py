"""Actual implementation activity; harmless provider and fake review/publication."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker
from runtime.activities import execute_codex
from runtime.integration import require_gate
from runtime.profile import ROOT
from runtime.task import load
from runtime.workflow import DevelopmentTask

original_popen=subprocess.Popen

def fixture_popen(command,*args,**kwargs):
    if command[:3]==[sys.executable,'-m','runtime.attempt']:
        command=[sys.executable,'-m','experiments.recovery_probe.fixture_attempt',*command[3:]]
    return original_popen(command,*args,**kwargs)

subprocess.Popen=fixture_popen

def note(kind):
    with (ROOT/'evidence/recovery-probe/calls.jsonl').open('a') as out:
        out.write(json.dumps({'kind':kind,'task':activity.info().workflow_id})+'\n')

@activity.defn(name='review_candidate')
async def review(request):
    note('fixture_review');s=request['subject']
    r={k:s[k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
    r.update(scope='whole_task',terminal_status='completed',verdict='approved',blocking_findings=[],reviewer_run='fixture-independent-review')
    return r

@activity.defn(name='publish_candidate')
async def publish(request):
    require_gate(load(request['task_id'],request['task_digest']),request['subject'],request['tests'],request['review'])
    note('fixture_publication')
    return {'merged':True,'fixture_only':True,'remote_publications':0}

async def main():
    client=await Client.connect('127.0.0.1:7339',namespace='nr-recovery-fixture')
    with ThreadPoolExecutor(max_workers=1) as executor:
        async with Worker(client,task_queue='recovery-fixture',workflows=[DevelopmentTask],
                          activities=[execute_codex,review,publish],activity_executor=executor,
                          max_concurrent_activities=1):
            await asyncio.Event().wait()

if __name__=='__main__':asyncio.run(main())
