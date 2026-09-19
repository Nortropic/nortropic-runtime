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
        proc = subprocess.Popen(command, cwd=args.cwd, stdout=out, stderr=err, start_new_session=True)
        record['pid'] = proc.pid
        (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
        try:
            rc = proc.wait(timeout=args.seconds)
            record['timed_out'] = False
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            record['timed_out'] = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            rc = 124
        finally:
            # End descendants still holding this experiment's process group.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    record.update(exit_code=rc, elapsed_seconds=round(time.monotonic() - start, 3),
                  finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (args.output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
