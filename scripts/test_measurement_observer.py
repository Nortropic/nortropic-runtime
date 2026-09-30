"""Synthetic protocol cases; same UID fixtures do not establish installed UID isolation."""
import hashlib
import unittest
from runtime import measurement_observer as o


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'name':'test_x.T.test_task_boundary','file':'tests/test_x.py'},
                   {'name':'test_x.T.test_later_failure','file':'tests/test_x.py'}]
        self.events=[];self.now=10.;self.r=o.Receiver(self.rows,self.events.append,clock=lambda:self.now)
    def event(self,kind,**fields):
        self.now+=.25;self.r.feed({'schema':o.EVENT_SCHEMA,'event':kind,**fields})
    def terminal(self):
        self.event('terminal',count=2,successful=True,manifest_sha256=hashlib.sha256(o.canonical(o.manifest(self.rows))).hexdigest())
    def success(self):
        for i in (1,2):self.event('start',id=i);self.event('stop',id=i,status='success')
        self.terminal()
    def test_masking_substring_does_not_change_numeric_case_identity(self):
        self.success();r=self.r.finish(0,cleaned=True)
        self.assertTrue(r['passed']);self.assertEqual([c['name'] for c in r['cases']],[r['name'] for r in self.rows])
        self.assertEqual([c['seconds'] for c in r['cases']],[.25,.25])
    def test_invalid_event_preserves_later_failure_but_never_passes(self):
        self.r.feed({'schema':o.EVENT_SCHEMA,'event':'start','id':'masked-not-an-id'})
        self.event('start',id=1);self.event('stop',id=1,status='success')
        self.event('start',id=2);self.event('stop',id=2,status='failure');self.terminal()
        r=self.r.finish(1,cleaned=True);self.assertFalse(r['complete']);self.assertEqual(r['cases'][1]['status'],'failure')
    def test_missing_interval_and_class_fixture_error_remain_unknown(self):
        self.event('fixture-error',before_id=1,status='error')
        self.event('start',id=2);self.event('stop',id=2,status='success');self.terminal()
        r=self.r.finish(1,cleaned=True);self.assertFalse(r['passed']);self.assertEqual(r['cases'][0]['seconds'],None)
        self.assertEqual(r['cases'][0]['status'],'unknown');self.assertEqual(len(r['fixture_errors']),1)
    def test_duplicate_terminal_extra_case_and_false_cleanup_refuse(self):
        self.success();self.assertFalse(self.r.finish(0,cleaned=False)['passed'])
        self.terminal();self.assertFalse(self.r.finish(0,cleaned=True)['complete'])
        self.event('start',id=1);self.assertTrue(self.r.invalid)
    def test_child_duration_field_cannot_replace_parent_clock(self):
        self.event('start',id=1)
        self.r.feed({'schema':o.EVENT_SCHEMA,'event':'stop','id':1,'status':'success','seconds':0})
        self.event('stop',id=1,status='failure')
        self.assertEqual(self.r.stops[1]['seconds'],.25);self.assertTrue(self.r.invalid)
    def test_nonfinite_clock_and_out_of_order_events_never_complete(self):
        self.event('start',id=2);self.now=float('nan');self.r.feed({'schema':o.EVENT_SCHEMA,'event':'stop','id':2,'status':'success'})
        self.assertTrue(self.r.invalid);self.assertIsNone(self.r.stops[2]['seconds'])


