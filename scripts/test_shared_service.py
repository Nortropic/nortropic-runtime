import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from runtime import release, shared
from scripts.install_ap10 import plist
import plistlib


class SharedTests(unittest.TestCase):
    def test_nested_unbound_instructions_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'tasks/id/candidate';work.mkdir(parents=True)
            with patch.object(release,'require_active_code',return_value={'instruction_guards':{}}):
                release.require_workspace_instructions(work)
                nested=work.parent/'AGENTS.override.md';nested.write_text('Unexpected instruction')
                with self.assertRaisesRegex(ValueError,'Unbound intermediate'):
                    release.require_workspace_instructions(work)
                nested.unlink();(work/'.codex').mkdir();(work/'.codex/config.toml').write_text('model="other"')
                with self.assertRaisesRegex(ValueError,'workspace-specific'):
                    release.require_workspace_instructions(work)

    def test_pinned_bytes_and_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home=root/'.runtime/ap10';directory=home/'releases/r1';directory.mkdir(parents=True)
            code=directory/'runtime/mod.py';code.parent.mkdir();code.write_text('original')
            conf=directory/'config.json';value=dict(host_root=str(root),office_root=str(root.parent/'nortropic-projektkontor'),database=str(root/'.runtime/runtime.sqlite'),files={'runtime/mod.py':release.sha(code)})
            with patch.object(release,'ROOT',root):value['instruction_guards']=release.instruction_guards()
            conf.write_text(json.dumps(value));pointer=home/'active.json';pointer.write_text(json.dumps({'config':str(conf),'sha256':release.sha(conf)}))
            with patch.object(release,'ROOT',root),patch.object(release,'ACTIVE',pointer):
                self.assertEqual(release.installed()['database'],value['database'])
                # A live checkout change does not touch frozen module bytes.
                (root/'mod.py').write_text('working branch change')
                self.assertEqual(release.installed()['files'],value['files'])
                (root/'AGENTS.md').write_text('New branch instruction')
                with self.assertRaisesRegex(ValueError,'instruction/configuration inputs changed'):release.installed()
                (root/'AGENTS.md').unlink()
                code.write_text('tamper')
                with self.assertRaisesRegex(ValueError,'active code changed'):release.installed()
                code.write_text('original');value['database']=str(root/'second.sqlite');conf.write_text(json.dumps(value));pointer.write_text(json.dumps({'config':str(conf),'sha256':release.sha(conf)}))
                with self.assertRaisesRegex(ValueError,'canonical database'):release.installed()

    def test_stale_or_wrong_process_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home=root/'.runtime/ap10';home.mkdir(parents=True)
            config=dict(config_sha256='config',database='db',runtime_revision='r',office_revision='o')
            receipt={'config_sha256':'config','native_identity':config,'daemon':{'pid':4,'identity':'old process'}}
            (home/'service.json').write_text(json.dumps(receipt))
            with patch.object(shared,'ROOT',root),patch.object(shared,'require_active_code',return_value=config),patch.object(shared,'process_identity',return_value='reused pid'),patch.object(shared.Client,'connect',new_callable=AsyncMock) as connect:
                with self.assertRaisesRegex(ValueError,'identity unavailable'):
                    asyncio.run(shared.SharedService().__aenter__())
                connect.assert_not_called()

    def test_wrong_native_identity_and_attachment_cleanup(self):
        async def run(root):
            service=shared.SharedService()
            with self.assertRaisesRegex(ValueError,'native service identity'):
                await service.__aenter__()
            # Detachment must never kill the shared engine/worker.
            self.assertFalse(await service.__aexit__(None,None,None))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home=root/'.runtime/ap10';home.mkdir(parents=True)
            config=dict(config_sha256='config',database='db',runtime_revision='r',office_revision='o')
            receipt=dict(config_sha256='config',identity_workflow='identity',native_identity=config,**{r:{'pid':1,'identity':'process'} for r in ('daemon','engine','worker')})
            (home/'service.json').write_text(json.dumps(receipt))
            client=unittest.mock.Mock();client.get_workflow_handle.return_value.query=AsyncMock(return_value={'wrong':True})
            with patch.object(shared,'ROOT',root),patch.object(shared,'require_active_code',return_value=config),patch.object(shared,'process_identity',return_value='process'),patch.object(shared.Client,'connect',new_callable=AsyncMock,return_value=client):
                asyncio.run(run(root))

    def test_login_is_not_a_second_scheduler_or_retry_loop(self):
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config.json';config.write_text('{}')
            value=plistlib.loads(plist(config))
            self.assertTrue(value['RunAtLoad']);self.assertFalse(value['KeepAlive'])
            for key in ('StartInterval','StartCalendarInterval','UserName','Sockets'):
                self.assertNotIn(key,value)


if __name__=='__main__':unittest.main()
