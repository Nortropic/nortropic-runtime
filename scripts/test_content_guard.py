"""Host scanner observes complete blobs, never executes the candidate scanner."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import content_guard as c


class ContentGuardTest(unittest.TestCase):
    def test_policy_read_acl_for_other_non_test_account_is_refused(self):
        policy=self.root/'private-policy.json';policy.write_text('{"schema":1}');policy.chmod(0o600)
        subprocess.run(['/bin/chmod','+a','user:_spotlight allow read',str(policy)],check=True)
        with self.assertRaises(c.ContentRefused):c.load_policy(policy)

    def test_publication_fixture_uses_real_private_policy_parser(self):
        from scripts.test_integration import private_content_policy
        policy=private_content_policy(self)
        self.assertEqual(c.load_policy()['literals'],[])
        policy.write_text('not JSON')
        with self.assertRaises(c.ContentRefused):c.load_policy()
        policy.write_text('{"schema":1}');policy.chmod(0o644)
        with self.assertRaises(c.ContentRefused):c.load_policy()
        policy.chmod(0o600);policy.unlink()
        with self.assertRaises(c.ContentRefused):c.load_policy()

    def test_policy_and_literals_refuse_acl_access_on_file_or_ancestor(self):
        import types
        folder=self.root/'policy-home';folder.mkdir(mode=0o700)
        policy=folder/'policy.json';literal=folder/'literals.txt'
        literal.write_text('synthetic-private-value\n');literal.chmod(0o600)
        policy.write_text(json.dumps({'schema':1,'literal_file':str(literal)}));policy.chmod(0o600)
        self.assertEqual(c.load_policy(policy)['literals'],[b'synthetic-private-value'])
        original=c.subprocess.run
        accounts={'_nortropicprov':(470,20),'alias_test_uid':(470,20),'other_reader':(89,89)}
        def user(name):
            if name not in accounts:raise KeyError(name)
            uid,gid=accounts[name];return types.SimpleNamespace(pw_uid=uid,pw_gid=gid,pw_name=name)
        for target in (policy,literal,folder):
            for ace in ('user:alias_test_uid allow write', 'user:alias_test_uid allow read',
                        'group:staff allow delete_child', 'group:everyone allow write',
                        'user:other_reader allow writeattr', 'user:unknown allow read',
                        'user:other_reader allow unknown_right', 'unparseable ACL'):
                def command(argv,**kwargs):
                    if argv==['/bin/ls','-lde',str(target)]:
                        return subprocess.CompletedProcess(argv,0,('mode fixture\n 0: '+ace+'\n').encode(),b'')
                    return original(argv,**kwargs)
                with self.subTest(target=target.name,ace=ace),patch.object(c.subprocess,'run',side_effect=command),patch.object(c.pwd,'getpwnam',side_effect=user),patch.object(c.os,'getgrouplist',return_value=[20]),patch.object(c.grp,'getgrnam',return_value=types.SimpleNamespace(gr_gid=20)):
                    with self.assertRaises(c.ContentRefused):c.load_policy(policy)
        def readonly(argv,**kwargs):
            if argv==['/bin/ls','-lde',str(folder)]:
                return subprocess.CompletedProcess(argv,0,b'mode fixture\n 0: user:other_reader inherited allow read,readattr,file_inherit\n',b'')
            return original(argv,**kwargs)
        with patch.object(c.subprocess,'run',side_effect=readonly),patch.object(c.pwd,'getpwnam',side_effect=user),patch.object(c.os,'getgrouplist',return_value=[20]):
            self.assertEqual(c.load_policy(policy)['literals'],[b'synthetic-private-value'])

    def test_policy_parent_modes_and_unknown_default_presence_are_not_absence(self):
        import types
        folder=self.root/'mutable';folder.mkdir(mode=0o700)
        policy=folder/'policy.json';policy.write_text('{"schema":1}');policy.chmod(0o600)
        folder.chmod(0o777)
        try:
            with self.assertRaises(c.ContentRefused):c.load_policy(policy)
        finally:folder.chmod(0o700)
        self.assertEqual(c.load_policy(policy)['literals'],[])
        home=self.root/'home';home.mkdir();default=home/'Library/Application Support/Nortropic/content-guard.json'
        original=Path.lstat
        def inaccessible(path,*args,**kwargs):
            if path==default:raise PermissionError('synthetic unknown presence')
            return original(path,*args,**kwargs)
        with patch.object(c.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_dir=str(home))),patch.object(Path,'lstat',inaccessible):
            with self.assertRaisesRegex(c.ContentRefused,'presence is unknown'):c.load_policy()

    def test_publication_git_selects_fixed_gh_helper_and_resets_other_helpers(self):
        from runtime.integration import publication_git
        home=self.root/'auth-home';home.mkdir()
        repo=self.root/'auth-repo';repo.mkdir()
        subprocess.run(['git','init','-q',str(repo)],check=True)
        marker=self.root/'selected-gh';poison=self.root/'wrong-helper';commands=self.root/'commands';commands.mkdir()
        gh=commands/'gh'
        gh.write_text('#!/bin/sh\n[ "$1 $2 $3" = "auth git-credential get" ] || exit 23\n'
                      'cat >/dev/null\nprintf selected >"'+str(marker)+'"\n'
                      'printf "username=fixture-only\\npassword=noncredential-fixture\\n"\n')
        gh.chmod(0o700)
        (home/'.gitconfig').write_text('[credential]\n helper = !touch "'+str(poison)+'"\n'
                                      '[credential "https://example.invalid"]\n helper = !touch "'+str(poison)+'"\n')
        environment={'HOME':str(home),'PATH':str(commands)+':'+os.environ['PATH'],
                     'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'credential.helper',
                     'GIT_CONFIG_VALUE_0':'!touch '+str(poison)}
        with patch.dict(os.environ,environment):
            configured=publication_git(repo,'config','--get-all','credential.helper').splitlines()
            self.assertEqual(configured[-2:],['','!gh auth git-credential'])
            output=publication_git(repo,'-c',
                'alias.credential-probe=!printf "protocol=https\\nhost=example.invalid\\n\\n" | git credential fill',
                'credential-probe')
        self.assertTrue(marker.exists());self.assertFalse(poison.exists())
        self.assertIn('username=fixture-only',output)

    def test_invisible_unicode_families_are_detected_in_complete_content(self):
        for point in (0x061c,0x115f,0x1160,0x180e,*range(0x200b,0x2010),
                      *range(0x202a,0x202f),*range(0x2060,0x2065),
                      *range(0x2066,0x206a),0x3164,*range(0xfe00,0xfe10),0xfeff,
                      *range(0xe0000,0xe0080),*range(0xe0100,0xe01f0)):
            with self.subTest(codepoint=point):
                value=chr(point)
                raw=b'\xff\nprefix'+value.encode()+b'suffix\n'
                result=c.scan_blob('notes.txt',raw,self.policy)
                self.assertEqual(result['findings'],[{'line':2,'category':'invisible-unicode'}])
                self.assertNotIn(value,c.safe_path('notes'+value+'.txt'))
        clean='Åäö svenska العربية 中文\n'.encode()+br'\u200b \U000e0100'
        self.assertEqual(c.scan_blob('source.py',clean,self.policy)['findings'],[])

    def test_invisible_unicode_cannot_be_hidden_by_extension_or_partial_exception(self):
        raw=('left'+chr(0x200b)+'right').encode()
        target='Nortropic/nortropic-runtime'
        self.policy['exceptions'][target,'fixture.bin']={'sha256':hashlib.sha256(raw).hexdigest(),'reason_sha256':'a'*64}
        self.assertEqual(c.scan_blob('fixture.bin',raw,self.policy,target)['findings'],[])
        for path,body,repo in [('other.bin',raw,target),('fixture.bin',raw+b' ',target),
                               ('fixture.bin',raw,'Nortropic/nortropic-digitala')]:
            self.assertEqual(c.scan_blob(path,body,self.policy,repo)['findings'][0]['category'],'invisible-unicode')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.policy = {'literals': [], 'exceptions': {}, 'literal_status': 'litterallista ej konfigurerad'}

    def test_categories_and_redaction_of_values_in_paths_and_receipts(self):
        for category, raw in [('private-key', b'-----BEGIN '+c.KEY+b'-----'),
                              ('github-token', b'ghp_'+b'X'*36),
                              ('anthropic-token', b'sk-ant-'+b'X'*40),
                              ('openai-token', b'sk-proj-'+b'X'*60),
                              ('slack-token', b'xoxb-'+b'X'*25),
                              ('aws-key', b'AKIA'+b'X'*16),
                              ('vercel-token', b'vcp_'+b'X'*30),
                              ('home-path', b'/'+b'Users/syntetisk/fil')]:
            with self.subTest(category=category):
                r = c.scan_blob('evidence/'+raw.decode().replace('/', '_')+'.txt', b'ok\n'+raw, self.policy)
                self.assertIn({'line': 2, 'category': category}, r['findings'])
                # The path itself may contain the same credential.
                if category != 'home-path': self.assertNotIn(raw.decode(), json.dumps(r))
        self.policy['literals'] = [b'private-synthetic-literal']
        r = c.scan_blob('private-synthetic-literal.txt', b'private-synthetic-literal', self.policy)
        self.assertNotIn('private-synthetic-literal', json.dumps(r))
        self.assertEqual(r['findings'], [{'line': 1, 'category': 'private-literal'}])

    def test_native_event_forms_are_detected_in_renamed_files_and_terminal_excerpts(self):
        events=[{'type':'system','subtype':'init','session_id':'synthetic'},
                {'type':'result','subtype':'success','terminal_reason':'completed','result':'synthetic',
                 'structured_output':{'verdict':'approved'}},
                {'type':'result','subtype':'error_during_execution','is_error':True},
                {'type':'error','message':'synthetic'}, {'type':'turn.failed','error':{'message':'synthetic'}},
                {'type':'item.updated','item':{'type':'command_execution','command':'synthetic'}},
                {'type':'session_meta','payload':{'cwd':'synthetic'}},
                {'type':'event_msg','payload':{'type':'task_complete'}},
                {'type':'agent_message','text':'synthetic terminal excerpt'}]
        for path in ('docs/session.txt','evidence/terminal.bin','renamed.data'):
            for event in events:
                for body in (json.dumps(event).encode(),json.dumps(event,indent=2).encode()):
                    with self.subTest(path=path,event=event['type'],pretty=b'\n' in body):
                        result=c.scan_blob(path,b'old header\n'+body+b'\nnew footer',self.policy)
                        self.assertTrue(result['findings'])
                        self.assertTrue(all(row['category']=='raw-session' for row in result['findings']))
                        self.assertGreaterEqual(result['findings'][0]['line'],2)
        self.assertEqual(c.scan_blob('curated.json',b'{"schema":1,"passed":true}',self.policy)['findings'],[])

    def test_curated_native_terminal_requires_exact_target_path_and_bytes_exception(self):
        target='Nortropic/nortropic-runtime';path='docs/terminal.txt'
        raw=json.dumps({'type':'result','subtype':'success','terminal_reason':'completed',
                        'result':'synthetic','structured_output':{'verdict':'approved'}}).encode()
        self.policy['exceptions'][target,path]={'sha256':hashlib.sha256(raw).hexdigest(),'reason_sha256':'a'*64}
        self.assertEqual(c.scan_blob(path,raw,self.policy,target)['findings'],[])
        for name,body,repo in [('renamed.txt',raw,target),(path,raw+b' ',target),
                               (path,raw,'Nortropic/nortropic-digitala'),(path,raw,None)]:
            with self.subTest(path=name,target=repo):
                self.assertEqual(c.scan_blob(name,body,self.policy,repo)['findings'],[{'line':1,'category':'raw-session'}])

    def test_raw_stream_and_exact_byte_exception(self):
        raw = json.dumps({'type':'tool_result','content':'synthetic'}).encode()+b'\n'
        self.assertTrue(c.scan_blob('evidence/arbitrary.json', raw, self.policy)['findings'])
        self.assertTrue(c.scan_blob('evidence/session/stdout.log', b'partial', self.policy)['findings'])
        self.policy['exceptions']['Nortropic/nortropic-runtime','evidence/arbitrary.json'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'reason_sha256': 'f'*64}
        self.assertEqual(c.scan_blob('evidence/arbitrary.json', raw, self.policy, 'Nortropic/nortropic-runtime')['findings'], [])
        self.assertTrue(c.scan_blob('evidence/arbitrary.json', raw+b' ', self.policy)['findings'])
        self.assertTrue(c.scan_blob('evidence/other.json', raw, self.policy)['findings'])
        self.assertEqual(c.scan_blob('receipt.json', b'{"schema":1,"passed":true}', self.policy)['findings'], [])

    def test_exceptions_are_target_bound_and_streams_are_extension_independent(self):
        raw = json.dumps({'type':'assistant','message':'synthetic'}).encode()
        row = {'target':'Nortropic/nortropic-runtime','path':'docs/session.txt',
               'sha256':hashlib.sha256(raw).hexdigest(),'reason':'Named synthetic test fixture'}
        p=self.root/'policy.json';p.write_text(json.dumps({'schema':1,'exceptions':[row]}));p.chmod(0o600)
        policy=c.load_policy(p)
        self.assertFalse(c.scan_blob(row['path'],raw,policy,row['target'])['findings'])
        for target in (None,'Nortropic/nortropic-digitala'):
            self.assertEqual(c.scan_blob(row['path'],raw,policy,target)['findings'],[{'line':1,'category':'raw-session'}])
        row.pop('target');p.write_text(json.dumps({'schema':1,'exceptions':[row]}))
        with self.assertRaises(c.ContentRefused):c.load_policy(p)

    def test_replacement_objects_cannot_hide_transferred_bytes(self):
        from runtime.integration import publication_git
        from runtime.check_issuer import frozen_snapshot
        repo=self.root/'replace';repo.mkdir()
        def git(*args,input=None):
            return subprocess.check_output(['git','-C',str(repo),*args],input=input,stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Synthetic');git('config','user.email','test@example.invalid')
        raw=b'-----BEGIN '+c.KEY+b'-----';(repo/'note.txt').write_bytes(raw)
        git('add','.');git('commit','-m','original');head=git('rev-parse','HEAD');oid=git('rev-parse','HEAD:note.txt')
        replacement=git('hash-object','-w','--stdin',input=b'innocent replacement')
        git('replace',oid,replacement)
        self.assertEqual(git('cat-file','blob',oid),'innocent replacement')
        self.assertEqual(publication_git(repo,'cat-file','blob',oid,text=False),raw)
        self.assertFalse(c.scan_tree(repo,head,policy=self.policy)['passed'])
        dest=self.root/'snapshot';dest.mkdir();frozen_snapshot(repo,head,dest)
        self.assertEqual((dest/'note.txt').read_bytes(),raw)

    def test_private_policy_missing_empty_invalid_link_and_repo_are_closed(self):
        policy = self.root/'policy.json';literal = self.root/'literal.txt'
        def write(p, raw): p.write_bytes(raw);p.chmod(0o600)
        write(policy, json.dumps({'schema': 1, 'literal_file': str(literal)}).encode())
        for raw in (None, b'', b'\n', b'\xff'):
            if raw is not None: write(literal, raw)
            with self.assertRaises(c.ContentRefused): c.load_policy(policy)
        write(literal, b'private-synthetic-literal\n')
        self.assertEqual(c.load_policy(policy)['literals'], [b'private-synthetic-literal'])
        literal.chmod(0o644)
        with self.assertRaises(c.ContentRefused): c.load_policy(policy)
        literal.chmod(0o600);link=self.root/'link';link.symlink_to(literal)
        write(policy, json.dumps({'schema':1,'literal_file':str(link)}).encode())
        with self.assertRaises(c.ContentRefused): c.load_policy(policy)
        write(policy, b'{"schema":1}')
        (self.root/'.git').mkdir()
        with self.assertRaises(c.ContentRefused): c.load_policy(policy)

    def test_changed_whole_blob_and_candidate_cannot_disable_host_scanner(self):
        repo=self.root/'repo';repo.mkdir()
        def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Synthetic');git('config','user.email','test@example.invalid')
        raw=b'header\n'+b'ghp_'+b'X'*36+b'\nold line\n'
        (repo/'file.txt').write_bytes(raw);git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
        (repo/'file.txt').write_bytes(raw+b'new line\n');(repo/'runtime').mkdir()
        (repo/'runtime/content_guard.py').write_text('raise RuntimeError("must never execute")\n')
        git('add','.');git('commit','-m','candidate');head=git('rev-parse','HEAD')
        r=c.scan_tree(repo,head,base,self.policy)
        self.assertFalse(r['passed']);self.assertEqual(r['files'][0]['findings'][0]['line'],2)
        with patch.object(c,'load_policy',return_value=self.policy):
            with self.assertRaises(c.ContentRefused) as error:c.require_content(repo,base,head,'Nortropic/nortropic-runtime')
        self.assertNotIn('ghp_'+ 'X'*36,str(error.exception))
        self.assertIn('github-token',str(error.exception))
        (repo/'file.txt').write_text('clean\n');git('add','.');git('commit','--amend','--no-edit');head=git('rev-parse','HEAD')
        self.assertTrue(c.scan_tree(repo,head,base,self.policy)['passed'])

    def test_deletion_requires_exact_private_target_base_path_and_bytes(self):
        repo=self.root/'repo';repo.mkdir()
        def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Synthetic');git('config','user.email','test@example.invalid')
        raw=b'preserved original fixture\n';(repo/'old.txt').write_bytes(raw);git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
        target='Nortropic/nortropic-runtime';row={'target':target,'path':'old.txt','base':base,'sha256':hashlib.sha256(raw).hexdigest(),'reason':'Exact private archive verified'}
        policy_file=self.root/'policy.json';policy_file.write_text(json.dumps({'schema':1,'deletions':[row]}));policy_file.chmod(0o600)
        policy=c.load_policy(policy_file)
        self.assertEqual(c.require_deletion(repo,base,'old.txt',target,policy)['sha256'],row['sha256'])
        for b,p,t in ((base,'other.txt',target),('a'*40,'old.txt',target),(base,'old.txt','Nortropic/nortropic-digitala')):
            with self.assertRaises(c.ContentRefused):c.require_deletion(repo,b,p,t,policy)
        policy['deletions'][target,base,'old.txt']['sha256']='0'*64
        with self.assertRaises(c.ContentRefused):c.require_deletion(repo,base,'old.txt',target,policy)
        policy_file.write_text(json.dumps({'schema':1,'deletions':{}}))
        with self.assertRaises(c.ContentRefused):c.load_policy(policy_file)
        row['reason']='';policy_file.write_text(json.dumps({'schema':1,'deletions':[row]}))
        with self.assertRaises(c.ContentRefused):c.load_policy(policy_file)

    def test_each_publisher_target_rejects_poison_before_push(self):
        from types import SimpleNamespace
        from runtime.integration import Publisher, GateClosed
        from runtime.check_issuer import DigitalaPublisher
        for target in ('Nortropic/nortropic-runtime','Nortropic/nortropic-projektkontor','Nortropic/nortropic-digitala'):
            repo=self.root/target.split('/')[-1];repo.mkdir()
            def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.name','Synthetic');git('config','user.email','test@example.invalid')
            git('remote','add','origin','https://github.com/'+target+'.git')
            (repo/'seed').write_text('base');git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            (repo/'runtime').mkdir();(repo/'runtime/content_guard.py').write_text('def scan_tree(*a): return {"passed": True}\n')
            (repo/'evidence').mkdir();path=repo/'evidence/data.json'
            publisher=DigitalaPublisher(SimpleNamespace(host=self.root/'runtime')) if target.endswith('digitala') else Publisher(repo,target)
            self.policy['literals']=[b'synthetic-private-literal']
            for raw in (b'-----BEGIN '+c.KEY+b'-----', b'/'+b'home/synthetic/file', json.dumps({'type':'tool_result','content':'x'}).encode(), b'synthetic-private-literal'):
                path.write_bytes(raw);git('add','.')
                git('commit','-m','candidate') if git('rev-parse','HEAD')==base else git('commit','--amend','--no-edit')
                head=git('rev-parse','HEAD');task={'target':target,'allowed_paths':['evidence/data.json','runtime/content_guard.py']}
                with patch.object(c,'load_policy',return_value=self.policy), self.assertRaises(GateClosed) as error:
                    publisher.inspect_candidate(task,{'base':base,'candidate':head})
                self.assertNotIn(raw.decode(),str(error.exception))
            path.write_text('clean');git('add','.');git('commit','--amend','--no-edit')
            with patch.object(c,'load_policy',return_value=self.policy):
                self.assertEqual(publisher.inspect_candidate(task,{'base':base,'candidate':git('rev-parse','HEAD')}),git('rev-parse','HEAD^{tree}'))

    def test_local_push_skips_hook_and_rejects_redirected_remote(self):
        from runtime.integration import Publisher, GateClosed, require_git_origin
        remote=self.root/'remote.git';repo=self.root/'work';repo.mkdir()
        subprocess.run(['git','init','--bare',str(remote)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Synthetic');git('config','user.email','test@example.invalid')
        git('remote','add','origin',str(remote));(repo/'seed').write_text('base');git('add','.');git('commit','-m','base')
        hook=repo/'.git/hooks/pre-push';marker=self.root/'hook-executed'
        hook.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');hook.chmod(0o755)
        p=Publisher(repo);p.ORIGIN=str(remote)
        p.git('push','origin','HEAD:refs/heads/accepted')
        self.assertFalse(marker.exists())
        self.assertEqual(subprocess.check_output(['git','--git-dir',str(remote),'rev-parse','accepted'],text=True).strip(),git('rev-parse','HEAD'))
        git('config','remote.origin.pushurl',str(self.root/'other.git'))
        with self.assertRaises(GateClosed):p.git('push','origin','HEAD:refs/heads/rejected')
        git('config','--unset','remote.origin.pushurl')
        git('config','url.'+str(self.root/'other')+'.pushInsteadOf',str(remote))
        with self.assertRaises(GateClosed):require_git_origin(repo,str(remote))
        git('config','--unset','url.'+str(self.root/'other')+'.pushInsteadOf')
        git('config','credential.helper','!touch '+str(marker))
        with self.assertRaises(GateClosed):p.git('push','origin','HEAD:refs/heads/rejected')
        self.assertFalse(marker.exists())

    def test_all_git_boolean_forms_receive_worktree_transport_checks(self):
        from runtime.integration import GateClosed,publication_git,require_git_origin
        repo=self.root/'boolean-repo';repo.mkdir();linked=self.root/'boolean-linked'
        def git(where,*args):
            return subprocess.check_output(['git','-C',str(where),*args],stderr=subprocess.DEVNULL).decode().strip()
        git(repo,'init','-q');git(repo,'config','user.name','Fixture');git(repo,'config','user.email','fixture@example.invalid')
        git(repo,'commit','--allow-empty','-qm','fixture');git(repo,'worktree','add','--detach',str(linked),'HEAD')
        expected='https://github.com/Nortropic/nortropic-runtime.git';git(repo,'remote','add','origin',expected)
        config=repo/'.git/config';original=config.read_text()
        for worktree in (repo,linked):
            path=Path(git(worktree,'rev-parse','--path-format=absolute','--git-path','config.worktree'))
            path.write_text('[http]\nproxy = http://127.0.0.1:9\nsslVerify = false\n')
        for value,active in [(None,True),('2',True),('-1',True),('true',True),('yes',True),('on',True),('1',True),('false',False),('no',False),('off',False),('0',False),('',False)]:
            config.write_text(original+'\n[extensions]\nworktreeConfig'+('' if value is None else ' = '+value)+'\n')
            for worktree in (repo,linked):
                with self.subTest(value=value,worktree=worktree.name):
                    self.assertEqual(git(worktree,'config','--bool','--get','extensions.worktreeConfig'),str(active).lower())
                    if active:
                        self.assertEqual(publication_git(worktree,'config','--get','http.sslVerify').strip(),'false')
                        with self.assertRaisesRegex(GateClosed,'Unsafe repository-local'):require_git_origin(worktree,expected)
                    else:require_git_origin(worktree,expected)


if __name__ == '__main__': unittest.main()
