#!/usr/bin/env python3
"""Bound an operator-invoked experiment; preserve raw stdout/stderr and metadata.

Not a Runtime scheduler. No automatic retries. Never pass secrets as arguments.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import time


class StopRequested(Exception):
    def __init__(self, signum):
        self.signum = signum


def stop_group(proc, term_grace=2, kill_grace=2):
    """Stop our process group, including children after the leader has exited.

    Children that deliberately leave the group are outside this helper's scope.
    SIGKILL of the helper cannot be caught; recovery must inspect recorded PIDs.
    """
    def absent_after_eperm():
        # EPERM alone is not evidence of exit. Reap our leader first, then
        # require an independent readable OS listing with no group member.
        if proc.poll() is None:return False
        try:
            result = subprocess.run(['ps', '-axo', 'pgid=,stat='], capture_output=True,
                                    timeout=1, env={'PATH':'/usr/bin:/bin', 'LC_ALL':'C'})
            if result.returncode:return False
            rows = result.stdout.decode('ascii').splitlines()
            if not rows:return False
            for row in rows:
                fields = row.split()
                if len(fields) != 2 or not fields[0].isdigit():return False
                if int(fields[0]) == proc.pid:return False
            return True
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            return False

    def exists():
        proc.poll()
        try:
            os.killpg(proc.pid, 0)
            return True
        except ProcessLookupError:
            return proc.poll() is None
        except PermissionError:
            return not absent_after_eperm()

    for sig, grace in ((signal.SIGTERM, term_grace), (signal.SIGKILL, kill_grace)):
        if not exists():
            return True
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            # Still verify and reap below; a failed signal never proves exit.
            pass
        end = time.monotonic() + grace
        while time.monotonic() < end:
            if not exists():
                return True
            time.sleep(0.05)
    return not exists()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seconds', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cwd', type=Path, default=Path.cwd())
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or not 1 <= args.seconds <= 3600:
        p.error('command and 1..3600 seconds required')
    args.output.mkdir(parents=True, exist_ok=False)
    record = {'command': command, 'cwd': str(args.cwd.resolve()),
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'limit_seconds': args.seconds, 'automatic_retries': 0}
    start = time.monotonic()
    with (args.output / 'stdout.log').open('wb') as out, (args.output / 'stderr.log').open('wb') as err:
        starting = True
        pending_stop = None
        def handle_stop(signum, _frame):
            nonlocal pending_stop
            if starting:
                pending_stop = signum
                return
            raise StopRequested(signum)
        old_handlers = {sig: signal.signal(sig, handle_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        proc = None
        rc = 125
        try:
            # Record a stop during Popen, then raise after ownership is stored.
            # A POSIX signal mask would be inherited by the child and prevent
            # its normal SIGTERM handling; this deferral only affects us.
            proc = subprocess.Popen(command, cwd=args.cwd, stdout=out, stderr=err, start_new_session=True)
            starting = False
            if pending_stop is not None:
                raise StopRequested(pending_stop)
            record['pid'] = proc.pid
            (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
            rc = proc.wait(timeout=args.seconds)
            record['timed_out'] = False
        except subprocess.TimeoutExpired:
            record['timed_out'] = True
            rc = 124
        except StopRequested as stop:
            record.update(timed_out=False, interrupted_by=stop.signum)
            rc = 128 + stop.signum
        finally:
            for sig in old_handlers:
                signal.signal(sig, signal.SIG_IGN)
            try:
                if proc is not None:
                    record.setdefault('pid', proc.pid)
                record['process_group_removed'] = proc is None or stop_group(proc)
                if not record['process_group_removed']:
                    rc = 125
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
    record.update(exit_code=rc, elapsed_seconds=round(time.monotonic() - start, 3),
                  finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
