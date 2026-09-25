"""One bounded provider process, no retry loop. Host evidence stays outside candidate."""
import fcntl
import hashlib
import select
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.bounded import stop_group
from .profile import ROOT, command, environment, selected_model as codex_model
from .task import load, task_directory, evidence_directory
from .targets import OFFICE
from .provider_result import parse as parse_provider
from .claude_profile import command as claude_command, require_subscription, selected_model
from .review import strict_object
from .development_binding import reserve_task_call, REVIEW_BUDGET_SECONDS
from .development_scope import ScopeClosed


def transfer(proc, payload, command, seconds, started, control=None):
    """Deliver the whole prompt, close stdin, then wait - all inside the run's OWN bound and stop check.

    Measured on the live application 2026-09-22 and reproduced without a model: subprocess.communicate(input,
    timeout) abandons a partially written input when its timeout fires, and never closes stdin. A child that is
    slow to start reading therefore receives nothing, emits nothing, and is killed at the deadline with an empty
    event stream - which is exactly what both review runs of ap11-step-5 did, at 182.2 s and again at 302.0 s under
    a raised bound. CPython issue 141473 describes the same mechanism; the local reproduction is what this is fixed
    against, and neither is taken as proof that this correction works - the tests exercise this function itself.

    The transfer must stay bounded and stoppable: it is NOT replaced by a blocking write, which could hang before
    any control check ran. One non-blocking write per pass, the scope control re-read every pass, the run's own
    deadline enforced every pass, and process cleanup left to the caller.
    """
    pending = memoryview(payload)
    descriptor = proc.stdin.fileno()
    os.set_blocking(descriptor, False)

    def sent():
        try:
            proc.stdin.close()
        except InterruptedError:
            raise                       # a stop signal is never swallowed by the close (BrokenPipeError is an OSError)
        except OSError:
            pass

    while True:
        if control is not None:
            state = control()
            if state not in ('active', 'paused'):
                raise ScopeClosed('Active scoped process stopped: ' + state)
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, seconds)
        if pending is not None:
            # A child that ended before taking the whole prompt surfaces as BrokenPipeError on the next write IF
            # nothing else holds the read end. Where a descendant inherited it and never reads, the run instead meets
            # its own deadline below - bounded and stoppable either way, and the same as the plain path has always
            # behaved. Measured by review N.
            ready = select.select([], [descriptor], [], min(1, remaining))[1]
            if ready:
                try:
                    pending = pending[os.write(descriptor, pending):]
                except BlockingIOError:
                    continue
                except BrokenPipeError:
                    sent(); pending = None
                    continue
                if not len(pending):
                    sent(); pending = None
            continue
        try:
            proc.wait(timeout=min(1, remaining))
            return
        except subprocess.TimeoutExpired:
            pass


def execute(task_id, number, prompt, seconds, change_reason=None, task_digest=None, role="implementation", workspace_name=None, provider="codex", binding=None):
    task = load(task_id, task_digest)
    if type(number) is not int or number < 1 or (number > 1 and not change_reason):
        raise ValueError('Explicit attempt and changed prerequisite required')
    # A bound review (it carries its budget in its binding) is bounded by the review frame, 180..900 s, not by the
    # implementation's time. Every other call keeps its former ceiling, the accepted attempt time.
    ceiling = (REVIEW_BUDGET_SECONDS[1] if role == 'review' and binding is not None and not task.get('development')
               else task['attempt_seconds'])
    if role not in ('implementation', 'review') or not 1 <= seconds <= ceiling:
        raise ValueError('Invalid role or invocation limit')
    if binding is not None and (role != 'review' or not isinstance(binding, dict) or binding.get('review_seconds') != seconds):
        raise ValueError('A review binding belongs to a review with exactly its budget')
    # The executor is the accepted task's explicit choice for this role. A caller
    # cannot substitute another one; an absent reviewer choice is original Codex.
    accepted = ({task.get('review_provider', 'codex')} if role == 'review'
                else {step.get('provider') for step in task['steps']})
    if provider not in ('codex','claude') or provider not in accepted:
        raise ValueError('Unqualified provider/role')
    model = None
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
            if os.environ.get('NR_CONFIG_SHA256'):
                from .release import require_active_code, require_workspace_instructions
                if provider == 'claude':
                    # Same order as the Codex profile: a changed bound input stops BEFORE a model call.
                    require_workspace_instructions(workspace)
                # The release's explicit model choice, for whichever executor runs (D022, D028). Resolved in
                # the same handler as the other preflight refusals so a release transition, a drifted
                # baseline or a misspelt key is reported as a diagnosable preflight failure instead of an
                # uncaught crash that leaves no result at all. ScopeClosed is a ValueError, so it lands here too.
                from .development_model import models
                model = models(require_active_code())[provider]
            # A Claude reviewer receives the read-only profile: no edit tool and no file grant.
            argv = claude_command(workspace, task['allowed_paths'], writable=role == 'implementation', model=model) if provider == 'claude' else command(workspace, writable=role == 'implementation', allowed_paths=task['allowed_paths'] if task['target'] == OFFICE else None, model=model)
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
        if binding is not None:
            record['binding'] = binding       # the accepted and the used Runtime revision and the budget of this review
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
                # One delivery path for both: the scope-reserved run re-reads its control every pass, the plain
                # run has none to read, and neither can lose part of the prompt or leave stdin open.
                transfer(proc, prompt.encode(), record['command'], seconds, started,
                         control=(lambda: reservation[0].inspect()['control']) if reservation else None)
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
        parsed = parse_provider(provider, records, role, model=model)
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
                  # Which model this run was started as. A release that changes only the selection keeps
                  # the same runtime_revision, so the revision no longer implies the model and the record
                  # has to say it. parse contributes the identity the provider itself reported.
                  'model': selected_model(model) if provider == 'claude' else codex_model(model),
                  'provider_completed': finished, 'exit_code': code,
                  **parsed, 'role': role,
                  'model_started': proc is not None,
                  'scope_reservation': reservation[1] if reservation else None,
                  'interrupted': interrupted, 'process_group_removed': removed,
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'evidence': str(output.relative_to(ROOT))}
        if binding is not None:
            report['binding'] = binding
        if not finished and not parse_error:
            # A failed run whose provider said it has no capacity: the owner is asked which way to go (D030), after the
            # run's own record is complete. The run stays a failure awaiting diagnosis exactly as before, nothing is
            # switched, and nothing here can keep its result from being written.
            try:
                from .development_model import capacity_lost
                from .model_question import ask_safely
                if capacity_lost(provider, records):
                    report['model_question'] = ask_safely(provider, report['model'], records,
                                                          {'kind': 'task attempt', 'task': task_id, 'attempt': number, 'role': role})
            except Exception as error:
                report['model_question'] = 'not written: %r' % error
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        return 0 if finished else 1


if __name__ == '__main__':
    request = json.load(sys.stdin)
    raise SystemExit(execute(**request))