class PipeTests(unittest.TestCase):
    def test_fragmented_protocol_and_large_stderr_do_not_deadlock_or_move_parent_clock(self):
        import json,sys,tempfile
        from pathlib import Path
        rows=[{'name':'test_x.T.test_task_one','file':'tests/test_x.py'}]
        digest=hashlib.sha256(o.canonical(o.manifest(rows))).hexdigest()
        events=[{'schema':o.EVENT_SCHEMA,'event':'start','id':1},
                {'schema':o.EVENT_SCHEMA,'event':'stop','id':1,'status':'failure'},
                {'schema':o.EVENT_SCHEMA,'event':'terminal','count':1,'successful':False,'manifest_sha256':digest}]
        code='import os,time,sys,json\ntime.monotonic=lambda:0\n'
        code+='events='+repr(events)+'\n'
        code+='for e in events:\n raw=(json.dumps(e)+"\\n").encode();os.write(1,raw[:9]);time.sleep(.04);os.write(1,raw[9:]);os.write(2,b"x"*70000)\n'
        code+='sys.exit(1)\n'
        with tempfile.TemporaryDirectory() as d:
            result=o.receive_process([sys.executable,'-B','-c',code],d,None,rows,Path(d).resolve()/'primary',5,
                 cleanup=lambda p:None,verify_cleanup=lambda p:p.poll() is not None)
            self.assertTrue(result['complete']);self.assertFalse(result['passed'])
            self.assertGreater(result['cases'][0]['seconds'],.03)
            self.assertEqual(result['cases'][0]['status'],'failure')
            self.assertEqual((Path(d)/'primary/suite.log').stat().st_size,210000)

    def test_timeout_requests_fixed_cleanup_and_preserves_unfinished_case(self):
        import json,os,signal,sys,tempfile
        from pathlib import Path
        rows=[{'name':'test_x.T.test_one','file':'tests/test_x.py'}]
        event={'schema':o.EVENT_SCHEMA,'event':'start','id':1}
        code='import os,time\nos.write(1,'+repr((json.dumps(event)+'\n').encode())+')\ntime.sleep(30)'
        called=[]
        def cleanup(p):
            called.append(p.pid)
            # Same-UID synthetic driver only. Production cannot use this method.
            os.killpg(p.pid,signal.SIGKILL)
        with tempfile.TemporaryDirectory() as d:
            result=o.receive_process([sys.executable,'-B','-c',code],d,None,rows,Path(d).resolve()/'primary',.2,
                 cleanup=cleanup,verify_cleanup=lambda p:p.poll() is not None)
            self.assertTrue(called);self.assertTrue(result['timed_out']);self.assertFalse(result['passed'])
            self.assertEqual(result['cases'][0]['status'],'unknown');self.assertIsNone(result['cases'][0]['seconds'])


