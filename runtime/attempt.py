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


def execute(task_id, number, prompt, seconds, change_reason=None, task_digest=None, role="implementation", workspace_name=None):
    task = load(task_id, task_digest)
    if type(number) is not int or number < 1 or (number > 1 and not change_reason):
        raise ValueError('Explicit attempt and changed prerequisite required')
    if role not in ('implementation', 'review') or not 1 <= seconds <= task['attempt_seconds']:
        raise ValueError('Invalid role or invocation limit')
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
        record = {'task': task_id, 'attempt': number, 'provider': 'codex',
                  'executor_pid': os.getpid(), 'started_epoch': time.time(),
                  'seconds_limit': seconds, 'automatic_retries': 0,
                  'command': command(workspace, writable=role == 'implementation'), 'workspace': str(workspace),
                  'role': role, 'task_sha256': task_digest,
                  'change_reason': change_reason,
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        if role == 'review':
            record['command'] = record['command'][:-1] + ['--output-schema', str(workspace / 'REVIEW_SCHEMA.json'), '-']
        (output / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')
        started = time.monotonic()
        proc = None
        interrupted = None
        def stop(sig, frame):
            raise InterruptedError(sig)
        old = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            with (output / 'events.jsonl').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
                proc = subprocess.Popen(record['command'], cwd=workspace, env=environment(),
                                        stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                        start_new_session=True)
                record['provider_pid'] = proc.pid
                (output / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')
                proc.communicate(prompt.encode(), timeout=seconds)
                code = proc.returncode
        except subprocess.TimeoutExpired:
            code, interrupted = 124, 'deadline'
        except InterruptedError:
            code, interrupted = 130, 'signal'
        finally:
            for sig in old:
                signal.signal(sig, signal.SIG_IGN)
            removed = proc is None or stop_group(proc)
            for sig, handler in old.items():
                signal.signal(sig, handler)
        records, parse_error = [], False
        for line in (output / 'events.jsonl').read_text().splitlines():
            try:
                event = json.loads(line)
                if not isinstance(event, dict): raise ValueError('Non-object event')
                records.append(event)
            except ValueError:
                parse_error = True
        threads = [x.get('thread_id') for x in records if x.get('type') == 'thread.started']
        terminals = [x for x in records if x.get('type') in ('turn.completed', 'turn.failed')]
        errors = [x for x in records if x.get('type') in ('error', 'turn.failed')]
        finished = (code == 0 and removed and not interrupted and not parse_error and not errors
                    and len(terminals) == 1 and terminals[0]['type'] == 'turn.completed'
                    and len(threads) == 1 and isinstance(threads[0], str) and bool(threads[0]))
        report = {'task': task_id, 'attempt': number, 'provider': 'codex',
                  'provider_completed': finished, 'exit_code': code,
                  'thread_id': threads[0] if len(threads) == 1 else None, 'role': role,
                  'interrupted': interrupted, 'process_group_removed': removed,
                  'usage': terminals[-1].get('usage') if terminals else None,
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'evidence': str(output.relative_to(ROOT))}
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        return 0 if finished else 1


if __name__ == '__main__':
    request = json.load(sys.stdin)
    raise SystemExit(execute(**request))
