"""Review evidence classification: defective candidate versus absent judgment."""
import unittest
from runtime.integration import digest
from runtime.review import recovery_kind

class ReviewRecoveryTests(unittest.TestCase):
    def test_only_bound_independent_rejection_permits_repair(self):
        task={'id':'test-review','target':'Nortropic/nortropic-runtime','base':'a'*40,
              'steps':[{}],'acceptance_sha256':'f'*64}
        subject={'task_id':task['id'],'task_sha256':digest(task),'base':task['base'],
                 'candidate':'b'*40,'completed_steps':[0],'acceptance_sha256':'f'*64,
                 'implementation_runs':['author']}
        tests={k:subject[k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
        tests.update(scope='whole_task',terminal_status='completed',passed=True)
        good={**tests,'verdict':'rejected','blocking_findings':['zero violates accepted requirement'],
              'summary':'Concrete reproduction','reviewer_run':'separate-review'}
        self.assertEqual(recovery_kind(task,subject,tests,good),'repair')
        for bad in (None,[], 'invalid', {}, {**good,'candidate':'c'*40},
                    {**good,'reviewer_run':'author'}, {**good,'terminal_status':'incomplete'},
                    {**good,'verdict':'inconclusive'}, {**good,'blocking_findings':[]},
                    {**good,'blocking_findings':['']}, {**good,'summary':''}):
            with self.subTest(review=bad):self.assertEqual(recovery_kind(task,subject,tests,bad),'review_only')
        self.assertEqual(recovery_kind(task,subject,{**tests,'passed':False},good),'review_only')

if __name__=='__main__':unittest.main()
