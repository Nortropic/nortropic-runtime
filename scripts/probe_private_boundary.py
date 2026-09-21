"""Real native private filesystem/network boundary; no model or private data output."""
import json
import os
from pathlib import Path
import subprocess
import uuid
from runtime.profile import ROOT, sandbox_command, environment


def main():
    home=ROOT/'.runtime/ap10/build-evidence'/('boundary-'+uuid.uuid4().hex)
    work=home/'workspace';work.mkdir(parents=True);(work/'.scratch').mkdir()
    (work/'input.txt').write_text('synthetic evidence')
    outside=home/'publisher-canary';outside.write_text('synthetic credential, not a real secret')
    script=r'''
import pathlib,json,socket,subprocess,os
w=pathlib.Path.cwd();out={}
assert (w/'input.txt').read_text()=='synthetic evidence'
(w/'.scratch/result.txt').write_text('allowed scratch')
def denied(name,fn):
 try:fn()
 except (OSError,PermissionError):out[name]='denied'
 else:raise AssertionError('Unexpected access: '+name)
denied('input-write',lambda:(w/'input.txt').write_text('tamper'))
denied('outside-private-read',lambda:(w.parent/'publisher-canary').read_text())
denied('outside-write',lambda:(w.parent/'unauthorized.txt').write_text('tamper'))
denied('publisher-config-read',lambda:list((pathlib.Path.home()/'.config/gh').iterdir()))
s=socket.socket();s.settimeout(1)
denied('temporal-control-network',lambda:s.connect(('127.0.0.1',7339)));s.close()
# Never print or retain token bytes, even if an unexpected grant existed.
p=subprocess.run(['/opt/homebrew/bin/gh','auth','token'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
assert p.returncode!=0,'Publisher credential unexpectedly available'
out['publisher-credential-command']='unavailable';out['model_calls']=0;out['passed']=True
print(json.dumps(out))
'''
    p=subprocess.run(sandbox_command(work,['/opt/homebrew/bin/python3.12','-I','-B','-c',script]),
                     env=environment(),capture_output=True,text=True,timeout=30)
    (home/'stderr.txt').write_text(p.stderr)
    if p.returncode:raise RuntimeError('Native boundary probe failed; inspect '+str(home))
    result=json.loads(p.stdout)
    assert (work/'input.txt').read_text()=='synthetic evidence' and outside.read_text()=='synthetic credential, not a real secret'
    (home/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(home)


if __name__=='__main__':main()
