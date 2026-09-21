"""Synthetic session-selection and closure fixtures, not a G2 pass."""
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from runtime.development_interactive import actual_session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.workspace=self.root/'selected'
        self.folder=self.root/'.codex/sessions'/datetime.now(timezone.utc).strftime('%Y/%m/%d');self.folder.mkdir(parents=True)
    def tearDown(self):self.temp.cleanup()
    def history(self,name='one',complete=True,cwd=None):
        rows=[{'type':'session_meta','payload':{'id':name,'cwd':str(cwd or self.workspace),'source':'cli'}}]
        if complete:rows.append({'type':'event_msg','payload':{'type':'task_complete'}})
        (self.folder/('rollout-'+name+'.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    def read(self):
        with patch('runtime.development_interactive.Path.home',return_value=self.root):
            return actual_session(self.workspace,time.time()-60)
    def test_exact_cwd_and_actual_completed_turn_required(self):
        self.history('unrelated',cwd=self.root/'other');self.history(complete=False)
        with self.assertRaisesRegex(ValueError,'no actual completed'):self.read()
    def test_fresh_selected_history_and_identity_retained(self):
        self.history();identity,raw,source=self.read()
        self.assertEqual(identity,'one');self.assertEqual(source,'cli');self.assertIn(b'task_complete',raw)
    def test_multiple_matching_sessions_are_not_assumed_one_interactive_exit(self):
        self.history();self.history('two')
        with self.assertRaisesRegex(ValueError,'Exactly one'):self.read()


if __name__=='__main__':unittest.main()
