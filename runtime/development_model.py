"""One read-only native agent call for the activated finite development goal.

No task generation is executed here. Structured answers are untrusted data for
the frozen Office policy and independent review. No retry loop or new provider.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from .development_scope import Scope, ScopeClosed, identifier, decode
from .release import ROOT, require_active_code, require_workspace_instructions
from .profile import command, environment
from .provider_result import parse
from .private_stage import stop_private_group, write
from .shared import process_identity
from .snapshot import read_regular


def active_scope(expected):
    config = require_active_code()
    selected = config.get('development')
    if (not isinstance(selected, dict) or selected.get('id') != 'office-ap11'
            or selected.get('contract_sha256') != expected):
        raise ScopeClosed('Finite goal has no matching explicit activation')
    return Scope(ROOT / '.runtime/ap11/application', expected), config


def execute(request):
    os.umask(0o077)
    scope, config = active_scope(request['contract_sha256'])
    nonce = identifier(request['nonce'])
    stage = scope.directory / 'calls' / nonce
    raw = read_regular(stage, 'input.json')
    if hashlib.sha256(raw).hexdigest() != request['input_sha256']:
        raise ScopeClosed('Prepared call input changed')
    data = decode(raw)
    if (set(data) != {'prompt', 'schema', 'work', 'role', 'seconds', 'workspace_sha256'}
            or data['role'] not in ('driver', 'preparation-review', 'diagnosis', 'final-review')
            or type(data['seconds']) is not int or not 1 <= data['seconds'] <= 480):
        raise ScopeClosed('Only bounded read-only goal roles are supported')
    workspace = stage / 'workspace'
    if not isinstance(data['workspace_sha256'], dict) or not data['workspace_sha256']:
        raise ScopeClosed('Actual delivered context must be bound')
    for name, expected in data['workspace_sha256'].items():
        if hashlib.sha256(read_regular(workspace, name)).hexdigest() != expected:
            raise ScopeClosed('Actual delivered context changed')
    if decode(read_regular(workspace, 'OUTPUT_SCHEMA.json')) != data['schema']:
        raise ScopeClosed('Selected role schema differs from actual delivered schema')
    # Exclusive consumed receipt, before reservation, so native redelivery cannot
    # replay the same call even if it never reached Popen. Diagnose explicitly.
    write(stage / 'consumed.json', {'nonce': nonce, 'input_sha256': request['input_sha256']})
    argv = command(workspace, writable=False)
    argv = argv[:-1] + ['--output-schema', str(workspace / 'OUTPUT_SCHEMA.json'), '-']
    parent = os.getppid()
    parent_identity = process_identity(parent)
    record = {'role': data['role'], 'nonce': nonce, 'parent_pid': parent,
              'parent_identity': parent_identity, 'started_epoch': time.time(),
              'seconds_limit': data['seconds'], 'input_sha256': request['input_sha256']}
    write(stage / 'prompt.json', {'prompt': data['prompt'], 'schema': data['schema']})
    prompt_file = stage / 'stdin.txt'
    with prompt_file.open('x') as stream:
        stream.write(data['prompt'])
    proc = None; reason = None; removed = False; start = time.monotonic()
    def interrupted(sig, frame):
        raise InterruptedError('goal call signal')
    old = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with (stage/'events.jsonl').open('xb') as out, (stage/'stderr.log').open('xb') as err, \
                prompt_file.open('rb') as inp, selectors.DefaultSelector() as streams:
            scope.reserve(data['work'], data['role'], nonce)
            def launch():
                nonlocal proc
                proc = subprocess.Popen(argv, cwd=workspace, env=environment(), stdin=inp,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                record.update(provider_pid=proc.pid, provider_identity=process_identity(proc.pid))
                write(stage / 'launch.json', record)
                return proc
            scope.launch(nonce, launch)
            for source, target in ((proc.stdout, out), (proc.stderr, err)):
                os.set_blocking(source.fileno(), False)
                streams.register(source, selectors.EVENT_READ, target)
            while streams.get_map() or proc.poll() is None:
                if os.getppid() != parent or process_identity(parent) != parent_identity:
                    raise InterruptedError('call owner ended')
                if scope.inspect()['control'] not in ('active', 'paused'):
                    raise ScopeClosed('Finite goal stopped during call')
                if time.monotonic() - start >= data['seconds']:
                    raise TimeoutError('bounded model call ended')
                for key, _ in streams.select(.25):
                    content = os.read(key.fileobj.fileno(), 65536)
                    if not content:
                        streams.unregister(key.fileobj); key.fileobj.close(); continue
                    target = key.data
                    remaining = 1024*1024 - target.tell()
                    target.write(content[:remaining]); target.flush()
                    if len(content) > remaining:
                        raise ValueError('model output bound exceeded')
    except (OSError, ValueError, TimeoutError, InterruptedError) as error:
        reason = str(error)
    finally:
        for sig in old:
            signal.signal(sig, signal.SIG_IGN)
        try:
            removed = proc is None or stop_private_group(proc)
        finally:
            if proc is not None:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
            for sig, handler in old.items():
                signal.signal(sig, handler)
    records = []; parsed = {}; answer = None
    try:
        records = [decode(line) for line in read_regular(stage, 'events.jsonl', limit=1024*1024).splitlines()]
        parsed = parse('codex', records)
        if not parsed.get('valid_terminal'):
            reason = reason or 'No valid native provider terminal'
        messages = [e.get('item', {}).get('text') for e in records
                    if e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'agent_message']
        answer = decode(messages[-1])
        require_workspace_instructions(workspace)
        for name, expected in data['workspace_sha256'].items():
            if hashlib.sha256(read_regular(workspace, name)).hexdigest() != expected:
                raise ScopeClosed('Delivered context changed during call')
    except (OSError, ValueError, TypeError, IndexError, KeyError) as error:
        reason = reason or str(error)
    # Only provider error events can trigger this classification; agent text is
    # never authority to change control. Unknown failure remains inconclusive.
    errors = json.dumps([e for e in records if e.get('type') in ('error', 'turn.failed')]).lower()
    if any(word in errors for word in ('usage limit', 'quota', 'rate limit', 'rate_limit', 'unauthorized', 'authentication')):
        if scope.inspect()['control'] in ('active', 'paused'):
            scope.control('quota', 'Native provider reported quota/access failure; preserve original events')
    result = {'completed': reason is None and proc is not None and proc.returncode == 0 and removed,
              'reason': reason, 'answer': answer, 'provider': parsed,
              'process_group_removed': removed, 'model_started': proc is not None,
              'elapsed_seconds': round(time.monotonic()-start, 3), 'nonce': nonce}
    write(stage / 'result.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(execute(json.load(sys.stdin))))
