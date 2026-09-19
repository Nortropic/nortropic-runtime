#!/usr/bin/env python3
"""Fresh app-server thread/tool inventory; deliberately no model turn."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.profile import ROOT, permissions
from scripts.probe_bridge import worker_command


def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise RuntimeError('Preserve previous evidence')
    workspace = ROOT / '.runtime/boundary-candidate'
    command = worker_command()[:-1] + permissions(workspace) + ['app-server']
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, cwd=workspace)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    records, buffer, response = [], b'', None
    def send(message):
        records.append({'direction': 'request', 'message': message})
        proc.stdin.write(json.dumps(message).encode() + b'\n')
        proc.stdin.flush()
    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'nr-profile-preflight', 'version': '0.1'},
            'capabilities': {'experimentalApi': True}}})
        end = time.monotonic() + 30
        while time.monotonic() < end and response is None:
            if not selector.select(1):
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                records.append({'direction': 'response', 'message': message})
                if message.get('id') == 1:
                    send({'method': 'initialized', 'params': {}})
                    send({'id': 2, 'method': 'thread/start', 'params': {
                        'cwd': str(workspace), 'model': 'gpt-6-astra',
                        'approvalPolicy': 'never', 'dynamicTools': []}})
                elif message.get('id') == 2 and 'result' in message:
                    send({'id': 3, 'method': 'mcpServerStatus/list', 'params': {
                        'threadId': message['result']['thread']['id'], 'detail': 'full'}})
                elif message.get('id') == 3:
                    response = message
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        selector.close()
    result = (response or {}).get('result', {})
    passed = (isinstance(result.get('data'), list) and not result.get('nextCursor')
              and all(x.get('runtimeStatus') == 'disabled' and not x.get('tools') for x in result['data']))
    output.write_text(json.dumps({'command': command, 'model_turns': 0,
                                 'passed': passed, 'records': records}, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'servers': [
        {'name': s['name'], 'status': s['runtimeStatus'], 'tools': len(s.get('tools', {}))}
        for s in result.get('data', [])]}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
