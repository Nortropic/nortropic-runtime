"""Pure staging/control profile fixtures; never switch the active service."""
import hashlib
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from scripts import install_ap11, install_ap10
from scripts.test_development_scope import contract


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()/'runtime';self.root.mkdir()
        self.selected=self.root.parent/'nortropic-projektkontor/evidence/ap11/local/selected';self.selected.mkdir(parents=True)
        self.inputs={'authority.md':b'accepted authority','goal.md':b'frozen overall acceptance'}
        self.contract=contract();self.contract.update(authority_sha256=hashlib.sha256(self.inputs['authority.md']).hexdigest(),acceptance_sha256=hashlib.sha256(self.inputs['goal.md']).hexdigest())
        self.inputs['contract.json']=json.dumps(self.contract).encode()
        for n,v in self.inputs.items():(self.selected/n).write_bytes(v)
        self.prior=self.root/'old';(self.prior/'context').mkdir(parents=True);(self.prior/'context/selected.md').write_bytes(b'preserved exact AP10 context')
        self.config={'directory':str(self.prior),'files':{'context/selected.md':install_ap10.sha(self.prior/'context/selected.md')}}
        self.path=self.root/'new/config.json';self.path.parent.mkdir();self.path.write_text(json.dumps({'files':{},'marker':'unchanged'}))
    def tearDown(self):self.temp.cleanup()

    def stage(self):
        with patch.object(install_ap11,'ROOT',self.root),patch.object(install_ap11,'installed',return_value=self.config),patch.object(install_ap11,'stage',return_value=self.path):
            return install_ap11.stage_development(self.contract['runtime_revision'],self.contract['office_revision'],self.selected)

    def test_preserves_context_and_binds_only_selected_goal_without_activation(self):
        value=json.loads(self.stage().read_text())
        self.assertEqual((self.path.parent/'context/selected.md').read_bytes(),(self.prior/'context/selected.md').read_bytes())
        self.assertEqual(value['development']['contract_sha256'],install_ap11.digest(self.contract))
        self.assertEqual(value['marker'],'unchanged')
        self.assertFalse((self.root/'.runtime/ap10/active.json').exists())
        self.assertFalse((self.root/'.runtime/ap11/application').exists())

    def test_changed_authority_or_extra_private_file_refused(self):
        (self.selected/'authority.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'must match'):self.stage()
        (self.selected/'raw.txt').write_text('must never copy')
        with self.assertRaisesRegex(ValueError,'only the exact'):self.stage()

    def test_old_context_change_refused(self):
        (self.prior/'context/selected.md').write_text('changed old context')
        with self.assertRaisesRegex(ValueError,'AP10 context changed'):self.stage()

    def test_same_host_auth_only_for_explicit_development_plist(self):
        with patch.object(install_ap10,'ROOT',self.root):
            old=plistlib.loads(install_ap10.plist(self.path))
            self.assertNotIn('GIT_CONFIG_COUNT',old['EnvironmentVariables'])
            self.stage()
            new=plistlib.loads(install_ap10.plist(self.path))
        self.assertEqual(new['EnvironmentVariables']['GIT_CONFIG_VALUE_1'],'!gh auth git-credential')
        self.assertEqual(new['Label'],old['Label']);self.assertEqual(new['RunAtLoad'],old['RunAtLoad'])
        self.assertFalse(new['KeepAlive']);self.assertNotIn('StartInterval',new)
        from runtime.profile import environment
        with patch.dict('os.environ',new['EnvironmentVariables'],clear=True):
            self.assertNotIn('GIT_CONFIG_COUNT',environment())


if __name__=='__main__':unittest.main()
