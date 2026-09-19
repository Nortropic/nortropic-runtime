"""Real Git freeze and fail-closed review protocol checks; no model/remote calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import candidate
from runtime.review import verdict


class ConnectedTests(unittest.TestCase):
    def test_frozen_git_and_scope(self):
        with tempfile.TemporaryDirectory(prefix='nr-connected-') as temp:
            root = Path(temp)
            origin, source, state = (root/x for x in ('origin','source','state'))
            origin.mkdir(); state.mkdir()
            candidate.git(origin, 'init', '-q')
            candidate.git(origin, 'config', 'user.email', 'fixture@example.invalid')
            candidate.git(origin, 'config', 'user.name', 'Runtime fixture')
            (origin/'README').write_text('accepted base\n')
            candidate.git(origin, 'add', '.'); candidate.git(origin, 'commit', '-qm', 'base')
            base = candidate.git(origin, 'rev-parse', 'HEAD')
            subprocess.run(['git','clone','-q',str(origin),str(source)], check=True)
            (source/'tools').mkdir(); (source/'tools/tool.py').write_text('print(42)\n')
            task = {'id':'fixture','base':base,'allowed_paths':['tools/tool.py']}
            with patch.object(candidate,'ROOT',origin), patch.object(candidate,'task_directory',return_value=state):
                result = candidate.prepare(task, 1, source)
                frozen = state/result['workspace_name']
                self.assertEqual(candidate.git(frozen,'rev-parse','HEAD^'),base)
                self.assertEqual(candidate.git(frozen,'show',result['candidate']+':tools/tool.py'), 'print(42)')
                self.assertEqual(result['candidate_files_sha256']['tools/tool.py'],hashlib.sha256(b'print(42)\n').hexdigest())
                (source/'tools/tool.py').write_text('changed after freeze\n')
                self.assertEqual(candidate.git(frozen,'show',result['candidate']+':tools/tool.py'), 'print(42)')
                with self.assertRaises(ValueError): candidate.prepare(task,1,source)
                (source/'README').unlink()
                with self.assertRaises(ValueError): candidate.prepare(task,2,source)
                (source/'README').write_text('accepted base\n')
                (source/'tools/tool.py').unlink(); (source/'tools/tool.py').symlink_to(origin/'README')
                with self.assertRaises((OSError, ValueError)): candidate.prepare(task,2,source)

    def test_review_missing_malformed_conflicting_or_duplicate(self):
        good={'verdict':'approved','blocking_findings':[],'summary':'Brief fulfilled.'}
        with tempfile.TemporaryDirectory(prefix='nr-review-') as temp:
            path=Path(temp)/'events.jsonl'
            def write(text):
                path.write_text(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':text}})+'\n')
            write(json.dumps(good)); self.assertEqual(verdict(path),good)
            path.write_text('');
            with self.assertRaises(ValueError): verdict(path)
            for bad in ('{}','null','not json',json.dumps({**good,'blocking_findings':['blocker']}),
                        json.dumps({**good,'summary':''}),json.dumps({**good,'extra':1}),
                        '{"verdict":"rejected","verdict":"approved","blocking_findings":[],"summary":"x"}'):
                write(bad)
                with self.subTest(bad=bad), self.assertRaises(ValueError): verdict(path)


if __name__=='__main__': unittest.main()
