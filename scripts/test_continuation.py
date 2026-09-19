import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from runtime import continuation
from runtime.candidate import git
from runtime.integration import digest


class ContinuationTest(unittest.TestCase):
    def test_preserve_exact_inherited_work_and_never_overwrite_partial_state(self):
        with tempfile.TemporaryDirectory(prefix='nr-continuation-') as temp:
            root=Path(temp).resolve();git(root,'init','-q')
            git(root,'config','user.name','Fixture');git(root,'config','user.email','fixture@example.invalid')
            (root/'AGENTS.md').write_text('fixture');git(root,'add','.');git(root,'commit','-qm','old base')
            oldbase=git(root,'rev-parse','HEAD')
            (root/'support.txt').write_text('new support');git(root,'add','.');git(root,'commit','-qm','new base')
            base=git(root,'rev-parse','HEAD')
            state=root/'state';state.mkdir();evidence=root/'evidence';evidence.mkdir()
            candidate=state/'candidate'
            git(root,'clone','--no-hardlinks',str(root),str(candidate));git(candidate,'checkout','--detach',oldbase)
            (candidate/'tools').mkdir();(candidate/'tools/a.py').write_bytes(b'preserved source\n')
            snapshot=evidence/'attempt-2/candidate/tools';snapshot.mkdir(parents=True)
            (snapshot/'a.py').write_bytes(b'preserved source\n')
            old={'id':'fixture','base':oldbase,'allowed_paths':['tools/a.py'],'steps':[{'provider':'codex','prompt':'one'},
                 {'provider':'claude','prompt':'two','waiting_reason':'access'},{'provider':'codex','prompt':'three'}]}
            new=copy.deepcopy(old);new['base']=base;new['steps'][1].pop('waiting_reason')
            new['continuation']={'previous_task_sha256':digest(old),'expected_attempt':2,'reason':'qualified','evidence':'fixture'}
            native={'phase':'waiting_access','attempts':2}
            def load(_):return json.loads((state/'accepted.json').read_text()) if (state/'accepted.json').exists() else old
            with patch.object(continuation,'ROOT',root),patch.object(continuation,'task_directory',return_value=state),\
                 patch.object(continuation,'evidence_directory',return_value=evidence),patch.object(continuation,'load',side_effect=load),\
                 patch.object(continuation.Publisher,'require_base'):
                (state/'candidate-continuation').mkdir()
                with self.assertRaises(ValueError):continuation.prepare(new,b'verifier',b'brief',base,native)
                self.assertEqual((candidate/'tools/a.py').read_bytes(),b'preserved source\n')
                (state/'candidate-continuation').rmdir()
                receipt=continuation.prepare(new,b'verifier',b'brief',base,native)
                self.assertEqual(git(candidate,'rev-parse','HEAD'),base)
                self.assertEqual(git(state/'candidate-before-continuation','rev-parse','HEAD'),oldbase)
                self.assertEqual((candidate/'tools/a.py').read_bytes(),b'preserved source\n')
                self.assertEqual(continuation.prepare(new,b'verifier',b'brief',base,native),receipt)
                (candidate/'tools/a.py').write_text('unexpected change')
                with self.assertRaises(ValueError):continuation.prepare(new,b'verifier',b'brief',base,native)

if __name__=='__main__':unittest.main()
