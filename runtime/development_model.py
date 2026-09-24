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
from .profile import command, environment, MODEL as CODEX_MODEL
from .claude_profile import command as claude_command, require_subscription, MODEL as CLAUDE_MODEL, MODEL_NAME
from .provider_result import parse
from .model_question import ask_safely
from .review import claude_response
from .private_stage import stop_private_group, write
from .shared import process_identity
from .snapshot import read_regular


ROLES = ('interactive', 'driver', 'preparation-review', 'diagnosis', 'final-review', 'implementation', 'review')
EXECUTORS = ('codex', 'claude')
QUOTA_WORDS = ('usage limit', 'quota', 'rate limit', 'rate_limit', 'unauthorized', 'authentication')
CLAUDE_QUOTA_WORDS = QUOTA_WORDS + ('session limit',)


def executors(config):
    """Explicit frozen per-role executor choice; absent is the original Codex route.

    Never a fallback: quota or access loss stays a persisted wait. The selection is
    part of the frozen release configuration and changes only through a separately
    reviewed controlled release transition.
    """
    development = config.get('development') or {}
    # A misspelt selection must not silently become the Codex default.
    if 'executors' in config or 'executor' in config or not isinstance(development, dict) or 'executor' in development:
        raise ScopeClosed('Invalid explicit executor selection')
    chosen = development.get('executors', {})
    if (not isinstance(chosen, dict) or set(chosen) - set(ROLES)
            or any(value not in ('codex', 'claude') for value in chosen.values())):
        raise ScopeClosed('Invalid explicit executor selection')
    return {role: chosen.get(role, 'codex') for role in ROLES}


def models(config):
    """Explicit frozen per-executor model choice; absent is each profile's own qualified model.

    Mirrors executors(): part of the frozen release configuration, changed only through a separately
    reviewed controlled release transition, and never a fallback. A misspelt key must not silently
    run a different model than the chosen one, so an unknown key refuses instead of defaulting.

    The choice is per executor, not per role: the owner makes one collected choice for the mission
    and the host applies it to every role that executor drives. A name that could be read as a flag
    is refused here rather than reaching an argument list.
    """
    development = config.get('development') or {}
    if 'models' in config or 'model' in config or not isinstance(development, dict) or 'model' in development:
        raise ScopeClosed('Invalid explicit model selection')
    chosen = development.get('models', {})
    # The same rule the profile applies, so a name cannot pass one validator and fail the other.
    if (not isinstance(chosen, dict) or set(chosen) - set(EXECUTORS)
            or any(not isinstance(value, str) or not MODEL_NAME.match(value)
                   for value in chosen.values())):
        raise ScopeClosed('Invalid explicit model selection')
    # Both routes read their model from here. The Codex startup chain takes the chosen name as its one model
    # argument (D028); until then a different Codex value was refused, because it would have been configured
    # and then not run.
    return {'claude': chosen.get('claude', CLAUDE_MODEL), 'codex': chosen.get('codex', CODEX_MODEL)}


def capacity_lost(provider, records):
    """Quota or access loss, from the provider's own terminal or error rows only; agent text is never authority."""
    if provider == 'claude':
        return claude_unavailable(records)
    errors = json.dumps([e for e in records if e.get('type') in ('error', 'turn.failed')]).lower()
    return any(word in errors for word in QUOTA_WORDS)


def claude_unavailable(records):
    """Quota/access only from a failed terminal's own status or error text (measured shape).

    Usage counters, tool inventories and agent output in the same row are never read.
    """
    failed = [e for e in records if e.get('type') == 'result' and e.get('is_error') is not False]
    return any(e.get('api_error_status') in (401, 403, 429)
               or any(word in str(e.get('result') or '').lower() for word in CLAUDE_QUOTA_WORDS) for e in failed)


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
    # Validated BEFORE the exclusive consumed receipt: the receipt cannot be rewritten and the stage
    # directory cannot be re-made, so a selection that refuses after it would strand this prepared call
    # on a key that can never be delivered again.
    chosen = models(config)
    write(stage / 'consumed.json', {'nonce': nonce, 'input_sha256': request['input_sha256']})
    provider = executors(config)[data['role']]
    selected = chosen[provider]
    if provider == 'claude':
        # Same order as the Codex profile: bound inputs and the qualified subscription
        # route are checked before any model could start. Read-only, no file grant.
        require_subscription(); require_workspace_instructions(workspace)
        argv = claude_command(workspace, (), writable=False, model=selected) + ['--json-schema', json.dumps(data['schema'])]
    else:
        argv = command(workspace, writable=False, model=selected)
        argv = argv[:-1] + ['--output-schema', str(workspace / 'OUTPUT_SCHEMA.json'), '-']
    parent = os.getppid()
    parent_identity = process_identity(parent)
    record = {'role': data['role'], 'nonce': nonce, 'provider': provider, 'parent_pid': parent,
              'parent_identity': parent_identity, 'started_epoch': time.time(),
              'seconds_limit': data['seconds'], 'input_sha256': request['input_sha256']}
    write(stage / 'prompt.json', {'prompt': data['prompt'], 'schema': data['schema']})
    prompt_file = stage / 'stdin.txt'
    with prompt_file.open('x') as stream:
        stream.write(data['prompt'])
    proc = None; reason = None; removed = False; start = time.monotonic(); signalled = []
    def interrupted(sig, frame):
        # Recorded here and acted on by the loop, never raised from the handler (D026). The loop waits almost all the
        # time inside streams.select(), and the standard selectors catch InterruptedError and return no events, so a
        # handler that raised it was swallowed there and the call ran on to its end as if nothing had been sent.
        signalled.append(sig)
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
                if signalled:
                    raise InterruptedError('goal call signal')
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
        if not all(isinstance(e, dict) for e in records):
            records = []
            raise ValueError('Native provider event is not an object')
        parsed = parse('claude', records, 'structured', model=selected) if provider == 'claude' else parse('codex', records)
        if not parsed.get('valid_terminal'):
            reason = reason or 'No valid native provider terminal'
        if provider == 'claude':
            # Only the single valid terminal's strictly repeated structured object is an answer.
            answer = claude_response(records)
        else:
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
    capacity = capacity_lost(provider, records)
    if capacity:
        if scope.inspect()['control'] in ('active', 'paused'):
            scope.control('quota', 'Native provider reported quota/access failure; preserve original events')
    result = {'completed': reason is None and proc is not None and proc.returncode == 0 and removed,
              'reason': reason, 'answer': answer, 'provider': parsed,
              'process_group_removed': removed, 'model_started': proc is not None,
              'elapsed_seconds': round(time.monotonic()-start, 3), 'nonce': nonce}
    if capacity:
        # The wait persists as before; the owner is asked which way to go (D030), after the call's own record is complete.
        # Nothing is switched, and ask_safely records a question it cannot write instead of raising.
        result['model_question'] = ask_safely(provider, selected, records, {'kind': 'goal call', 'role': data['role'], 'nonce': nonce})
    write(stage / 'result.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(execute(json.load(sys.stdin))))
