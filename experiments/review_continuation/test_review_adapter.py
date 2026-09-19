"""Numbered real adapter protocol with a declared no-model invoke substitute."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from runtime import activities

class ReviewAdapterTest(unittest.TestCase):
    def test_repeated_review_uses_new_guardian_identity_and_retains_prior_receipt(self):
        with tempfile.TemporaryDirectory(prefix='nr-review-adapter-') as temp:
            root=Path(temp); workspace=root/'commit-1';workspace.mkdir()
            task={'id':'adapter-test','allowed_paths':['tools/a.py'],'attempt_seconds':300}
            subject={'task_id':task['id'],'task_sha256':'a'*64,'candidate':'b'*40,'acceptance_sha256':'c'*64}
            calls=[]
            def invoke(request):
                calls.append(request.copy());output=root/('review-'+str(request['number']));output.mkdir()
                if request['number']>1:self.assertTrue(request['change_reason'])
                decision={'verdict':'approved','blocking_findings':[],'summary':'Adapter fixture'}
                (output/'events.jsonl').write_text(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(decision)}})+'\n')
                return {'provider_completed':True,'thread_id':'review-'+str(request['number'])}
            with patch.object(activities,'load',return_value=task),patch.object(activities,'task_directory',return_value=root),patch.object(activities,'evidence_directory',return_value=root),patch.object(activities,'git',return_value='b'*40),patch.object(activities,'read_regular',return_value=b'Accepted brief'),patch.object(activities,'invoke',side_effect=invoke):
                request={'task_id':task['id'],'task_digest':'a'*64,'subject':subject,'workspace_name':'commit-1'}
                first=activities.review_candidate(request)
                original=(root/'review-1/decision.json').read_bytes()
                second=activities.review_candidate({**request,'review_number':2,'change_reason':'Inspected prerequisite restored'})
            self.assertEqual((root/'review-1/decision.json').read_bytes(),original)
            self.assertNotEqual(first['reviewer_run'],second['reviewer_run'])
            self.assertEqual([x['number'] for x in calls],[1,2])
            self.assertTrue(all(x['role']=='review' and x['seconds']==180 for x in calls))
            self.assertEqual(second['candidate'],first['candidate'])

if __name__=='__main__':unittest.main()
