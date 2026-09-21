"""Isolated real Temporal identity workflow; no model or production DB access."""
import asyncio
import json
from pathlib import Path
import uuid
from temporalio.worker import Worker
from runtime.shared import ServiceIdentity
from runtime.service import LocalService


async def main():
    home=Path('.runtime/ap10/build-evidence')/('identity-'+uuid.uuid4().hex);home.mkdir(parents=True)
    async with LocalService(home/'isolated.sqlite',home/'service') as client:
        async with Worker(client,task_queue='identity-test',workflows=[ServiceIdentity]):
            handle=await client.start_workflow(ServiceIdentity.run,{'scope':'isolated','code':'fixture'},id='identity-'+uuid.uuid4().hex,task_queue='identity-test')
            actual=await asyncio.wait_for(handle.query(ServiceIdentity.describe),15)
            assert actual=={'scope':'isolated','code':'fixture'}
            await handle.cancel()
    (home/'result.json').write_text(json.dumps({'passed':True,'model_calls':0,'canonical_db_used':False,'identity':actual},indent=2)+'\n')
    print(home)


if __name__=='__main__':asyncio.run(main())
