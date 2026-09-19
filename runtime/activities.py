"""Host activities, using native engine retries/timeouts instead of a scheduler."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from temporalio import activity
from .profile import ROOT
from acceptance.run_report_phase1 import verify
from scripts.bounded import stop_group
from .snapshot import snapshot


@activity.defn
def execute_codex(request: dict) -> dict:
    proc = subprocess.Popen([sys.executable, '-m', 'runtime.attempt'], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(json.dumps(request).encode(), timeout=request['seconds'] + 15)
    finally:
        removed = stop_group(proc)
    try:
        result = json.loads(stdout)
    except (ValueError, UnboundLocalError):
        result = {'provider_completed': False, 'reason': 'missing valid attempt result',
                  'exit_code': proc.returncode, 'attempt': request['number']}
    if proc.returncode != 0 or not removed or not result.get('provider_completed'):
        return result
    workspace = ROOT / '.runtime/tasks' / request['task_id'] / 'candidate'
    output = ROOT / result['evidence']
    try:
        files = snapshot(workspace, output / 'candidate',
                         ('tools/run_report.py', 'tools/test_run_report.py', 'tools/README.md'))
        validation = verify(output / 'candidate')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        files = {}
        validation = {'passed': False, 'reason': str(error)}
    validation['candidate_files_sha256'] = files
    (output / 'acceptance.json').write_text(json.dumps(validation, indent=2) + '\n')
    result.update(phase_acceptance_passed=validation['passed'], candidate_files_sha256=files)
    return result