class LateObservationTests(unittest.TestCase):
    def produce(self,root):
        import json,sys
        rows=[{'name':'test_x.T.test_one','file':'tests/test_x.py'}]
        events=[{'schema':o.EVENT_SCHEMA,'event':'start','id':1},
                {'schema':o.EVENT_SCHEMA,'event':'stop','id':1,'status':'failure'},
                {'schema':o.EVENT_SCHEMA,'event':'terminal','count':1,'successful':False,
                 'manifest_sha256':hashlib.sha256(o.canonical(o.manifest(rows))).hexdigest()}]
        raw=''.join(json.dumps(e)+'\n' for e in events).encode()
        code='import os,sys;os.write(1,'+repr(raw)+');sys.exit(1)'
        return o.receive_process([sys.executable,'-B','-c',code],root,None,rows,root/'run',5,
                                 cleanup=lambda p:None,verify_cleanup=lambda p:p.poll() is not None)

    def assert_observation(self,report):
        self.assertEqual(report['returncode'],1)
        self.assertEqual([(r['order'],r['name'],r['status']) for r in report['cases']],[(1,'test_x.T.test_one','failure')])
        self.assertIsInstance(report['cases'][0]['seconds'],float)

    def test_late_log_read_error_preserves_real_received_cases(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();original=Path.read_bytes
            def read(path):
                if path==root/'run/suite.log':raise OSError('synthetic late log read loss')
                return original(path)
            with patch.object(Path,'read_bytes',read),self.assertRaises(o.ObservationInterrupted) as caught:
                self.produce(root)
            self.assert_observation(caught.exception.observation)
            self.assertTrue((root/'run/events.jsonl').exists())

    def test_final_receipt_failure_preserves_actual_report_and_primary_suite(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();report=self.produce(root)
            report.update(candidate='a'*40,test_count=1,last_line='FAILED')
            original=o.write_owner
            def write(path,value,**kwargs):
                if path.name=='klar.json':raise OSError('synthetic final receipt loss')
                return original(path,value,**kwargs)
            with patch.object(o,'write_owner',side_effect=write),self.assertRaises(o.ObservationInterrupted) as caught:
                o.save_suite(root,report,'fixture')
            self.assert_observation(caught.exception.observation)
            self.assertEqual(json.loads((root/'suite.json').read_text()),caught.exception.observation)
            self.assertFalse((root/'klar.json').exists())


class OwnerPathTests(unittest.TestCase):
    def test_preparation_stream_failures_refuse_before_transport_start(self):
        import subprocess,tempfile
        from pathlib import Path
        from unittest.mock import patch
        original=o.owner_node
        for name in ('preparation.log','protocol.jsonl'):
            for failure in ('open','acl'):
                with self.subTest(name=name,failure=failure),tempfile.TemporaryDirectory() as temp:
                    root=Path(temp).resolve();actual_open=o.os.open
                    def open_file(path,*args,**kwargs):
                        if Path(path).name==name and failure=='open':raise OSError('synthetic opening failure')
                        return actual_open(path,*args,**kwargs)
                    def check(path,*args,**kwargs):
                        if Path(path).name==name and failure=='acl':
                            subprocess.run(['/bin/chmod','+a','user:_spotlight allow read',str(path)],check=True)
                        return original(path,*args,**kwargs)
                    # ACL observation uses subprocess.run/Popen too; only the
                    # transport is replaced, while real ls/chmod still run.
                    def spawn(argv,*args,**kwargs):
                        if argv==['never-run']:raise AssertionError('transport started before stream validation')
                        return real_popen(argv,*args,**kwargs)
                    real_popen=subprocess.Popen
                    with patch.object(o.os,'open',side_effect=open_file),patch.object(o,'owner_node',side_effect=check), \
                         patch.object(o.subprocess,'Popen',side_effect=spawn),self.assertRaises((OSError,o.Refused)):
                        o.capture_stage(['never-run'],root/'run',5,lambda p:None,lambda p:True)
                    for stream in (root/'run').glob('*'):
                        self.assertEqual(stream.read_bytes(),b'')

    def test_preparation_keeps_verified_streams_and_observes_cleanup(self):
        import sys,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();cleaned=[]
            code='import sys;print('+repr('{"probe":true}')+');print('+repr('{"inventory":[]}')+');sys.stderr.write("synthetic preparation")'
            result=o.capture_stage([sys.executable,'-B','-c',code],root/'run',5,
                                   lambda p:cleaned.append(p.pid),lambda p:p.pid in cleaned and p.poll()==0)
            self.assertEqual(result,[{'probe':True},{'inventory':[]}])
            self.assertEqual((root/'run/preparation.log').read_bytes(),b'synthetic preparation')
            self.assertEqual((root/'run/protocol.jsonl').read_bytes(),b'{"probe":true}\n{"inventory":[]}\n')
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in (root/'run').iterdir()))

    def test_shared_host_tool_read_acl_uses_shared_contract(self):
        import os,pwd,subprocess,tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();tool=root/'fixed-tool';tool.write_bytes(b'synthetic');tool.chmod(0o444)
            subprocess.run(['/bin/chmod','+a','user:_spotlight allow read',str(tool)],check=True)
            plats=SimpleNamespace(runtime=root,prov='_nortropicprov')
            profile={'lankar':[],'python':str(tool)}
            # The shared OS temp parent is a disposable fixture, not a trusted
            # installed tool root. ACL traversal itself remains real.
            with patch.object(o,'test_can_write',return_value=False):
                self.assertEqual(o.protected_tools(plats,profile),sorted(set(os.getgrouplist('_nortropicprov',pwd.getpwnam('_nortropicprov').pw_gid))))
                subprocess.run(['/bin/chmod','+a','user:_spotlight allow write',str(tool)],check=True)
                with self.assertRaises(o.Refused):o.protected_tools(plats,profile)

    def test_private_and_deliberately_shared_paths_have_different_acl_contracts(self):
        import os,subprocess,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp).resolve()/'fixture';path.write_bytes(b'synthetic');path.chmod(0o600)
            subprocess.run(['/bin/chmod','+a','user:_spotlight allow read',str(path)],check=True)
            o.owner_node(path,os.getuid())
            with self.assertRaises(o.Refused):o.owner_node(path,os.getuid(),private=True)

    def test_inherited_read_acl_is_refused_before_writing_private_bytes(self):
        import subprocess,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            subprocess.run(['/bin/chmod','+a','user:_spotlight allow read,file_inherit',str(root)],check=True)
            target=root/'private.json'
            with self.assertRaises(o.Refused):o.write_owner(target,{'synthetic':'must not be written'})
            self.assertEqual(target.read_bytes(),b'')

    def test_raw_stream_boundary_refuses_inherited_read_acl_before_child_start(self):
        import subprocess,tempfile
        from pathlib import Path
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            subprocess.run(['/bin/chmod','+a','user:_spotlight allow read,file_inherit,directory_inherit',str(root)],check=True)
            child=Mock()
            with self.assertRaises(o.Refused):o.receive_process(['never-run'],root,None,[],root/'run',5,lambda p:None,lambda p:True,popen=child)
            child.assert_not_called()

    def test_regular_owner_path_rejects_writable_mode_and_link(self):
        import os,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'record';path.write_text('fixture');path.chmod(0o600)
            self.assertEqual(o.owner_node(path,os.getuid()).st_uid,os.getuid())
            path.chmod(0o666)
            with self.assertRaises(o.Refused):o.owner_node(path,os.getuid())
            link=Path(d)/'link';link.symlink_to(path)
            with self.assertRaises(o.Refused):o.owner_node(link,os.getuid())
    def test_own_real_process_is_visible_without_command_arguments(self):
        import os
        rows=o.process_table(os.getuid());self.assertIn(os.getpid(),rows)
        self.assertEqual(set(rows[os.getpid()]),{'pid','ppid','pgid','uid','started'})


