import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from .activities import execute_codex, review_candidate, publish_candidate
from .workflow import DevelopmentTask


async def main():
    client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
    with ThreadPoolExecutor(max_workers=1) as executor:
        async with Worker(client, task_queue='development', workflows=[DevelopmentTask],
                          activities=[execute_codex, review_candidate, publish_candidate], activity_executor=executor,
                          max_concurrent_activities=1):
            await asyncio.Event().wait()


if __name__ == '__main__': asyncio.run(main())
