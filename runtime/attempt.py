"""One bounded provider process, no retry loop. Host evidence stays outside candidate."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.bounded import stop_group
from .profile import ROOT, command, environment
from .task import load, task_directory, evidence_directory
from .targets import OFFICE
from .provider_result import parse as parse_provider
from .claude_profile import command as claude_command, require_subscription
from .review import strict_object
from .development_binding import reserve_task_call
from .development_scope import ScopeClosed


def execute(task_id, number, prompt, seconds, change_reason=None, task_digest=None, role="implementation", workspace_name=None, provider="codex"):
    task = load(task_id, task_digest)
    if type(number) is not int or number < 1 or (number > 1 and not change_reason):
        raise ValueError('Explicit attempt and changed prerequisite required')
    if role not in ('implementation', 'review') or not 1 <= seconds <= task['attempt_seconds']:
        raise ValueError('Invalid role or invocation limit')
    # The executor is the accepted task's explicit choice for this role. A caller
    # cannot substitute another one; an absent reviewer choice is original Codex.
    accepted = ({task.get('review_provider', 'codex')} if role == 'review'
                else {step.get('provider') for step in task['steps']})
    if provider not in ('codex','claude') or provider not in accepted:
        raise ValueError('Unqualified provider/role')
    state = task_directory(task_id)
    if role == 'review':
        if not isinstance(workspace_name, str) or not workspace_name.startswith('commit-') or not workspace_name[7:].isdigit():
            raise ValueError('Review must use a host-prepared immutable candidate')
        workspace = state / workspace_name
    else:
        workspace = state / 'candidate'
    output = evidence_directory(task_id) / (('review-' if role == 'review' else 'attempt-') + str(number))
    # A launch marker is not an approval; an interrupted launch requires diagnosis.
    with (state / 'writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(exist_ok=False)
        try:
            subscription = require_subscription() if provider == 'claude' else None
            if provider == 'claude' and os.environ.get('NR_CONFIG_SHA256'):
                # Same order as the Codex profile: a changed bound input stops BEFORE a model call.
                from .release import require_workspace_instructions
                require_workspace_instructions(workspace)
            # A Claude reviewer receives the read-only profile: no edit tool and no file grant.
            argv = claude_command(workspace, task['allowed_paths'], writable=role == 'implementation') if provider == 'claude' else command(workspace, writable=role == 'implementation', allowed_paths=task['allowed_paths'] if task['target'] == OFFICE else None)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            report = {'task':task_id,'attempt':number,'provider':provider,'provider_completed':False,
                      'reason':'Provider preflight failed: '+str(error),'process_group_removed':True,
                      'model_started':False,'evidence':str(output.relative_to(ROOT))}
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report))
            return 1
        record = {'task': task_id, 'attempt': number, 'provider': provider,
                  'executor_pid': os.getpid(), 'started_epoch': time.time(),
                  'seconds_limit': seconds, 'automatic_retries': 0,
                  'command': argv, 'workspace': str(workspace), 'subscription': subscription,
                  'role': role, 'task_sha256': task_digest,
                  'change_reason': change_reason,
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        if role == 'review' and provider == 'claude':
            # Host-written schema; the native CLI refuses invalid JSON before any model call.
            record['command'] = record['command'] + ['--json-schema', (workspace / 'REVIEW_SCHEMA.json').read_text()]
        elif role == 'review':
            record['command'] = record['command'][:-1] + ['--output-schema', str(workspace / 'REVIEW_SCHEMA.json'), '-']
        (output / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')
        started = time.monotonic()
        proc = None
        interrupted = None
        reservation = None
        def stop(sig, frame):
            raise InterruptedError(sig)
        old = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            with (output / 'events.jsonl').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
                def launch():
                    # Retain ownership BEFORE Scope records success. An append/
                    # disk failure after Popen must still clean up this process.
                    nonlocal proc
                    proc = subprocess.Popen(record['command'], cwd=workspace, env=environment(),
                                            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                            start_new_session=True)
                    record['provider_pid'] = proc.pid
                    (output / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')
                    return proc
                reservation = reserve_task_call(task, role, number)
                if reservation:
                    reservation[0].launch(reservation[1], launch)
                else:
                    launch()
                if reservation:
                    first_input = prompt.encode()
                    while True:
                        control = reservation[0].inspect()['control']
                        if control not in ('active', 'paused'):
                            raise ScopeClosed('Active scoped process stopped: ' + control)
                        remaining = seconds - (time.monotonic() - started)
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(record['command'], seconds)
                        try:
                            proc.communicate(first_input, timeout=min(1, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            first_input = None
                else:
                    proc.communicate(prompt.encode(), timeout=seconds)
                code = proc.returncode
        except subprocess.TimeoutExpired:
            code, interrupted = 124, 'deadline'
        except InterruptedError:
            code, interrupted = 130, 'signal'
        except (ScopeClosed, OSError) as error:
            code, interrupted = 125, str(error)
        finally:
            for sig in old:
                signal.signal(sig, signal.SIG_IGN)
            if reservation:
                # Reuse the qualified macOS EPERM readback: a reaped leader
                # AND an absent OS process group, never EPERM alone as success.
                from .private_stage import stop_private_group
                removed = proc is None or stop_private_group(proc)
            else:
                removed = proc is None or stop_group(proc)
            for sig, handler in old.items():
                signal.signal(sig, handler)
        records, parse_error = [], False
        for line in (output / 'events.jsonl').read_text().splitlines():
            try:
                event = json.loads(line, object_pairs_hook=strict_object) if provider == 'claude' else json.loads(line)
                if not isinstance(event, dict): raise ValueError('Non-object event')
                records.append(event)
            except ValueError:
                parse_error = True
        parsed = parse_provider(provider, records, role)
        valid_terminal = parsed.pop('valid_terminal')
        finished = (code == 0 and removed and not interrupted and not parse_error and valid_terminal)
        if os.environ.get('NR_CONFIG_SHA256'):
            from .release import require_workspace_instructions
            try:
                require_workspace_instructions(workspace)
            except (OSError, ValueError):
                finished = False
                interrupted = 'active instruction/configuration binding changed'
        report = {'task': task_id, 'attempt': number, 'provider': provider,
                  'provider_completed': finished, 'exit_code': code,
                  **parsed, 'role': role,
                  'model_started': proc is not None,
                  'scope_reservation': reservation[1] if reservation else None,
                  'interrupted': interrupted, 'process_group_removed': removed,
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'evidence': str(output.relative_to(ROOT))}
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        return 0 if finished else 1


if __name__ == '__main__':
    request = json.load(sys.stdin)
    raise SystemExit(execute(**request))
