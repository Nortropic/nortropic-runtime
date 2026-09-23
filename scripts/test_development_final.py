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


class ContinuationClosureTests(unittest.TestCase):
    """G6 examination: the continued half of an interruption in its own run cannot close the commitment by approving.

    Drives the REAL close() and the REAL continues_an_interruption() over real stage files; only the call result and
    the Office policy's reading of an answer are substituted, as in the tests above."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.events=[]
        self.config={'runtime_revision':'a'*40,'office_revision':'b'*40,'config_sha256':'c'*64}
        self.calls=[]
    def tearDown(self):self.temp.cleanup()
    def stage(self,nonce,completed=None):
        d=self.root/'calls'/nonce;d.mkdir(parents=True)
        (d/'workspace').mkdir();(d/'workspace'/'ACTUAL_REPORTS.json').write_text('{}')
        if completed is not None:(d/'result.json').write_text(json.dumps({'completed':completed,'process_group_removed':True}))
        self.calls.append({'nonce':nonce,'role':'final-review'})
    def scope(self):
        state={'control':'active'}
        def control(value,reason):self.events.append((value,reason));state['control']=value
        return SimpleNamespace(directory=self.root,control=control,inspect=lambda:{'control':state['control'],'calls':list(self.calls)})
    def close(self,nonce,approved=True):
        result={'answer':{'verdict':'approved' if approved else 'inconclusive'},'provider':{'thread_id':'fresh'}}
        with patch.object(final.host,'call_result',return_value=result),patch.object(final.host,'policy',return_value=SimpleNamespace(review=lambda _:approved)):
            return final.close(self.scope(),self.config,nonce)
    def test_an_approval_continuing_an_interrupted_review_of_its_own_run_is_withheld(self):
        self.stage('office-ap11-assessment-4-step-2',completed=False)     # the interrupted review
        self.stage('office-ap11-assessment-4-step-3')                     # the continued one
        closed=self.close('office-ap11-assessment-4-step-3')
        self.assertTrue(closed['approved']);self.assertFalse(closed['whole_goal_complete'])
        self.assertIn('closure_withheld',closed)
        self.assertEqual([e[0] for e in self.events],['paused']);self.assertFalse((self.root/'final.json').exists())
    def test_an_interruption_in_another_run_does_not_withhold_an_independent_approval(self):
        self.stage('office-ap11-assessment-4-step-2',completed=False)
        self.stage('office-ap11-assessment-4-step-3',completed=True)
        self.stage('office-ap11-assessment-5-step-2')                     # a separate run examining it
        closed=self.close('office-ap11-assessment-5-step-2')
        self.assertTrue(closed['whole_goal_complete']);self.assertEqual([e[0] for e in self.events],['stopped'])
        self.assertTrue((self.root/'final.json').is_file())
    def test_a_similar_prefix_is_not_the_same_run(self):
        self.stage('office-ap11-assessment-40-step-2',completed=False)
        self.stage('office-ap11-assessment-4-step-3')
        self.assertTrue(self.close('office-ap11-assessment-4-step-3')['whole_goal_complete'])
    def test_a_later_assessment_may_follow_a_withheld_approval_but_never_a_closing_one(self):
        from runtime import development_assessment as assessment
        self.stage('office-ap11-assessment-4-step-2',completed=False)
        self.stage('office-ap11-assessment-4-step-3',completed=True)
        (self.root/'calls/office-ap11-assessment-4-step-3/result.json').write_text(json.dumps({'completed':True,'answer':{'verdict':'approved'}}))
        policy=SimpleNamespace(review=lambda answer:(answer or {}).get('verdict')=='approved')
        with patch.object(assessment.host,'policy',return_value=policy):
            self.assertEqual(assessment.preserved_refusal(self.scope(),{})[0],'office-ap11-assessment-4-step-3')
        with tempfile.TemporaryDirectory() as other:
            root=Path(other);(root/'calls/office-ap11-assessment-5-step-2').mkdir(parents=True)
            (root/'calls/office-ap11-assessment-5-step-2/result.json').write_text(json.dumps({'completed':True,'answer':{'verdict':'approved'}}))
            plain=SimpleNamespace(directory=root,inspect=lambda:{'calls':[{'nonce':'office-ap11-assessment-5-step-2','role':'final-review'}]})
            with patch.object(assessment.host,'policy',return_value=policy):
                with self.assertRaisesRegex(ValueError,'was approved'):
                    assessment.preserved_refusal(plain,{})


if __name__=='__main__':unittest.main()
