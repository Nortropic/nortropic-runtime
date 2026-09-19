import copy
import json
from pathlib import Path
import unittest
from runtime.integration import digest
from runtime.revision import require_revision


class AccessRevisionTest(unittest.TestCase):
    def setUp(self):
        self.old=json.loads(Path('tasks/run-report.json').read_text())
        self.new=copy.deepcopy(self.old)
        self.new['steps'][1].pop('waiting_reason')
        self.new.update(base='f'*40,acceptance='acceptance/run_report_complete.py',acceptance_sha256='a'*64,
                        brief='tasks/run-report-complete.md',continuation={'previous_task_sha256':digest(self.old),
                        'expected_attempt':2,'reason':'access restored and qualified','evidence':'fixture'})

    def test_same_task_continues_with_bound_history(self):
        self.assertTrue(require_revision(self.old,self.new,1,2))

    def test_scope_and_history_cannot_be_reset(self):
        for field,value in [('id','renamed'),('allowed_paths',['tools/other.py']),('attempt_seconds',900),('outcome','new scope')]:
            new=copy.deepcopy(self.new);new[field]=value
            with self.assertRaises(ValueError):require_revision(self.old,new,1,2)
        for field,value in [('expected_attempt',0),('previous_task_sha256','b'*64),('reason','')]:
            new=copy.deepcopy(self.new);new['continuation'][field]=value
            with self.assertRaises(ValueError):require_revision(self.old,new,1,2)
        new=copy.deepcopy(self.new);new['steps'][1]['prompt']='different scope'
        with self.assertRaises(ValueError):require_revision(self.old,new,1,2)

if __name__=='__main__':unittest.main()
