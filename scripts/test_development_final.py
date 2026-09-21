"""Whole-goal closure remains independent of individual child PASS."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from runtime import development_final as final


class FinalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.control='active';self.events=[]
        def control(value,reason):self.events.append(value);self.control=value
        self.scope=SimpleNamespace(directory=self.root,control=control,inspect=lambda:{'control':self.control,'calls':[]})
        self.config={'runtime_revision':'a'*40,'office_revision':'b'*40,'config_sha256':'c'*64}
        self.workspace=self.root/'calls/fixture/workspace';self.workspace.mkdir(parents=True)
        (self.workspace/'ACTUAL_REPORTS.json').write_text('{}')
    def tearDown(self):self.temp.cleanup()
    def test_missing_qualification_waits_without_model_or_closure(self):
        result=final.prepare(self.scope,self.config,'fixture')
        self.assertTrue(result['proof_wait']);self.assertEqual(self.events,[])
    def test_inconclusive_does_not_become_overall_success(self):
        result={'answer':{'verdict':'inconclusive'},'provider':{'thread_id':'fresh'}}
        with patch.object(final.host,'call_result',return_value=result),patch.object(final.host,'policy',return_value=SimpleNamespace(review=lambda _:False)):
            closed=final.close(self.scope,self.config,'fixture')
        self.assertFalse(closed['whole_goal_complete']);self.assertEqual(self.events,['paused'])
        self.assertFalse((self.root/'final.json').exists())
    def test_independent_approval_closes_only_own_scope_and_reads_it_back(self):
        result={'answer':{'verdict':'approved'},'provider':{'thread_id':'fresh'}}
        with patch.object(final.host,'call_result',return_value=result),patch.object(final.host,'policy',return_value=SimpleNamespace(review=lambda _:True)):
            closed=final.close(self.scope,self.config,'fixture')
        self.assertTrue(closed['whole_goal_complete']);self.assertEqual(self.events,['stopped'])
        self.assertEqual(json.loads((self.root/'final.json').read_text())['scope']['control'],'stopped')

    def test_child_implementer_or_code_reviewer_cannot_close_whole_goal(self):
        (self.workspace/'ACTUAL_REPORTS.json').write_text(json.dumps({'A':{'state':{
            'results':[{'thread_id':'implementer'}],
            'reviews':[{'result':{'reviewer_run':'earlier-reviewer'}}],
            'review':{'reviewer_run':'code-reviewer'}}}}))
        for identity in ('implementer','code-reviewer','earlier-reviewer'):
            result={'answer':{'verdict':'approved'},'provider':{'thread_id':identity}}
            with patch.object(final.host,'call_result',return_value=result),patch.object(final.host,'policy',return_value=SimpleNamespace(review=lambda _:True)):
                with self.assertRaisesRegex(ValueError,'actual child'):final.close(self.scope,self.config,'fixture')
        self.assertEqual(self.events,[]);self.assertFalse((self.root/'final.json').exists())


if __name__=='__main__':unittest.main()
