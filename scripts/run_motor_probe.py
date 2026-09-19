#!/usr/bin/env python3
"""Run one bounded experiment with upstream Symphony; no retry/scheduling loop."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from bounded import StopRequested, stop_group

ROOT = Path(__file__).resolve().parents[1]


def main():
    contract = json.loads((ROOT / 'config/motor-probe.json').read_text())
    if not contract.get('execution_enabled', False):
        raise RuntimeError('Fixture profile is disabled pending verified authorization')
    output = ROOT / 'evidence/motor-probe/engine'
    output.mkdir(parents=True, exist_ok=False)
    with (ROOT / '.runtime/engine.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        auth = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=15, check=True)
        environment = dict(os.environ)
        environment['GITHUB_TOKEN'] = auth.stdout.strip()
        environment['SYMPHONY_INSTALL_DIR'] = str(ROOT / '.runtime/symphony-install')
        command = [str(ROOT / '.runtime/bin/symphony-nightly-macos_arm64'),
                   '--i-understand-that-this-will-be-running-without-the-usual-guardrails',
                   '--logs-root', str(output / 'logs'), str(ROOT / 'config/PROBE_WORKFLOW.md')]
        started = time.monotonic()
        record = {'command': command, 'started_at_epoch': time.time(),
                  'model_attempt_limit': 1, 'engine_seconds': 240,
                  'cleanup_grace_seconds': 4, 'automatic_model_retries': 0}
        def stop(signum, frame):
            raise StopRequested(signum)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            proc = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment, start_new_session=True)
            record['pid'] = proc.pid
            (output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
            result = ROOT / 'evidence/motor-probe' / ('GH-' + str(contract['issue_number'])) / 'tracker-transition.json'
            try:
                while proc.poll() is None and time.monotonic() - started < 240:
                    if result.exists():
                        record['stop_reason'] = 'preservation and tracker transition recorded'
                        break
                    time.sleep(0.2)
                else:
                    record['stop_reason'] = 'engine exit or experiment timeout'
            except StopRequested as stop:
                record['stop_reason'] = 'signal ' + str(stop.signum)
            finally:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    signal.signal(sig, signal.SIG_IGN)
                record['process_group_removed'] = stop_group(proc)
                record['elapsed_seconds'] = round(time.monotonic() - started, 3)
                record['engine_exit_code'] = proc.poll()
                (output / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record))
        return 0 if result.exists() and record['process_group_removed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
