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


def stop_group(proc):
    """Stop our process group, including children after the leader has exited.

    Children that deliberately leave the group are outside this helper's scope.
    SIGKILL of the helper cannot be caught; recovery must inspect recorded PIDs.
    """
    def exists():
        proc.poll()  # Reap the leader even while other group members survive.
        try:
            os.killpg(proc.pid, 0)
            return True
        except ProcessLookupError:
            return False

    for sig, grace in ((signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        if not exists():
            return True
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return True
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
        def handle_stop(signum, _frame):
            raise StopRequested(signum)
        old_handlers = {sig: signal.signal(sig, handle_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        proc = subprocess.Popen(command, cwd=args.cwd, stdout=out, stderr=err, start_new_session=True)
        record['pid'] = proc.pid
        (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
        try:
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
            record['process_group_removed'] = stop_group(proc)
            if not record['process_group_removed']:
                rc = 125
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
    record.update(exit_code=rc, elapsed_seconds=round(time.monotonic() - start, 3),
                  finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