class RunnerSemanticsTests(unittest.TestCase):
    def test_real_runner_preserves_module_class_state_and_numeric_ids(self):
        import json,subprocess,sys,tempfile
        from pathlib import Path
        from scripts.matning_provanvandare import OWNER_EVENT_RUNNER
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();(root/'tests').mkdir()
            (root/'tests/test_fixture.py').write_text('import unittest\nclass T(unittest.TestCase):\n @classmethod\n def setUpClass(cls):cls.value=0\n def test_a_task_boundary(self):type(self).value+=1\n def test_b(self):self.assertEqual(type(self).value,1)\n')
            plan=root/'plan.json';plan.write_text(json.dumps({'names':[]}))
            argv=[sys.executable,'-B','-c',OWNER_EVENT_RUNNER,str(root),'tests','inventory',str(plan)]
            inventory=subprocess.run(argv,cwd=root,capture_output=True)
            self.assertEqual(inventory.returncode,0,inventory.stderr)
            rows=json.loads(inventory.stdout)['rows'];plan.write_text(json.dumps({'names':[],'manifest':rows}));argv[-2]='run'
            primary=root/'primary'
            report=o.receive_process(argv,root,None,[{'name':r['name'],'file':r['file']} for r in rows],primary,10,
                                     cleanup=lambda p:None,verify_cleanup=lambda p:p.poll() is not None)
            self.assertTrue(report['passed'],(primary/'suite.log').read_text())
            self.assertEqual([r['order'] for r in report['cases']],[1,2]);self.assertTrue(report['shared_interpreter_state'])
    def test_class_fixture_failure_keeps_later_case_observation(self):
        import json,subprocess,sys,tempfile
        from pathlib import Path
        from scripts.matning_provanvandare import OWNER_EVENT_RUNNER
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();(root/'tests').mkdir()
            (root/'tests/test_fixture.py').write_text('import unittest\nclass A(unittest.TestCase):\n @classmethod\n def setUpClass(cls):raise ValueError("synthetic fixture failure")\n def test_a(self):pass\nclass B(unittest.TestCase):\n def test_later(self):self.fail("synthetic later failure")\n')
            plan=root/'plan.json';plan.write_text(json.dumps({'names':[]}))
            argv=[sys.executable,'-B','-c',OWNER_EVENT_RUNNER,str(root),'tests','inventory',str(plan)]
            inventory=subprocess.run(argv,cwd=root,capture_output=True);rows=json.loads(inventory.stdout)['rows']
            plan.write_text(json.dumps({'names':[],'manifest':rows}));argv[-2]='run'
            report=o.receive_process(argv,root,None,[{'name':r['name'],'file':r['file']} for r in rows],root/'primary',10,
                                     cleanup=lambda p:None,verify_cleanup=lambda p:p.poll() is not None)
            self.assertFalse(report['passed']);self.assertEqual(report['cases'][0]['status'],'unknown')
            self.assertEqual(report['cases'][1]['status'],'failure');self.assertEqual(len(report['fixture_errors']),1)


