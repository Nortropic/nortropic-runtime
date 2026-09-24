import asyncio
import dataclasses
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
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
        self.assertEqual(s.policy.catchup_window.total_seconds(),22*3600)
        self.assertEqual(s.action.execution_timeout.total_seconds(),1200)
        self.assertEqual(s.action.retry_policy.maximum_attempts,1)
        test=definition({'config_sha256':'x'},datetime.now(timezone.utc))
        self.assertTrue(test.state.limited_actions);self.assertEqual(test.state.remaining_actions,1)
        self.assertEqual(test.spec.time_zone_name,'UTC')

    def test_catchup_window_below_closest_stockholm_daily_occurrences(self):
        # Real timezone transition: two consecutive09 starts are only23h apart.
        zone=ZoneInfo('Europe/Stockholm')
        before=datetime(2026,3,28,9,tzinfo=zone).astimezone(timezone.utc)
        after=datetime(2026,3,29,9,tzinfo=zone).astimezone(timezone.utc)
        window=definition({'config_sha256':'fixture'}).policy.catchup_window
        self.assertEqual(after-before,timedelta(hours=23))
        self.assertLess(window,after-before)
        before27=datetime(2027,3,27,9,tzinfo=zone).astimezone(timezone.utc)
        after27=datetime(2027,3,28,9,tzinfo=zone).astimezone(timezone.utc)
        returned=datetime(2027,3,28,9,30,tzinfo=zone).astimezone(timezone.utc)
        self.assertEqual(sum(returned-x<=timedelta(hours=24) for x in (before27,after27)),2)
        self.assertEqual(sum(returned-x<=window for x in (before27,after27)),1)
        self.assertTrue((after27+window-timedelta(seconds=1))-after27<window)
        self.assertFalse((after27+window+timedelta(seconds=1))-after27<=window)
        # Compare all adjacent days across both transitions in an actual year.
        starts=[(datetime(2026,1,1,9,tzinfo=zone)+timedelta(days=n)).astimezone(timezone.utc) for n in range(366)]
        self.assertTrue(all(b-a>window for a,b in zip(starts,starts[1:])))
        for start in starts[1:]:
            at=start+timedelta(seconds=1)
            self.assertLessEqual(sum(timedelta(0)<=at-x<=window for x in starts),1)

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

    def test_capture_does_not_limit_native_provider_state_files(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d).resolve()/'analysis';stage.mkdir();work=stage/'work';work.mkdir()
            state=stage/'synthetic-provider-state'
            code=("import sys,json,pathlib;sys.stdin.read();"
                  "pathlib.Path("+repr(str(state))+").write_bytes(b'x'*(2*1024*1024));"
                  "print(json.dumps({'type':'thread.started','thread_id':'synthetic'}));"
                  "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{}'}}));"
                  "print(json.dumps({'type':'turn.completed','usage':None}))")
            with patch.object(ps,'command',return_value=[sys.executable,'-c',code,'-']),patch.object(ps,'require_workspace_instructions'):
                result=ps.model(stage,work,'synthetic',{},3,os.getppid())
            self.assertTrue(result['completed']);self.assertEqual(result['exit_code'],0)
            self.assertEqual(state.stat().st_size,2*1024*1024)
            self.assertEqual(result['answer'],{})

    def test_each_capture_is_bounded_and_flooding_process_is_cleaned(self):
        for fd in (1,2):
            with self.subTest(fd=fd),tempfile.TemporaryDirectory() as d:
                stage=Path(d).resolve()/'analysis';stage.mkdir();work=stage/'work';work.mkdir()
                code="import os,sys;sys.stdin.read();\nwhile True:os.write("+str(fd)+",b'x'*65536)"
                with patch.object(ps,'command',return_value=[sys.executable,'-c',code,'-']),patch.object(ps,'require_workspace_instructions'),patch.object(ps,'LOG_BYTES',32768):
                    result=ps.model(stage,work,'synthetic',{},3,os.getppid())
                self.assertFalse(result['completed']);self.assertTrue(result['process_group_removed'])
                self.assertIsInstance(result['exit_code'],int)
                self.assertLessEqual((stage/'events.jsonl').stat().st_size,16384)
                self.assertLessEqual((stage/'stderr.log').stat().st_size,16384)
                self.assertLess(result['elapsed_seconds'],5)

    def test_early_signal_exit_is_preserved_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d).resolve()/'analysis';stage.mkdir();work=stage/'work';work.mkdir()
            code="import os,signal;os.kill(os.getpid(),signal.SIGTERM)"
            with patch.object(ps,'command',return_value=[sys.executable,'-c',code,'-']),patch.object(ps,'require_workspace_instructions'):
                result=ps.model(stage,work,'synthetic',{},3,os.getppid())
            self.assertEqual(result['exit_code'],-15);self.assertFalse(result['completed'])
            self.assertTrue(result['process_group_removed'])
            self.assertEqual(json.loads((stage/'budget.json').read_text())['model_calls'],1)

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


