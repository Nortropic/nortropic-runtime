#!/usr/bin/env python3
"""Narrow Symphony app-server boundary for the first fixture experiment.

Symphony owns dispatch. This bridge removes host-authenticated dynamic tools,
enforces the fixture sandbox, records protocol evidence and permits one launch.
It is NOT the general Runtime adapter or a claimed v0.1 permission boundary.
"""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = ROOT / '.runtime' / 'workspaces'


def restrict_message(message, workspace):
    method = message.get('method')
    if method in ('thread/start', 'turn/start'):
        params = message.setdefault('params', {})
        params['cwd'] = str(workspace)
        params['approvalPolicy'] = {'reject': {'sandbox_approval': True, 'rules': True, 'mcp_elicitations': True}}
        if method == 'thread/start':
            params['dynamicTools'] = []
            params['sandbox'] = 'workspace-write'
            params['model'] = 'gpt-6-astra'
        else:
            params['sandboxPolicy'] = {
                'type': 'workspaceWrite', 'writableRoots': [str(workspace)],
                'networkAccess': False, 'excludeTmpdirEnvVar': True,
                'excludeSlashTmp': True,
            }
    return message


def main():
    workspace = Path.cwd().resolve()
    if workspace.parent != WORKSPACES.resolve():
        raise RuntimeError('Not an isolated Symphony fixture workspace')
    contract = json.loads((ROOT / 'config/motor-probe.json').read_text())
    if workspace.name != 'GH-' + str(contract['issue_number']):
        raise RuntimeError('Not the accepted fixture issue')
    state = ROOT / 'evidence' / 'motor-probe' / workspace.name
    state.mkdir(parents=True, exist_ok=True)
    # Durable one-attempt marker: unchanged retries never invoke a model again.
    with (state / 'launch.json').open('x') as f:
        json.dump({'workspace': str(workspace), 'pid': os.getpid(),
                   'started_at_epoch': time.time(), 'attempt': 1}, f)
    command = [str(ROOT / '.runtime/bin/codex-0.155.1'),
               '-c', 'model="gpt-6-astra"', '-c', 'approval_policy="never"',
               '-c', 'model_reasoning_effort="high"']
    # Retain auth and safety rules, but do not give fixture workers desktop/app MCPs.
    config = (Path.home() / '.codex/config.toml').read_text()
    for name in re.findall(r'^\[mcp_servers\.([\w-]+)\]$', config, re.M):
        command += ['-c', 'mcp_servers.' + name + '.enabled=false']
    for name in re.findall(r'^\[plugins\."([^"\n]+)"\]$', config, re.M):
        command += ['-c', 'plugins.' + json.dumps(name) + '.enabled=false']
    command += ['app-server']
    environment = dict(os.environ)
    for key in list(environment):
        if key in ('GITHUB_TOKEN', 'GH_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'GH_ENTERPRISE_TOKEN',
                   'OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY'):
            environment.pop(key)
    with (state / 'app-server.stderr').open('wb') as err, (state / 'protocol.jsonl').open('a', buffering=1) as trace:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=err, env=environment)
        sel = selectors.DefaultSelector()
        sel.register(sys.stdin.buffer, selectors.EVENT_READ, 'to_codex')
        sel.register(proc.stdout, selectors.EVENT_READ, 'from_codex')
        buffers = {'to_codex': b'', 'from_codex': b''}
        started = time.monotonic()
        try:
            while time.monotonic() - started < 180:
                for key, _ in sel.select(timeout=1):
                    direction = key.data
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        return 0 if proc.poll() in (None, 0) else proc.returncode
                    buffers[direction] += chunk
                    while b'\n' in buffers[direction]:
                        line, buffers[direction] = buffers[direction].split(b'\n', 1)
                        if not line.strip():
                            continue
                        message = json.loads(line)
                        if direction == 'to_codex':
                            message = restrict_message(message, workspace)
                        trace.write(json.dumps({'time': time.time(), 'direction': direction, 'message': message}) + '\n')
                        target = proc.stdin if direction == 'to_codex' else sys.stdout.buffer
                        target.write(json.dumps(message).encode() + b'\n')
                        target.flush()
            return 124
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            sel.close()


if __name__ == '__main__':
    raise SystemExit(main())
