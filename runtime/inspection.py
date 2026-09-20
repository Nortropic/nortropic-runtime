"""Read preserved Runtime evidence only. Never start an engine or import activities.

A snapshot is explicitly not a live query. Its age is always exposed. Completion
requires matching frozen input, native observation, acceptance, independent
review and integration receipts. Remote freshness is checked by the operator.
"""
import hashlib
import json
import time
from .profile import ROOT
from .task import load, task_directory, evidence_directory
from .integration import digest, require_gate
from .snapshot import read_regular


def read_json(root, name):
    value = json.loads(read_regular(root, name, limit=4194304))
    if not isinstance(value, dict):
        raise ValueError('Expected an evidence object: ' + name)
    return value


def inspect(task_id):
    report = {'task_id': task_id, 'observation': 'unavailable', 'live': False,
              'remote_current': False, 'verified_delivery': False,
              'limitations': ['Saved Runtime observation; not a live engine or remote query.']}
    try:
        task = load(task_id)
        root = evidence_directory(task_id)
        manifest = read_json(root, 'accepted.json')
        if manifest.get('task_sha256') != digest(task) or manifest.get('task') != task:
            raise ValueError('Frozen input and acceptance manifest differ')
        if hashlib.sha256(read_regular(task_directory(task_id), 'acceptance.py')).hexdigest() != task['acceptance_sha256']:
            raise ValueError('Frozen acceptance changed')
        if hashlib.sha256(read_regular(task_directory(task_id), 'brief.md')).hexdigest() != manifest.get('brief_sha256'):
            raise ValueError('Frozen brief changed')
        if task.get('runtime_revision') and manifest.get('runtime_source') != task['runtime_revision']:
            raise ValueError('Runtime revision differs from accepted task')
        report.update(target=task['target'], runtime_revision=manifest['runtime_source'],
                      input_revision=manifest.get('input_source'), base=task['base'],
                      task_sha256=digest(task))
        paths = [p for p in [root/'state.json', *root.glob('observations/*/state.json')] if p.exists()]
        if not paths: raise ValueError('No saved engine observation')
        latest = max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))
        state = read_json(root, str(latest.relative_to(root)))
        stamp = latest.stat().st_mtime
        report.update(observation='snapshot', observed_at_epoch=stamp,
                      age_seconds=max(0, round(time.time()-stamp, 3)),
                      state=state, evidence=str(latest.relative_to(ROOT)),
                      phase=state['phase'])
        if state['phase'] != 'completed':
            return report
        latest_result = state['results'][-1]
        candidate = latest_result['candidate']
        subject = {'task_id':task_id, 'task_sha256':digest(task), 'base':task['base'],
                   'candidate':candidate, 'completed_steps':list(range(len(task['steps']))),
                   'acceptance_sha256':task['acceptance_sha256'],
                   'implementation_runs':[r['thread_id'] for r in state['results'] if r.get('thread_id')]}
        # Never follow a path supplied by evidence outside this task's directory.
        attempt = latest_result['attempt']
        if type(attempt) is not int or attempt < 1: raise ValueError('Invalid attempt')
        acceptance = read_json(root, f'attempt-{attempt}/acceptance.json')
        frozen = read_json(root, f'attempt-{attempt}/candidate.json')
        if frozen.get('candidate') != candidate or frozen.get('task_sha256') != digest(task) or frozen.get('base') != task['base']:
            raise ValueError('Candidate identity differs')
        if acceptance.get('candidate_files_sha256') != frozen.get('candidate_files_sha256') or not frozen.get('candidate_files_sha256'):
            raise ValueError('Acceptance candidate files differ')
        tests = {k:subject[k] for k in ('task_id','task_sha256','candidate','acceptance_sha256')}
        tests.update(scope='whole_task', terminal_status='completed', passed=acceptance.get('passed'))
        review = state['review']
        decisions = [read_json(root, str(p.relative_to(root))) for p in root.glob('review-*/decision.json')]
        if review not in decisions: raise ValueError('Independent review receipt missing')
        require_gate(task, subject, tests, review)
        integration = read_json(root, 'integration.json')
        if (integration != state.get('integration') or integration.get('candidate') != candidate
                or integration.get('merged') is not True):
            raise ValueError('Integration receipt differs from engine observation')
        import re
        if not all(re.fullmatch('[0-9a-f]{40}', integration.get(k, '')) for k in ('merge_commit','tree')):
            raise ValueError('Exact remote integration identities missing')
        if not integration.get('url','').startswith('https://github.com/'+task['target']+'/pull/'):
            raise ValueError('Integration target differs')
        report.update(verified_delivery=True, candidate=candidate, integration=integration,
                      acceptance_sha256=task['acceptance_sha256'],
                      review_run=review['reviewer_run'])
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        report.update(observation='unavailable', verified_delivery=False, error=str(error))
    return report