class SnapshotTests(unittest.TestCase):
    def test_bundle_materializes_owner_sources_and_only_named_disposable_link(self):
        import json,os,subprocess,tempfile,types
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();original=root/'original'
            def git(cwd,*args):return subprocess.check_output(['git','--no-replace-objects','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-C',str(cwd),*args],stderr=subprocess.DEVNULL).decode().strip()
            git(root,'init','-q',str(original));(original/'test.py').write_text('# fixture\n');git(original,'add','.');git(original,'commit','-qm','fixture')
            inbox=root/'shared/in';target=inbox/'fixture';target.mkdir(parents=True)
            bundle=target/'kandidat.bundle';git(original,'bundle','create',str(bundle),'HEAD')
            request={'candidate':git(original,'rev-parse','HEAD'),'tree':git(original,'rev-parse','HEAD^{tree}'),'repo':'kontoret'}
            (target/'begaran.json').write_text(json.dumps(request))
            plats=types.SimpleNamespace(inkorg=inbox,arbete=root/'test-work',runtime=root/'host')
            source,files=o.materialize_snapshot(plats,'fixture',request,bundle)
            self.assertEqual(files,{'test.py':hashlib.sha256(b'# fixture\n').hexdigest()})
            self.assertTrue((source/'.scratch').is_symlink());self.assertEqual((source/'.scratch').readlink(),plats.arbete/'fixture/scratch')
            self.assertEqual((source/'test.py').stat().st_mode&0o022,0)
            with self.assertRaises(o.Refused):o.materialize_snapshot(plats,'fixture',request,bundle)


class FailureBoundaryTests(unittest.TestCase):
    def test_lost_cleanup_preserves_later_failure_and_never_passes(self):
        import json,sys,tempfile
        from pathlib import Path
        rows=[{'name':'test_x.T.test_failed','file':'tests/test_x.py'}]
        digest=hashlib.sha256(o.canonical(o.manifest(rows))).hexdigest()
        events=[{'schema':o.EVENT_SCHEMA,'event':'start','id':1},
                {'schema':o.EVENT_SCHEMA,'event':'stop','id':1,'status':'failure'},
                {'schema':o.EVENT_SCHEMA,'event':'terminal','count':1,'successful':False,'manifest_sha256':digest}]
        def lost(child):raise OSError('synthetic lost fixed helper')
        with tempfile.TemporaryDirectory() as d:
            code='import sys\nsys.stdout.write('+repr(''.join(json.dumps(e)+'\n' for e in events))+')'
            report=o.receive_process([sys.executable,'-B','-c',code],d,None,rows,Path(d).resolve()/'primary',5,
                                     cleanup=lost,verify_cleanup=lambda p:False)
            self.assertFalse(report['complete']);self.assertFalse(report['cleanup_verified'])
            self.assertEqual(report['cases'][0]['status'],'failure')

    def test_fixed_stop_uses_owner_bound_identity_and_refuses_uid_or_reused_pid(self):
        import os,types
        from unittest.mock import patch
        from scripts import matning_provanvandare as fast
        candidate='a'*40;run='b'*32;pid=98765
        row={'pid':pid,'ppid':1,'pgid':pid,'uid':os.getuid(),'started':'Thu Oct  1 00:00:00 2026'}
        stop={'schema':'nortropic-measurement-stop/1','id':'fixture','run':run,'candidate':candidate,'processes':[row]}
        def document(plats,ident,name):return {'run':run} if name=='observation.json' else stop
        # No actual process is signaled: emulate a reused PID with another start.
        response=types.SimpleNamespace(returncode=0,stdout=f'{pid} 1 {pid} {os.getuid()} Thu Oct  1 00:00:01 2026\n'.encode())
        with patch.object(fast,'las_begaran',return_value=({'candidate':candidate},None)), \
             patch.object(fast,'owner_document',side_effect=document), \
             patch.object(fast.subprocess,'run',return_value=response),patch.object(fast.os,'kill') as kill, \
             patch.object(fast.time,'sleep'):
            self.assertEqual(fast.observed_stop(None,'fixture'),0);kill.assert_not_called()
            row['uid']=os.getuid()+1
            with self.assertRaises(fast.Vagrar):fast.observed_stop(None,'fixture')
            kill.assert_not_called()

    def test_fixed_source_refuses_group_writable_request_bytes(self):
        import os,tempfile,pwd,json,subprocess
        from pathlib import Path
        from scripts import matning_provanvandare as fast
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();inbox=root/'shared/in';base=inbox/'fixture';base.mkdir(parents=True)
            original=root/'repo';original.mkdir()
            for args in (['init','-q','-b','main'],['commit','-q','--allow-empty','-m','fixture']):
                subprocess.run(['git','-C',str(original),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],check=True)
            candidate=subprocess.check_output(['git','-C',str(original),'rev-parse','HEAD']).decode().strip()
            tree=subprocess.check_output(['git','-C',str(original),'rev-parse','HEAD^{tree}']).decode().strip()
            subprocess.run(['git','-C',str(original),'bundle','create',str(base/'kandidat.bundle'),'--branches'],check=True)
            request={'schema':fast.BEGARAN,'id':'fixture','repo':'runtime','candidate':candidate,'tree':tree,
                     'ref':'refs/heads/main','expected_test_count':1,'requested_at':'2026-10-01T00:00:00+00:00'}
            path=base/'begaran.json';path.write_text(json.dumps(request));path.chmod(0o664)
            me=pwd.getpwuid(os.getuid()).pw_name
            plats=fast.Plats(agare=me,agarhem=root/'owner',prov=me,provhem=root/'prov',inkorg=inbox)
            with self.assertRaises(fast.Vagrar):fast.las_begaran(plats,'fixture')

    def test_actual_same_uid_is_refused_before_privileged_transport(self):
        import os,pwd,types
        from unittest.mock import patch
        me=pwd.getpwuid(os.getuid()).pw_name
        with patch.object(o.subprocess,'run') as run:
            with self.assertRaisesRegex(o.Refused,'Distinct actual owner/test'):
                o.measure(types.SimpleNamespace(prov=me,agare=me),'fixture',{},None,'b'*32,'/not-used')
            run.assert_not_called()


