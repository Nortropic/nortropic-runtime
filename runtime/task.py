"""Frozen accepted input and isolated task locations; Temporal owns execution state."""
import hashlib
import json
from pathlib import Path
import re

from .integration import digest
from .profile import ROOT
from .snapshot import read_regular


def task_directory(task_id):
    if not isinstance(task_id, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', task_id):
        raise ValueError('Invalid accepted task ID')
    return ROOT / '.runtime/tasks' / task_id


def validate(task):
    task_directory(task['id'])
    if task.get('target') != 'Nortropic/nortropic-runtime' or not re.fullmatch('[0-9a-f]{40}', task.get('base', '')):
        raise ValueError('Authorized target and exact accepted base required')
    paths = task.get('allowed_paths')
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise ValueError('Explicit unique source paths required')
    for path in paths:
        if (not isinstance(path, str) or not path.startswith('tools/') or
                any(part in ('', '.', '..') for part in path.split('/')) or
                not re.fullmatch('[A-Za-z0-9_./-]+', path)):
            raise ValueError('This qualified profile supports explicit tools/ source files only')
    if type(task.get('attempt_seconds')) is not int or not 1 <= task['attempt_seconds'] <= 3600:
        raise ValueError('Bound each individual invocation to 1..3600 seconds')
    if task.get('automatic_retries') != 0:
        raise ValueError('Automatic model retries are not enabled')
    if not isinstance(task.get('steps'), list) or not task['steps']:
        raise ValueError('Accepted executor steps required')
    for step in task['steps']:
        if step.get('provider') not in ('codex', 'claude') or not isinstance(step.get('prompt'), str) or not step['prompt']:
            raise ValueError('Invalid provider step')
        if step['provider'] == 'claude' and not step.get('waiting_reason'):
            raise ValueError('Claude is not yet qualified: explicit waiting state required')
    if not re.fullmatch('[0-9a-f]{64}', task.get('acceptance_sha256', '')):
        raise ValueError('Frozen acceptance digest required')
    return task


def load(task_id, expected_digest=None):
    state = task_directory(task_id)
    if not (state / 'accepted.json').exists() and task_id == 'runtime-run-report-1':
        # Compatibility for the already-persisted pilot history; no new task uses this.
        task = json.loads((ROOT / 'tasks/run-report.json').read_text())
    else:
        task = validate(json.loads(read_regular(state, 'accepted.json')))
    if task['id'] != task_id or (expected_digest is not None and digest(task) != expected_digest):
        raise ValueError('Task input changed after acceptance')
    return task


def evidence_directory(task_id):
    task_directory(task_id)
    if task_id == 'runtime-run-report-1': return ROOT / 'evidence/accepted-task'
    return ROOT / 'evidence/runs' / task_id


def frozen_verifier(task):
    state = task_directory(task['id'])
    source = read_regular(state, 'acceptance.py')
    if hashlib.sha256(source).hexdigest() != task['acceptance_sha256']:
        raise ValueError('Frozen verifier bytes changed')
    namespace = {'__file__': str(state / 'acceptance.py'), '__name__': 'runtime_frozen_acceptance'}
    # This is reviewed, host-owned acceptance code, never candidate-generated code.
    exec(compile(source, str(state / 'acceptance.py'), 'exec'), namespace)
    return namespace['verify']