# The real stage guardian, model() in its own process as private_activity starts it; only the provider command, the
# instruction check and the storage sample are substituted. The provider is NATIVE (a shell keeping one child in its
# group), as the real Codex binary is: a venv Python would re-exec itself on macOS and change its ps identity.
GUARDIAN = r"""
import json, os, sys
from pathlib import Path
code, stage, work, pids, provider, seconds = sys.argv[1:7]; sys.path.insert(0, code)
from unittest.mock import patch
from runtime import private_stage as ps
argv = ['/bin/sh', '-c', provider, 'provider', pids, '-']
with patch.object(ps, 'command', return_value=argv), patch.object(ps, 'require_workspace_instructions'), \
     patch.object(ps, 'private_size', return_value=0):
    print(json.dumps(ps.model(Path(stage), Path(work), 'synthetic', {}, int(seconds), os.getppid())))
"""
SILENT = 'sleep 60 & printf \'{"provider": %d, "child": %d}\' $$ $! > "$1"; wait'
SPOKE_THEN_SILENT = ('printf \'{"type":"thread.started","thread_id":"t"}\\n{"type":"item.completed","item":{"type":"agent_message",'
                     '"text":"{}"}}\\n\'; ' + SILENT)
# A provider that answers: its exact events are written by the test and replayed by the shell.
ANSWER_EVENTS = [{'type': 'thread.started', 'thread_id': 't'},
                 {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'decision': 'hold'})}},
                 {'type': 'turn.completed', 'usage': {}}]


class StageSignalTests(unittest.TestCase):
    """D031: a termination signal to the waiting stage guardian ends its call, within the activity's own stop."""

    def run_guardian(self, provider, seconds=30):
        import subprocess
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve(); self.stage = root / 'analysis'; self.stage.mkdir(); work = root / 'work'; work.mkdir()
        self.pids = root / 'pids.json'
        code = str(Path(ps.__file__).resolve().parents[1])
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1'); environment.pop('NR_CONFIG_SHA256', None)
        self.proc = subprocess.Popen([sys.executable, '-B', '-c', GUARDIAN, code, str(self.stage), str(work), str(self.pids),
                                      provider, str(seconds)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, start_new_session=True)
        self.addCleanup(lambda: self.proc.poll() is None and self.proc.kill())
        import time
        end = time.monotonic() + 20
        while not ((self.stage / 'launch.json').exists() and self.pids.exists()) and time.monotonic() < end:
            time.sleep(.05)
        return json.loads(self.pids.read_text())

    def gone(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    def stop_as_the_activity_does(self):
        """private_activity's finally: SIGTERM, then at most 6 s for the guardian to end by itself."""
        import signal, subprocess, time
        time.sleep(.3); sent = time.monotonic(); self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            self.fail('the guardian did not end within the activity grace: the signal was swallowed')
        return time.monotonic() - sent

    def test_a_termination_signal_ends_the_waiting_call_within_the_activitys_grace(self):
        pids = self.run_guardian(SILENT)
        elapsed = self.stop_as_the_activity_does()
        self.assertLess(elapsed, 3, 'the guardian ends its call itself, long before the 6 s grace')
        self.assertEqual(self.proc.returncode, 0)
        result = json.loads((self.stage / 'result.json').read_text())
        self.assertEqual((result['completed'], result['reason'], result['process_group_removed']), (False, 'InterruptedError', True))
        self.assertTrue(self.gone(pids['provider']) and self.gone(pids['child']), 'the provider and its child are removed')
        self.assertEqual(json.loads((self.stage / 'budget.json').read_text())['model_calls'], 1, 'and the call stays consumed')

    def test_an_interrupted_call_is_never_a_completed_answer(self):
        """The provider had already spoken; the interruption still leaves no valid terminal and no completed stage."""
        self.run_guardian(SPOKE_THEN_SILENT)
        self.stop_as_the_activity_does()
        result = json.loads((self.stage / 'result.json').read_text())
        self.assertFalse(result['completed']); self.assertFalse(result['provider']['valid_terminal'])
        self.assertEqual(result['reason'], 'InterruptedError')

    def test_the_stage_deadline_still_ends_a_silent_call(self):
        import time
        pids = self.run_guardian(SILENT, seconds=2); start = time.monotonic()
        self.proc.wait(timeout=10)
        self.assertLess(time.monotonic() - start, 6)
        result = json.loads((self.stage / 'result.json').read_text())
        self.assertEqual((result['completed'], result['reason'], result['process_group_removed']), (False, 'TimeoutError', True))
        self.assertTrue(self.gone(pids['provider']) and self.gone(pids['child']))

    def test_a_normal_call_still_completes_with_its_answer(self):
        events = Path(tempfile.mkdtemp()) / 'events.jsonl'; self.addCleanup(lambda: events.unlink(missing_ok=True))
        events.write_text(''.join(json.dumps(e) + '\n' for e in ANSWER_EVENTS))
        self.run_guardian('printf \'{"provider": %%d, "child": 0}\' $$ > "$1"; cat \'%s\'' % events)
        self.proc.wait(timeout=10)
        result = json.loads((self.stage / 'result.json').read_text())
        self.assertTrue(result['completed'], result); self.assertEqual(result['answer'], {'decision': 'hold'})
        self.assertTrue(result['provider']['valid_terminal']); self.assertTrue(result['process_group_removed'])

if __name__=='__main__':unittest.main()
