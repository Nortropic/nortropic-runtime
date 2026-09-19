import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from runtime import run
from runtime.candidate import git


class SubmissionTest(unittest.TestCase):
    def test_input_must_be_preserved_before_preparation(self):
        with tempfile.TemporaryDirectory(prefix='nr-submit-') as temp:
            root=Path(temp).resolve()
            git(root,'init','-q');git(root,'config','user.name','Fixture');git(root,'config','user.email','fixture@example.invalid')
            (root/'README').write_text('base');git(root,'add','.');git(root,'commit','-qm','base')
            base=git(root,'rev-parse','HEAD')
            (root/'tasks').mkdir();(root/'acceptance').mkdir()
            verifier=b'def verify(workspace): return {"passed": True}\n'
            (root/'acceptance/check.py').write_bytes(verifier)
            (root/'tasks/brief.md').write_text('A preserved brief')
            task={'id':'fixture','target':'Nortropic/nortropic-runtime','base':base,
                  'allowed_paths':['tools/a.py'],'attempt_seconds':2,'automatic_retries':0,
                  'steps':[{'provider':'codex','prompt':'fixture'}],
                  'acceptance':'acceptance/check.py','acceptance_sha256':hashlib.sha256(verifier).hexdigest(),'brief':'tasks/brief.md'}
            selected=root/'tasks/task.json';selected.write_text(json.dumps(task))
            git(root,'add','tasks/task.json');git(root,'commit','-qm','task only')
            with patch.object(run,'ROOT',root), patch.object(run,'task_directory',return_value=root/'state'),patch.object(run,'evidence_directory',return_value=root/'evidence'):
                with self.assertRaises(subprocess.CalledProcessError):run.prepare(selected)
                self.assertFalse((root/'state').exists())
                git(root,'add','tasks/brief.md','acceptance/check.py');git(root,'commit','-qm','accepted inputs')
                actual,output=run.prepare(selected)
                self.assertEqual(actual,task)
                self.assertEqual((root/'state/acceptance.py').read_bytes(),verifier)
                self.assertEqual((root/'state/brief.md').read_text(),'A preserved brief')
                with self.assertRaises(ValueError):run.prepare(selected)

if __name__=='__main__':unittest.main()
