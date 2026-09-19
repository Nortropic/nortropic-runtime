"""Frozen host assertions; candidate code runs only in read-only source sandbox."""
import hashlib
import json
from pathlib import Path
import tempfile

from acceptance.run_report_phase1 import run as isolated_run
from runtime.profile import ROOT
from runtime.snapshot import read_regular


PATHS = ['tools/evidence_index.py','tools/test_evidence_index.py','tools/EVIDENCE_INDEX.md']


def run(workspace, argv, stdin=None):
    return isolated_run(workspace, ['/usr/bin/env', 'TMPDIR='+str(workspace/'.scratch'), *argv], stdin)


def verify(candidate):
    observations=[]
    with tempfile.TemporaryDirectory(prefix='evidence-acceptance-',dir=ROOT/'.runtime') as temp:
        workspace=Path(temp)
        (workspace/'tools').mkdir(); (workspace/'.scratch').mkdir()
        for name in PATHS: (workspace/name).write_bytes(read_regular(candidate,name))
        fixtures=workspace/'fixtures';fixtures.mkdir()
        (fixtures/'nested').mkdir();(fixtures/'nested/å.bin').write_bytes(b'\x00\xff\n')
        (fixtures/'a.txt').write_bytes(b'original\n');(fixtures/'empty').write_bytes(b'')
        (fixtures/'link').symlink_to(fixtures/'a.txt');(fixtures/'dirlink').symlink_to(fixtures/'nested')
        import os
        os.mkfifo(fixtures/'fifo')
        root=str(fixtures)
        entry=lambda path,data: {'path':path,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        good={'version':1,'files':[entry('a.txt',b'original\n'),entry('nested/å.bin',b'\x00\xff\n')]}
        def check(label,args,stdin,code,expected=None,error=False):
            result=run(workspace,['/opt/homebrew/bin/python3.12','-B','tools/evidence_index.py',*args],stdin)
            try: actual=json.loads(result.stdout)
            except ValueError: actual=None
            passed=result.returncode==code and (isinstance(actual,dict) and isinstance(actual.get('error'),str) and bool(actual['error']) if error else actual==expected)
            observations.append({'case':label,'passed':passed,'returncode':result.returncode,'actual':actual,'stderr':result.stderr})
        check('create binary/unicode sorted',['create',root,'nested/å.bin','a.txt'],None,0,good)
        check('create empty',['create',root],None,0,{'version':1,'files':[]})
        check('verify exact',['verify',root],json.dumps(good),0,{'ok':True,'files':[{'path':x['path'],'status':'ok'} for x in good['files']]})
        mixed={'version':1,'files':[entry('missing',b''),entry('a.txt',b'wrong'),entry('link',b'original\n'),entry('fifo',b''),entry('nested/å.bin',b'\x00\xff\n')]}
        check('inspect all mismatches',['verify',root],json.dumps(mixed),1,{'ok':False,'files':[{'path':p,'status':s} for p,s in [('a.txt','changed'),('fifo','unsafe'),('link','unsafe'),('missing','missing'),('nested/å.bin','ok')]]})
        for path in ['../a.txt','/etc/passwd','nested//å.bin','nested/./å.bin','C:/file','link','dirlink/å.bin','fifo','missing']:
            check('refuse create '+path,['create',root,path],None,2,error=True)
        check('duplicate selected path',['create',root,'a.txt','a.txt'],None,2,error=True)
        invalid=[{}, {'version':True,'files':[]}, {'version':1,'files':[entry('../x',b'')]},
                 {'version':1,'files':[entry('a.txt',b''),entry('a.txt',b'')]},
                 {'version':1,'files':[{**entry('a.txt',b''),'size':True}]},
                 {'version':1,'files':[{**entry('a.txt',b''),'sha256':'A'*64}]}]
        for i,value in enumerate(invalid):check('invalid manifest '+str(i),['verify',root],json.dumps(value),2,error=True)
        check('duplicate JSON key',['verify',root],'{"version":0,"version":1,"files":[]}',2,error=True)
        check('invalid JSON',['verify',root],'{',2,error=True)
        check('invalid command',['unknown',root],None,2,error=True)
        code=('from tools.evidence_index import create,verify; import json; '
              'm=create('+repr(root)+',["empty"]); print(json.dumps(verify('+repr(root)+',m)))')
        result=run(workspace,['/opt/homebrew/bin/python3.12','-B','-c',code])
        try:actual=json.loads(result.stdout)
        except ValueError:actual=None
        observations.append({'case':'importable functions','passed':result.returncode==0 and actual=={'ok':True,'files':[{'path':'empty','status':'ok'}]},'actual':actual,'stderr':result.stderr})
        result=run(workspace,['/opt/homebrew/bin/python3.12','-B','-m','unittest','discover','-s','tools','-p','test_evidence_index.py','-v'])
        observations.append({'case':'candidate tests','passed':result.returncode==0 and 'Ran 0 tests' not in result.stderr,'stdout':result.stdout,'stderr':result.stderr})
    return {'passed':all(x['passed'] for x in observations),'observations':observations}
