"""Frozen accepted input and isolated task locations; Temporal owns execution state."""
import hashlib
import json
from pathlib import Path
import re

from .integration import digest
from .profile import ROOT
from .snapshot import read_regular
from .targets import TARGETS, OFFICE


def task_directory(task_id):
    if not isinstance(task_id, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', task_id):
        raise ValueError('Invalid accepted task ID')
    return ROOT / '.runtime/tasks' / task_id


def validate(task):
    task_directory(task['id'])
    if task.get('target') not in TARGETS or not re.fullmatch('[0-9a-f]{40}', task.get('base', '')):
        raise ValueError('Authorized target and exact accepted base required')
    paths = task.get('allowed_paths')
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise ValueError('Explicit unique source paths required')
    for path in paths:
        if (not isinstance(path, str) or not path.startswith('tools/') or
                any(part in ('', '.', '..') for part in path.split('/')) or
                not re.fullmatch('[A-Za-z0-9_./-]+', path)):
            raise ValueError('This qualified profile supports explicit tools/ source files only')
    if task['target'] == OFFICE:
        if not re.fullmatch('[0-9a-f]{40}', task.get('runtime_revision', '')):
            raise ValueError('Office task requires exact reviewed Runtime revision')
        if task.get('continuation') or any(s.get('waiting_reason') for s in task.get('steps', [])):
            raise ValueError('Legacy access/base revision is not qualified for office tasks')
    if task['target'] == OFFICE and any(p in ('tools/kontor.py',) for p in paths):
        raise ValueError('Active office entry is host-owned, not candidate-writable')
    if type(task.get('attempt_seconds')) is not int or not 1 <= task['attempt_seconds'] <= 3600:
        raise ValueError('Bound each individual invocation to 1..3600 seconds')
    if task.get('automatic_retries') != 0:
        raise ValueError('Automatic model retries are not enabled')
    if not isinstance(task.get('steps'), list) or not task['steps']:
        raise ValueError('Accepted executor steps required')
    for step in task['steps']:
        # The executor is an explicit accepted choice per step, never a fallback.
        if step.get('provider') not in ('codex', 'claude') or not isinstance(step.get('prompt'), str) or not step['prompt']:
            raise ValueError('Invalid provider step')
    # Absent means the original Codex reviewer, so every earlier accepted task
    # keeps its exact digest and history. A present value is part of the digest.
    if 'review_provider' in task and task['review_provider'] not in ('codex', 'claude'):
        raise ValueError('Invalid review provider')
    # Absent keeps the former review bound, so every earlier accepted task keeps its exact digest and history. A present
    # value is an explicit budget within the accepted frame and part of the digest (RUNTIME-GRANSKNINGSBUDGET-ACCEPT-20260925).
    if 'review_seconds' in task:
        from .development_binding import review_budget
        review_budget(task['review_seconds'])
        if 'development' in task:
            raise ValueError('The finite development profile keeps its own review bound')
    if not re.fullmatch('[0-9a-f]{64}', task.get('acceptance_sha256', '')):
        raise ValueError('Frozen acceptance digest required')
    if 'development' in task:
        binding = task['development']
        if (task['target'] != OFFICE or not isinstance(binding, dict)
                or set(binding) != {'contract_sha256', 'work'}
                or not re.fullmatch('[0-9a-f]{64}', str(binding.get('contract_sha256', '')))
                or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', str(binding.get('work', '')))):
            raise ValueError('Invalid finite development binding')
        if len(paths) != 2 or task['attempt_seconds'] > 480:
            raise ValueError('Finite child profile supports two files and at most480 model seconds')
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
