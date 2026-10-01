"""Private ledger and real timed unittest process, with only synthetic failures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime import failure_ledger as ledger
from scripts import matning_provanvandare as fast

COMMIT = 'a' * 40
SOURCE = 'b' * 64


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.book = ledger.Ledger(self.root / 'private', {'literals': []})

    def record(self, phase, status='failure', source=None):
        run = self.book.begin(COMMIT, phase, SOURCE, diagnostic_of=source)
        self.book.finish(run, [{'name': 'test_fixture.T.test_first', 'seconds': .01, 'status': status}], 0 if status == 'success' else 1)
        return run

    def test_begin_syncs_its_directory_before_returning_and_failed_sync_stays_incomplete(self):
        seen=[];original=ledger.sync_directory
        def sync(path):
            seen.append([p.name for p in path.glob('*-begin.json')]);return original(path)
        with patch.object(ledger,'sync_directory',side_effect=sync):run=self.book.begin(COMMIT,'regression',SOURCE)
        self.assertIn(run+'-begin.json',seen[-1])
        with patch.object(ledger,'sync_directory',side_effect=OSError('synthetic reservation sync failure')):
            with self.assertRaisesRegex(OSError,'reservation sync'):self.book.begin(COMMIT,'regression',SOURCE)
        self.assertEqual(len(list(self.book.directory.glob('*-begin.json'))),2)
        self.assertFalse(self.book.publishable(COMMIT))

    def test_new_ledger_directories_and_parents_are_synced_before_use(self):
        seen=[];original=ledger.sync_directory;path=self.root/'new-parent/ledger'
        def sync(where):seen.append(where);return original(where)
        with patch.object(ledger,'sync_directory',side_effect=sync):ledger.Ledger(path,{'literals':[]})
        self.assertEqual(seen,[path,path.parent,path.parent,self.root])

    def test_private_ledger_refuses_read_acl_for_another_non_test_account(self):
        run=self.record('regression','success');record=self.book.directory/(run+'-finish.json')
        subprocess.run(['/bin/chmod','+a','user:_spotlight allow read',str(record)],check=True)
        with self.assertRaises(ledger.Refused):self.book.require_publishable(COMMIT)

    def test_primary_observation_digest_is_retained_and_malformed_binding_refused(self):
        run=self.book.begin(COMMIT,'regression',SOURCE)
        with self.assertRaisesRegex(ledger.Refused,'primary observation'):
            self.book.finish(run,[{'name':'test_x.T.test_x','status':'success','seconds':.1}],0,observation_sha256='bad')
        self.assertFalse((self.book.directory/(run+'-finish.json')).exists())
        end=self.book.finish(run,[{'name':'test_x.T.test_x','status':'success','seconds':.1}],0,observation_sha256='c'*64)
        self.assertEqual(self.book.ending(self.book.begin_record(run+'-begin.json'))['observation_sha256'],'c'*64)
        path=self.book.directory/(run+'-finish.json');path.chmod(0o600);path.write_text(json.dumps({**end,'observation_sha256':1}));path.chmod(0o400)
        self.assertFalse(self.book.publishable(COMMIT))

    def test_finish_is_not_committed_before_fsync_and_acl_checks(self):
        cases=[{'name':'test_x.T.test_x','status':'success','seconds':.1}]
        for point in ('fsync','acl','link'):
            run=self.book.begin(COMMIT,'regression',SOURCE)
            original=ledger.require_acl
            def check(path,**kwargs):
                if path.name.startswith('.pending-'):raise ledger.Refused('synthetic ACL loss')
                return original(path,**kwargs)
            target=patch.object(ledger,'require_acl',side_effect=check) if point=='acl' else patch.object(ledger.os,point,side_effect=OSError('synthetic '+point+' loss'))
            with self.subTest(point=point),target,self.assertRaises((OSError,ledger.Refused)):
                self.book.finish(run,cases,0)
            self.assertFalse((self.book.directory/(run+'-finish.json')).exists())
            self.assertFalse(self.book.publishable(COMMIT))

    def test_record_commit_never_replaces_existing_and_cleanup_cannot_abort_it(self):
        cases=[{'name':'test_x.T.test_x','status':'success','seconds':.1}]
        run=self.book.begin(COMMIT,'regression',SOURCE);original=Path.unlink
        def fail_staging(path,*args,**kwargs):
            if path.name.startswith('.pending-'):raise OSError('synthetic staging cleanup loss')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_staging):self.book.finish(run,cases,0)
        self.assertTrue(self.book.publishable(COMMIT))
        path=self.book.directory/(run+'-finish.json');before=path.read_bytes()
        with self.assertRaises(FileExistsError):self.book.finish(run,[],124,complete=False)
        self.assertEqual(path.read_bytes(),before)

    def test_masked_failure_can_be_read_classified_and_diagnosed_without_rehashing(self):
        run = self.book.begin(COMMIT, 'regression', SOURCE)
        end = self.book.finish(run, [{'name': 'private value with spaces', 'file': '/private/value',
                                     'seconds': None, 'status': 'unknown'}], 1, complete=False)
        self.assertEqual(self.book.ending(self.book.begin_record(run+'-begin.json')), end)
        self.assertEqual(self.book.classify(run, 1, 'infrastruktur')['run'], run)
        self.record('diagnostic', 'success', run)
        self.assertFalse(self.book.publishable(COMMIT))
        self.assertEqual(self.book.ending(self.book.begin_record(run+'-begin.json')), end)

    def test_allow_acl_on_ledger_or_ancestor_or_record_refuses_even_private_modes(self):
        run = self.record('regression', 'success')
        record = self.book.directory/(run+'-begin.json')
        original = ledger.subprocess.run
        for target in (self.book.directory, self.book.directory.parent, record):
            def command(argv, **kwargs):
                if argv == ['/bin/ls', '-lde', str(target)]:
                    return subprocess.CompletedProcess(argv, 0, b'drwx------ fixture\n 0: user:fixture allow delete_child,read\n', b'')
                return original(argv, **kwargs)
            with self.subTest(target=target), patch.object(ledger.subprocess, 'run', side_effect=command):
                with self.assertRaises(ledger.Refused):
                    self.book.require_publishable(COMMIT)

    def test_acl_uses_resolved_uid_groups_and_never_a_named_account_exception(self):
        import types
        accounts = {'_nortropicprov': (470, 20), 'independent_reader': (89, 89),
                    'different_name_same_test_uid': (470, 20)}
        def user(name):
            if name not in accounts: raise KeyError(name)
            uid, gid = accounts[name]
            return types.SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid)
        with patch.object(ledger.pwd, 'getpwnam', side_effect=user), \
             patch.object(ledger.os, 'getgrouplist', return_value=[20, 61]), \
             patch.object(ledger.grp, 'getgrnam', side_effect=lambda name: types.SimpleNamespace(gr_gid=20)):
            ledger.acl_entry(' 0: user:independent_reader inherited allow read,readattr,file_inherit')
            for entry in ('user:independent_reader allow delete_child',
                          'user:different_name_same_test_uid allow read',
                          'group:staff allow read', 'group:everyone allow search',
                          'user:unknown allow read', 'user:independent_reader allow unknown_right'):
                with self.subTest(entry=entry), self.assertRaises(ledger.Refused):
                    ledger.acl_entry(' 0: '+entry)

    def test_failure_survives_later_green_and_two_reruns_are_the_limit(self):
        failed = self.record('regression')
        original = (self.book.directory / (failed + '-finish.json')).read_bytes()
        self.record('diagnostic', 'success', failed)
        self.record('diagnostic', 'success', failed)
        with self.assertRaisesRegex(ledger.Refused, 'Two diagnostic'):
            self.record('diagnostic', 'success', failed)
        self.assertFalse(self.book.publishable(COMMIT))
        self.assertEqual(original, (self.book.directory / (failed + '-finish.json')).read_bytes())
        result = self.book.classify(failed, 1, 'fixtur', intermittent=True)
        self.assertEqual((result['commit'], result['attempt'], result['case_order']), (COMMIT, 1, 1))
        self.assertFalse(self.book.publishable(COMMIT))

    def test_host_and_sealed_measurement_never_intermittent(self):
        for phase in ('sealed', 'host', 'measurement', 'dry-run', 'publication'):
            run = self.record(phase)
            with self.assertRaisesRegex(ledger.Refused, 'cannot be called intermittent'):
                self.book.classify(run, 1, 'fixtur', intermittent=True)
            self.assertEqual(self.book.classify(run, 1, 'infrastruktur')['classification'], 'infrastruktur')
        with self.assertRaisesRegex(ledger.Refused, 'explicit diagnostic'):
            self.record('measurement')

    def test_diagnostics_inherit_the_original_intermittent_classification_limit(self):
        for number,phase in enumerate(('sealed','host','measurement','dry-run','publication','regression')):
            book=ledger.Ledger(self.root/('chain-'+str(number)),{'literals':[]})
            def failed(kind,prior=None):
                run=book.begin(COMMIT,kind,SOURCE,prior)
                book.finish(run,[{'name':'fixture.T.test_case','seconds':0.01,'status':'failure'}],1)
                return run
            original=failed(phase);first=failed('diagnostic',original);second=failed('diagnostic',first)
            for run in (first,second):
                with self.subTest(phase=phase,run=run):
                    if phase=='regression':self.assertTrue(book.classify(run,1,'fixtur',intermittent=True)['intermittent'])
                    else:
                        with self.assertRaisesRegex(ledger.Refused,'cannot be called intermittent'):
                            book.classify(run,1,'fixtur',intermittent=True)
                    self.assertFalse(book.classify(run,1,'produkt')['intermittent'])
            self.assertFalse(book.publishable(COMMIT))

    def test_data_redacted_permissions_and_exact_run_binding(self):
        secret = b'arbitrary_private_marker'
        book = ledger.Ledger(self.root / 'other', {'literals': [secret]})
        run = book.begin(COMMIT, 'regression', SOURCE)
        result = book.finish(run, [{'name': 'test_x.T.test_' + secret.decode(), 'status': 'failure',
                                   'seconds': 1.25, 'traceback': secret.decode()}], 1)
        raw = b''.join(p.read_bytes() for p in book.directory.glob('*.json'))
        self.assertNotIn(secret, raw)
        self.assertTrue(result['cases'][0]['name'].startswith('masked-'))
        self.assertEqual(result['cases'][0]['seconds'], 1.25)
        self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in book.directory.iterdir()))
        with self.assertRaises(FileExistsError): book.finish(run, [], 0)
        with self.assertRaises(ledger.Refused): book.begin('c' * 40, 'diagnostic', SOURCE, run)

    def test_repositories_links_and_lost_run_cannot_pass(self):
        repo = self.root / 'repo'; repo.mkdir(); (repo / '.git').mkdir()
        with self.assertRaises(ledger.Refused): ledger.Ledger(repo / 'book', {'literals': []})
        link = self.root / 'link'; link.symlink_to(self.book.directory, target_is_directory=True)
        with self.assertRaises(ledger.Refused): ledger.Ledger(link, {'literals': []})
        self.book.begin(COMMIT, 'regression', SOURCE)
        self.assertFalse(self.book.publishable(COMMIT))

    def test_terminal_true_cannot_override_corrupt_bindings_or_failed_primary_fields(self):
        for change in ({'id':'f'*32},{'begin_sha256':'0'*64},{'complete':False},
                       {'returncode':1},{'returncode':False},
                       {'cases':[{'order':1,'name':'test_x.T.test_x','file':None,'seconds':None,'status':'unknown'}]}):
            with self.subTest(change=change):
                book=ledger.Ledger(self.root/('book-'+str(len(list(self.root.iterdir())))),{'literals':[]})
                run=book.begin(COMMIT,'regression',SOURCE)
                book.finish(run,[{'name':'test_x.T.test_x','status':'success','seconds':.01}],0)
                path=book.directory/(run+'-finish.json');value=json.loads(path.read_text());value.update(change)
                path.chmod(0o600);path.write_text(json.dumps(value));path.chmod(0o400)
                self.assertFalse(book.publishable(COMMIT))

    def test_real_timed_runner_records_file_order_failure_and_duration(self):
        repo = self.root / 'fixture'; tests = repo / 'tests'; tests.mkdir(parents=True)
        (tests / 'test_a.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_first(self): self.fail("planted-private-output")\n')
        (tests / 'test_b.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_next(self): pass\n')
        output = self.root / 'cases.jsonl'
        result = subprocess.run([sys.executable, '-B', '-c', fast.TIMED_RUNNER, 'tests', str(output)], cwd=repo, capture_output=True)
        self.assertEqual(result.returncode, 1)
        cases = fast.case_observations(output)
        self.assertEqual([c['name'] for c in cases], ['test_a.T.test_first', 'test_b.T.test_next'])
        self.assertEqual([c['status'] for c in cases], ['failure', 'success'])
        self.assertTrue(all(c['seconds'] >= 0 for c in cases))
        run = self.book.begin(COMMIT, 'measurement', hashlib.sha256(output.read_bytes()).hexdigest())
        end = self.book.finish(run, cases, result.returncode)
        self.assertEqual([c['file'] for c in end['cases']], ['tests/test_a.py', 'tests/test_b.py'])
        self.assertNotIn(b'planted-private-output', (self.book.directory / (run + '-finish.json')).read_bytes())

    def test_interrupted_timing_preserves_unknown_instead_of_zero(self):
        output = self.root / 'partial.jsonl'
        output.write_text(json.dumps({'event': 'start', 'order': 1, 'name': 'test_a.T.test_first'}) + '\n')
        self.assertEqual(fast.case_observations(output), [{'order': 1, 'name': 'test_a.T.test_first', 'file': None, 'seconds': None, 'status': 'unknown'}])

    def test_consumption_binds_separately_adopted_program_and_external_observations(self):
        expected={p:SOURCE for p in ('scripts/matning_provanvandare.py','runtime/measurement_observer.py','scripts/measurement_queue.py')}
        good={'terminal_successful':True, 'passed':True, 'case_timing_schema':3,'observation_kind':'owner-received-events/1',
              'protected_primary_files':True,'shared_interpreter_state':True,
              'complete':True,'cleanup_verified':True,'timed_out':False,'overflow':False,'fixture_errors':[],
              'credential_free_execution':True,
              'credential_boundary':{'script_sha256':SOURCE,'observer_sha256':SOURCE,'queue_sha256':SOURCE,'owner_uid':501,'test_uid':502},
              'returncode':0,'test_count':1,
              'cases':[{'order':1,'name':'test_x.T.test_one','file':'tests/test_x.py','seconds':.01,'status':'success'}]}
        rows=[{'id':c['order'],'name':c['name'],'file':c['file']} for c in good['cases']]
        good['manifest_sha256']=hashlib.sha256((json.dumps(rows,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
        changes=({'case_timing_schema':1},{'case_timing_schema':2},{'protected_primary_files':False},
                 {'credential_boundary':dict(good['credential_boundary'],script_sha256='c'*64)},
                 {'credential_boundary':dict(good['credential_boundary'],observer_sha256='c'*64)},
                 {'credential_boundary':dict(good['credential_boundary'],queue_sha256='c'*64)},
                 {'credential_boundary':dict(good['credential_boundary'],test_uid=501)},
                 {'shared_interpreter_state':False},{'observation_kind':'candidate-reported'},
                 {'cases':[dict(good['cases'][0],seconds=None)]},
                 {'cases':[dict(good['cases'][0],file='../unknown.py')]},
                 {'manifest_sha256':'c'*64},{'complete':False},{'cleanup_verified':False},
                 {'test_count':True})
        for i,change in enumerate(changes):
            book=ledger.Ledger(self.root/('seal-'+str(i)),{'literals':[]})
            with self.subTest(change=change),self.assertRaises(ledger.Refused):
                book.consume(COMMIT,'sealed',SOURCE,dict(good,**change),expected)
            self.assertFalse(book.publishable(COMMIT))
        self.book.consume(COMMIT,'sealed',SOURCE,good,expected)
        self.assertTrue(self.book.publishable(COMMIT))

    def test_candidate_cannot_edit_observation_files_source_clock_or_owner_book(self):
        import os,time
        repo=self.root/'source';(repo/'tests').mkdir(parents=True)
        out=self.root/'observed';out.mkdir()
        owner=self.root/'owner';owner.mkdir()
        marker=self.book.directory/'marker';marker.write_text('original')
        source=repo/'tests/test_boundary.py'
        code=("import unittest,time,os\nfrom pathlib import Path\n"
              "class T(unittest.TestCase):\n def test_boundary(self):\n"
              "  time.monotonic=lambda:0\n  time.sleep(.08)\n"
              "  paths="+repr([str(marker),str(out/'suite.log'),str(out/'cases.jsonl'),str(source)])+"\n"
              "  for value in paths:\n"
              "   with self.assertRaises(PermissionError):Path(value).write_text('forged')\n"
              "  with self.assertRaises(PermissionError):os.kill(os.getppid(),9)\n")
        source.write_text(code)
        env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','HOME':str(self.root/'home'),
             'TMPDIR':str(self.root/'tmp'),'PYTHONDONTWRITEBYTECODE':'1'}
        observed=fast.observe_suite(sys.executable,'tests',repo,env,out,20,expected_count=1,
                                   owner_home=owner,extra_protected=(self.book.directory,))
        self.assertEqual(observed['returncode'],0,(out/'case-00001.log').read_text())
        self.assertGreaterEqual(observed['cases'][0]['seconds'],.08)
        self.assertEqual(marker.read_text(),'original');self.assertEqual(source.read_text(),code)
        self.assertEqual(fast.case_observations(out/'cases.jsonl'),observed['cases'])
        self.assertTrue(observed['protected_primary_files'])

    def test_external_observer_keeps_failed_process_and_times_out_infinite_case(self):
        import os
        repo=self.root/'source';(repo/'tests').mkdir(parents=True)
        env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','HOME':str(self.root/'home'),'TMPDIR':str(self.root/'tmp')}
        (repo/'tests/test_cases.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_a(self):self.fail("synthetic")\n def test_b(self):\n  while True:pass\n')
        out=self.root/'observed'
        observed=fast.observe_suite(sys.executable,'tests',repo,env,out,1.5,expected_count=2,owner_home=self.root/'owner')
        self.assertEqual([c['status'] for c in observed['cases']],['failure','timeout'])
        self.assertEqual(observed['returncode'],1);self.assertTrue(observed['timed_out'])
