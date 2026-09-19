import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import record_effect
from .workflow import ContinuityProbe


async def main():
    client = await Client.connect('127.0.0.1:7339', namespace='runtime-probe')
    worker = Worker(client, task_queue='nr-compat', workflows=[ContinuityProbe],
                    activities=[record_effect], max_concurrent_activities=1)
    await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