class ToolModeTests(unittest.TestCase):
    def test_actual_uid_and_groups_determine_mode_permission(self):
        from types import SimpleNamespace as S
        self.assertFalse(o.test_can_write(S(st_uid=501,st_gid=80,st_mode=0o775),502,{20,502}))
        self.assertTrue(o.test_can_write(S(st_uid=501,st_gid=20,st_mode=0o775),502,{20,502}))
        self.assertTrue(o.test_can_write(S(st_uid=501,st_gid=80,st_mode=0o777),502,{502}))
        self.assertTrue(o.test_can_write(S(st_uid=502,st_gid=80,st_mode=0o744),502,{502}))
        self.assertFalse(o.test_can_write(S(st_uid=502,st_gid=502,st_mode=0o044),502,{502}))

    def test_nonroot_fixed_file_is_refused_before_reading_or_launching_tools(self):
        import os,tempfile,types,pwd
        from pathlib import Path
        from unittest.mock import patch
        uid=os.getuid()
        def account(name):return types.SimpleNamespace(pw_uid=uid if name=='fixture-owner' else uid+1)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'fixed';path.write_text('synthetic untrusted program')
            with patch.object(pwd,'getpwnam',side_effect=account),patch.object(o.subprocess,'run') as run:
                with self.assertRaisesRegex(o.Refused,'regular root file'):
                    o.measure(types.SimpleNamespace(prov='fixture-test',agare='fixture-owner'),'fixture',{},None,'a'*32,path)
                run.assert_not_called()


