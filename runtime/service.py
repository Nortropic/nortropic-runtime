"""Bounded local Temporal lifecycle; native service remains the only state engine."""
import asyncio
import fcntl
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import time

from temporalio.client import Client
from scripts.bounded import stop_group
from .profile import ROOT


class LocalService:
    def __init__(self, database, output, namespace='nortropic-runtime', seed_database=None):
        self.database, self.output = Path(database), Path(output)
        self.namespace = namespace
        self.seed_database = Path(seed_database) if seed_database else None
        self.proc = self.log = self.lock = None
        self.migrated = False

    async def __aenter__(self):
        self.output.mkdir(parents=True, exist_ok=False)
        self.lock = (ROOT / '.runtime/engine.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for port in (7339, 7340, 7341):
                with socket.socket() as sock: sock.bind(('127.0.0.1', port))
            self.database.parent.mkdir(parents=True, exist_ok=True)
            if not self.database.exists() and self.seed_database is not None:
                with sqlite3.connect('file:' + str(self.seed_database) + '?mode=ro', uri=True) as source, sqlite3.connect(self.database) as target:
                    source.backup(target)
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Migrated native state failed SQLite integrity check')
                self.migrated = True
                (self.output / 'migration.json').write_text(json.dumps({'source': str(self.seed_database), 'destination': str(self.database), 'source_preserved': True, 'integrity_check': 'ok'}, indent=2)+'\n')
            command = [str(ROOT / '.runtime/bin/temporal-1.9.1'), '--disable-config-env',
                       '--disable-config-file', 'server', 'start-dev', '--ip', '127.0.0.1',
                       '--port', '7339', '--http-port', '7340', '--metrics-port', '7341',
                       '--namespace', self.namespace, '--headless', '--db-filename', str(self.database)]
            self.log = (self.output / 'server.log').open('wb')
            self.proc = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                                         cwd=ROOT, start_new_session=True)
            (self.output / 'process.json').write_text(json.dumps({'pid': self.proc.pid, 'command': command}, indent=2)+'\n')
            end = time.monotonic() + 15
            while time.monotonic() < end:
                if self.proc.poll() is not None: raise RuntimeError('Local engine exited during startup')
                try:
                    client = await asyncio.wait_for(Client.connect('127.0.0.1:7339', namespace=self.namespace), 1)
                    if self.proc.poll() is not None: raise RuntimeError('Local engine exited during connection')
                    return client
                except (RuntimeError, TimeoutError):
                    await asyncio.sleep(.2)
            raise TimeoutError('Local engine startup exceeded15 seconds')
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *_):
        removed = self.proc is None or stop_group(self.proc)
        if self.log: self.log.close()
        if self.lock: self.lock.close()
        (self.output / 'cleanup.json').write_text(json.dumps({'process_group_removed': removed})+'\n')
        if not removed: raise RuntimeError('Local engine process group remains; inspect before restart')
