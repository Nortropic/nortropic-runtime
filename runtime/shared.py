"""Attach to the verified shared engine; attachment never owns its processes."""
import asyncio
import json
import os
from pathlib import Path
import subprocess

from temporalio import workflow
from temporalio.client import Client
with workflow.unsafe.imports_passed_through():
    from .release import ROOT, require_active_code


@workflow.defn
class ServiceIdentity:
    @workflow.run
    async def run(self, identity: dict):
        self.identity = identity
        await workflow.wait_condition(lambda: False)

    @workflow.query
    def describe(self):
        return self.identity


def process_identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip() if result.returncode == 0 else ''


class SharedService:
    migrated = False

    async def __aenter__(self):
        config = require_active_code()
        receipt = json.loads((ROOT / '.runtime/ap10/service.json').read_text())
        if receipt.get('config_sha256') != config['config_sha256']:
            raise ValueError('Shared service has a different configuration')
        expected = {k:config[k] for k in ('config_sha256','database','runtime_revision','office_revision')}
        if receipt.get('native_identity') != expected:
            raise ValueError('Service receipt does not bind the active configuration')
        for role in ('daemon', 'engine', 'worker'):
            recorded = receipt[role]
            if not recorded['identity'] or process_identity(recorded['pid']) != recorded['identity']:
                raise ValueError('Shared service process identity unavailable: ' + role)
        client = await asyncio.wait_for(Client.connect('127.0.0.1:7339', namespace='nortropic-runtime'), 5)
        identity = await asyncio.wait_for(client.get_workflow_handle(receipt['identity_workflow']).query(
            ServiceIdentity.describe), 10)
        if identity != receipt['native_identity']:
            raise ValueError('Live native service identity differs')
        return client

    async def __aexit__(self, *_):
        # The calling command/observation owns no server or worker process.
        return False
