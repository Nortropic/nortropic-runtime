import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from .activities import execute_codex, execute_claude, review_candidate, publish_candidate
from .workflow import DevelopmentTask
from .shared import ServiceIdentity
from .private_workflow import PrivateAssessment
from .private_activity import private_stage
from .development_workflow import FiniteDevelopment
from .development_activity import development_step
from .development_trial import CapacityTrial, capacity_trial_stage


async def main():
    client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
    with ThreadPoolExecutor(max_workers=1) as executor:
        async with Worker(client, task_queue='development', workflows=[DevelopmentTask, ServiceIdentity, PrivateAssessment, FiniteDevelopment, CapacityTrial],
                          activities=[execute_codex, execute_claude, review_candidate, publish_candidate, private_stage, development_step, capacity_trial_stage], activity_executor=executor,
                          max_concurrent_activities=1):
            await asyncio.Event().wait()


if __name__ == '__main__': asyncio.run(main())
