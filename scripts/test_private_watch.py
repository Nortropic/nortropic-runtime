import asyncio
import dataclasses
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import os
import sys
import unittest
from unittest.mock import patch,AsyncMock
from runtime import private_stage as ps
from runtime import private_activity as pa
from temporalio.exceptions import CancelledError
from runtime.private_workflow import PrivateAssessment
from runtime.obligation import definition
from temporalio.client import ScheduleOverlapPolicy

class PrivateTests(unittest.TestCase):
    def test_fixed_native_budget_and_daily_schedule(self):
        s=definition({'config_sha256':'a'*64})
        self.assertTrue(s.state.paused)
        self.assertFalse(s.state.limited_actions)
        self.assertEqual(s.spec.time_zone_name,'Europe/Stockholm')
        self.assertEqual(s.spec.calendars[0].hour[0].start,9)
        self.assertEqual(s.policy.overlap,ScheduleOverlapPolicy.BUFFER_ONE)
        self.assertEqual(s.policy.catchup_window.total_seconds(),86400)
        self.assertEqual(s.action.execution_timeout.total_seconds(),1200)
        self.assertEqual(s.action.retry_policy.maximum_attempts,1)
        test=definition({'config_sha256':'x'},datetime.now(timezone.utc))
        self.assertTrue(test.state.limited_actions);self.assertEqual(test.state.remaining_actions,1)
        self.assertEqual(test.spec.time_zone_name,'UTC')

    def test_stage_order_no_publication_and_no_retry(self):
        class Info:
            run_id='00000000-0000-0000-0000-000000000001';workflow_id='synthetic';start_time=datetime.now(timezone.utc)
        calls=[]
        async def invoke(name,request,**kw):
            calls.append((name,request,kw))
            return {'completed':True,'needs_model':True} if request['role']=='intake' else {'completed':True}
        with patch('runtime.private_workflow.workflow.info',return_value=Info()),patch('runtime.private_workflow.workflow.execute_activity',side_effect=invoke):
            result=asyncio.run(PrivateAssessment().run({'obligation':'office-python-temporal','config_sha256':'x'}))
        self.assertEqual([x[1]['role'] for x in calls],['intake','analysis','review','report'])
        self.assertTrue(all(x[0]=='private_stage' and x[2]['retry_policy'].maximum_attempts==1 for x in calls))
        self.assertFalse(result['publication'])
        for x in calls:self.assertEqual(x[1]['run_id'],Info.run_id)

    def test_unchanged_or_intake_failure_never_calls_model(self):
        class Info:
            run_id='00000000-0000-0000-0000-000000000001';workflow_id='synthetic';start_time=datetime.now(timezone.utc)
        for result in ({'completed':True,'needs_model':False},{'completed':False}):
            calls=[]
            async def invoke(name,request,**kw):calls.append(request['role']);return result
            with patch('runtime.private_workflow.workflow.info',return_value=Info()),patch('runtime.private_workflow.workflow.execute_activity',side_effect=invoke):
                asyncio.run(PrivateAssessment().run({}))
            self.assertEqual(calls,['intake','report'])

    def test_budget_cannot_be_reset_and_unsafe_run_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d).resolve()/'rounds';home.mkdir();run='00000000-0000-0000-0000-000000000001'
            (home/run/'analysis').mkdir(parents=True)
            req=dict(config_sha256='a',obligation='office-python-temporal',run_id=run,role='analysis',seconds=480)
            with patch.object(ps,'HOME',home),patch.object(ps,'require_active_code',return_value={'config_sha256':'a'}),patch.object(ps,'module') as mod:
                with self.assertRaises(FileExistsError):ps.main(req)
                with self.assertRaises(ValueError):ps.main({**req,'run_id':'../../outside'})
                with self.assertRaises(ValueError):ps.main({**req,'seconds':960})
                mod.assert_not_called()

    def test_previous_requires_review_and_exact_intake_binding(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d).resolve();p=home/'one/report';p.mkdir(parents=True);data=home/'one/intake/data';data.mkdir(parents=True)
            packet=data/'packet.json';packet.write_text('{}')
            report=dict(reviewed=True,reported_at='2026-09-21T00:00:00Z',packet_sha256=ps.sha(packet))
            (p/'result.json').write_text(json.dumps(report))
            with patch.object(ps,'HOME',home):
                self.assertIsNotNone(ps.previous());packet.write_text('{"changed":true}')
                self.assertIsNone(ps.previous())

    def test_real_child_quota_failure_has_one_consumed_call(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d).resolve()/'analysis';stage.mkdir();work=stage/'work';work.mkdir()
            code="import sys,json;sys.stdin.read();print(json.dumps({'type':'thread.started','thread_id':'synthetic'}));print(json.dumps({'type':'turn.failed','error':{'message':'synthetic quota unavailable'}}))"
            with patch.object(ps,'command',return_value=[sys.executable,'-c',code,'-']),patch.object(ps,'require_workspace_instructions'):
                result=ps.model(stage,work,'synthetic',{},2,os.getppid())
                self.assertFalse(result['completed']);self.assertTrue(result['process_group_removed'])
                self.assertEqual(json.loads((stage/'budget.json').read_text())['model_calls'],1)
                with self.assertRaises(FileExistsError):ps.model(stage,work,'synthetic',{},2,os.getppid())

    def test_parent_loss_cleans_real_synthetic_child(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d).resolve()/'analysis';stage.mkdir();work=stage/'work';work.mkdir()
            code="import sys,time;sys.stdin.read();time.sleep(20)"
            with patch.object(ps,'command',return_value=[sys.executable,'-c',code,'-']),patch.object(ps,'require_workspace_instructions'):
                result=ps.model(stage,work,'synthetic',{},2,-1)
            self.assertFalse(result['completed']);self.assertTrue(result['process_group_removed'])
            self.assertLess(result['elapsed_seconds'],5)

    def test_activity_cancel_closes_real_stage_before_raising(self):
        import subprocess
        real_popen=subprocess.Popen
        children=[]
        def launch(argv,**kw):
            if 'runtime.private_stage' not in argv:return real_popen(argv,**kw)
            proc=real_popen([sys.executable,'-c','import time;time.sleep(20)'],**kw);children.append(proc);return proc
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            with patch.object(pa,'ROOT',root),patch.object(pa,'require_active_code'),patch.object(pa,'check_private_processes'),patch.object(pa,'cleanup_private_run'),patch.object(pa,'private_size',return_value=0),patch.object(pa.activity,'heartbeat'),patch.object(pa.activity,'is_cancelled',return_value=True),patch.object(pa.subprocess,'Popen',side_effect=launch):
                with self.assertRaises(CancelledError):pa.private_stage({'run_id':'synthetic','role':'intake','seconds':90})
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())

    def test_cleanup_real_completed_launch_uses_empty_identity_contract(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();home=root/'rounds';run='00000000-0000-0000-0000-000000000001'
            stage=home/run/'analysis';stage.mkdir(parents=True)
            proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.1)'],start_new_session=True)
            identity=ps.process_identity(proc.pid);proc.wait(timeout=2)
            (stage/'launch.json').write_text(json.dumps({'provider_pid':proc.pid,'provider_identity':identity}))
            self.assertFalse(ps.process_identity(proc.pid))
            with patch.object(ps,'ROOT',root),patch.object(ps,'HOME',home):
                result=ps.cleanup_private_run(run)
            self.assertTrue(result['process_groups_removed'])
            # Empty observed launch identity must not equal an absent PID into life.
            (stage/'launch.json').write_text(json.dumps({'provider_pid':proc.pid,'provider_identity':''}))
            with patch.object(ps,'ROOT',root),patch.object(ps,'HOME',home):ps.check_private_processes()

    def test_orphan_identity_requires_diagnosis(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d).resolve();p=home/'one/analysis';p.mkdir(parents=True)
            (p/'launch.json').write_text(json.dumps({'provider_pid':765432,'provider_identity':'original'}))
            with patch.object(ps,'HOME',home),patch.object(ps,'process_identity',return_value='original'):
                with self.assertRaisesRegex(ValueError,'Unfinished private'):ps.check_private_processes()
            with patch.object(ps,'HOME',home),patch.object(ps,'process_identity',return_value=None),patch.object(ps.os,'killpg',side_effect=ProcessLookupError):ps.check_private_processes()

if __name__=='__main__':unittest.main()
