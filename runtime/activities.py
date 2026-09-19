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


@activity.defn
def execute_codex(request: dict) -> dict:
    proc = subprocess.Popen([sys.executable, '-m', 'runtime.attempt'], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(json.dumps(request).encode(), timeout=request['seconds'] + 15)
    finally:
        removed = stop_group(proc)
    if proc.returncode != 0 or not removed:
        # No automatic retry, no inferred success if child output is unavailable.
        return {'provider_completed': False, 'reason': 'attempt failed or interrupted',
                'exit_code': proc.returncode, 'stderr': stderr.decode(errors='replace')[-4000:]}
    result = json.loads(stdout)
    workspace = ROOT / '.runtime/tasks' / request['task_id'] / 'candidate'
    validation = verify(workspace)
    files = {}
    for name in ('tools/run_report.py', 'tools/test_run_report.py', 'tools/README.md'):
        path = workspace / name
        if path.is_symlink() or not path.is_file():
            validation['passed'] = False
        else:
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    validation['candidate_files_sha256'] = files
    output = ROOT / result['evidence']
    (output / 'acceptance.json').write_text(json.dumps(validation, indent=2) + '\n')
    result.update(phase_acceptance_passed=validation['passed'], candidate_files_sha256=files)
    return result