class AgentUmaskTests(unittest.TestCase):
    """Real file/Git creation under the owner's actual restrictive umask.

    Same-UID mode observations; actual installed cross-UID access is separate.
    """
    def test_shared_descriptors_and_private_results_have_explicit_modes(self):
        import json,os,stat,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();previous=os.umask(0o077)
            try:
                for name,public in [('observation.json',True),('stop.json',True),('primary.json',False)]:
                    path=root/name;o.write_owner(path,{'version':1},public=public)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644 if public else 0o600,name)
                    o.write_owner(path,{'version':2},public=public,replace=True)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644 if public else 0o600,name)
                    self.assertEqual(json.loads(path.read_text()),{'version':2})
            finally:os.umask(previous)

    def test_actual_snapshot_creation_keeps_shared_tools_and_git_readable_under_agent_umask(self):
        import json,os,stat,subprocess,tempfile,types
        from pathlib import Path
        from scripts import matning_provanvandare as fast
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();repo=root/'original';repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),'-c','user.name=Fixture',
                    '-c','user.email=fixture@example.invalid',*args],stderr=subprocess.PIPE)
            git('init','-q','-b','main');(repo/'nested').mkdir()
            (repo/'nested/value.txt').write_text('fixture')
            executable=repo/'example.sh';executable.write_text('#!/bin/sh\nexit 0\n');executable.chmod(0o755)
            git('add','.');git('commit','-qm','fixture')
            commit=git('rev-parse','HEAD').decode().strip();tree=git('rev-parse','HEAD^{tree}').decode().strip()
            inbox=root/'shared/in';base=inbox/'fixture';base.mkdir(parents=True)
            for path in (inbox.parent,inbox,base):path.chmod(0o755)
            bundle=base/'kandidat.bundle';git('bundle','create',str(bundle),'--branches');bundle.chmod(0o644)
            request={'candidate':commit,'tree':tree,'repo':'runtime'}
            (base/'begaran.json').write_text(json.dumps(request));(base/'begaran.json').chmod(0o644)
            host=root/'host'
            for name in fast.PROFILER['runtime']['lankar']:(host/'.runtime'/name).mkdir(parents=True,exist_ok=True)
            plats=types.SimpleNamespace(inkorg=inbox,arbete=root/'test-work',runtime=host)
            previous=os.umask(0o077)
            try:source,files=o.materialize_snapshot(plats,'fixture',request,bundle)
            finally:os.umask(previous)
            self.assertEqual(stat.S_IMODE((source/'.runtime').stat().st_mode),0o755)
            self.assertEqual(stat.S_IMODE(source.stat().st_mode),0o755)
            self.assertEqual(stat.S_IMODE((source/'nested/value.txt').stat().st_mode),0o644)
            self.assertEqual(stat.S_IMODE((source/'example.sh').stat().st_mode),0o755)
            for path in (source/'.git').rglob('*'):
                if path.is_file():
                    with self.subTest(metadata=path.relative_to(source).as_posix()):
                        self.assertTrue(path.stat().st_mode & 0o004)
                        self.assertFalse(path.stat().st_mode & 0o022)
            self.assertEqual((source/'.scratch').readlink(),plats.arbete/'fixture/scratch')
            self.assertEqual(set(files),{'example.sh','nested/value.txt'})
            for name in fast.PROFILER['runtime']['lankar']:
                self.assertEqual((source/'.runtime'/name).resolve(),(host/'.runtime'/name).resolve())


class QualificationEvidenceTests(unittest.TestCase):
    def test_process_identities_survive_interrupted_transport_without_suite(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();rows=[]
            first={'stage':'before','test_uid':470,'processes':[],'transport':None,'observed_at':1.0}
            second={'stage':'cleanup-before','test_uid':470,'processes':[{'pid':101,'ppid':99,'pgid':101,'uid':470,'started':'synthetic'}],
                    'transport':None,'observed_at':2.0}
            with self.assertRaisesRegex(OSError,'synthetic transport loss'):
                o.retain_process_snapshot(root,rows,first)
                o.retain_process_snapshot(root,rows,second)
                raise OSError('synthetic transport loss')
            self.assertFalse((root/'suite.json').exists())
            self.assertEqual([json.loads(p.read_text()) for p in sorted(root.glob('process-*.json'))],[first,second])
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in root.glob('process-*.json')))
            with self.assertRaises(FileExistsError):o.retain_process_snapshot(root,[],first)

    def test_named_key_flag_does_not_clear_unknown_sweep(self):
        import copy
        probe={'kredentialfri':True,'nycklar_lasbara':[], 'svep':{'antal':0,'lasbara_med_nyckelnamn':[],'avbrutet':None}}
        self.assertTrue(o.clean_boundary_probe(probe))
        for change in ({'antal':1,'lasbara_med_nyckelnamn':['synthetic filename']},{'antal':True},{'avbrutet':'cut'},{'lasbara_med_nyckelnamn':['synthetic filename']}):
            value=copy.deepcopy(probe);value['svep'].update(change)
            with self.subTest(change=change):self.assertFalse(o.clean_boundary_probe(value))
        self.assertFalse(o.clean_boundary_probe({'kredentialfri':True}));self.assertFalse(o.clean_boundary_probe(None))
    def test_process_snapshot_preserves_real_identities_without_arguments(self):
        import os
        from types import SimpleNamespace
        row=o.process_snapshot(os.getuid(),'fixture',SimpleNamespace(pid=os.getpid()))
        self.assertEqual(row['transport']['pid'],os.getpid());self.assertEqual(row['transport']['uid'],os.getuid())
        self.assertEqual(row['stage'],'fixture');self.assertTrue(row['processes'])
        for proc in [row['transport'],*row['processes']]:
            self.assertEqual(set(proc),{'pid','ppid','pgid','uid','started'})
