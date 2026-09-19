"""No-model native sandbox test with nonsecret canaries and controlled listener."""
import json
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.profile import ROOT, sandbox_command, environment


def main():
    suffix = sys.argv[1] if len(sys.argv) > 1 else ''
    if suffix not in ('', '-instructions'): raise ValueError(suffix)
    output = ROOT / ('evidence/accepted-task/boundary' + suffix + '.json')
    if output.exists():
        raise RuntimeError('Preserve prior evidence')
    ws = ROOT / ('.runtime/boundary-candidate' + suffix)
    ws.mkdir(exist_ok=False)
    (ws / 'tools').mkdir()
    (ws / '.scratch').mkdir()
    (ws / 'AGENTS.md').write_text('immutable context\n')
    outside = ROOT / '.runtime/host-boundary-canary'
    outside.write_text('nonsecret authority canary\n')
    (ws / 'tools/escape').symlink_to(outside)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        port = listener.getsockname()[1]
        code = '''import json,socket
from pathlib import Path
r={}
Path('tools/allowed.txt').write_text('ok')
r['allowed_write']=Path('tools/allowed.txt').read_text()=='ok'
for label,path,operation in [('host_read',OUT,'read'),('host_write',OUT,'write'),('context_write','AGENTS.md','write'),('symlink_write','tools/escape','write')]:
 try:
  p=Path(path)
  if operation=='read': p.read_text()
  else: p.write_text('changed')
  r[label+'_denied']=False
 except PermissionError: r[label+'_denied']=True
try:
 s=socket.create_connection(('127.0.0.1',PORT),timeout=1); s.close(); r['network_denied']=False
except PermissionError: r['network_denied']=True
print(json.dumps(r))
'''.replace('OUT', repr(str(outside))).replace('PORT', str(port))
        cmd = sandbox_command(ws, ['/opt/homebrew/bin/python3.12', '-c', code])
        r = subprocess.run(cmd, capture_output=True, text=True, env=environment(), timeout=15)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    passed = len(data) == 6 and all(data.values()) and outside.read_text() == 'nonsecret authority canary\n'
    output.write_text(json.dumps({'passed': passed,'model_calls':0,'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'observations':data},indent=2)+'\n')
    print(json.dumps({'passed':passed,'observations':data,'stderr':r.stderr}))
    return 0 if passed else 1

if __name__ == '__main__': raise SystemExit(main())
