"""Host-only publication boundary. Receipts are evidence, never candidate authority.

The caller supplies frozen host task/evidence. Git object identities, whole-task
completion and both mandatory decisions are checked before any remote mutation.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .targets import TARGETS, RUNTIME, origin


class GateClosed(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require_gate(task, subject, tests, review):
    if not all(isinstance(x, dict) for x in (task, subject, tests, review)):
        raise GateClosed('Missing or non-object mandatory evidence')
    if task.get('target') not in TARGETS:
        raise GateClosed('Target is outside the authorized project')
    if not isinstance(task.get('id'), str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', task['id']):
        raise GateClosed('Accepted task ID missing or invalid')
    for name in ('base', 'candidate'):
        if not re.fullmatch('[0-9a-f]{40}', str(subject.get(name, ''))):
            raise GateClosed('Exact Git identity required: ' + name)
    if subject['candidate'] == subject['base']:
        raise GateClosed('No candidate change')
    if (subject.get('task_id') != task.get('id') or subject.get('task_sha256') != digest(task)
            or subject.get('base') != task.get('base')):
        raise GateClosed('Task identity does not match frozen subject')
    steps = task.get('steps')
    completed = subject.get('completed_steps')
    if (not isinstance(steps, list) or not steps or not all(isinstance(x, dict) for x in steps)
            or not isinstance(completed, list) or any(type(x) is not int for x in completed)
            or completed != list(range(len(steps)))):
        raise GateClosed('Whole accepted task is not complete')
    acceptance_hash = subject.get('acceptance_sha256', '')
    if (not isinstance(acceptance_hash, str) or not re.fullmatch('[0-9a-f]{64}', acceptance_hash)
            or acceptance_hash != task.get('acceptance_sha256')):
        raise GateClosed('Frozen acceptance identity missing')
    implementation_runs = subject.get('implementation_runs')
    if (not isinstance(implementation_runs, list) or not implementation_runs
            or not all(isinstance(x, str) and x for x in implementation_runs)):
        raise GateClosed('Implementation run identity missing')
    for evidence in (tests, review):
        for field in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256'):
            if evidence.get(field) != subject.get(field):
                raise GateClosed('Stale or mismatched evidence: ' + field)
        if evidence.get('scope') != 'whole_task' or evidence.get('terminal_status') != 'completed':
            raise GateClosed('Mandatory evidence unfinished or wrong scope')
    if tests.get('passed') is not True:
        raise GateClosed('Required tests did not pass')
    if review.get('verdict') != 'approved' or review.get('blocking_findings') != []:
        raise GateClosed('Required review did not approve')
    reviewer_run = review.get('reviewer_run')
    if not isinstance(reviewer_run, str) or not reviewer_run or reviewer_run in implementation_runs:
        raise GateClosed('Independent review run missing')
    return True


class Publisher:
    REPOSITORY = 'Nortropic/nortropic-runtime'
    ORIGIN = 'https://github.com/Nortropic/nortropic-runtime.git'

    def __init__(self, repository, target=RUNTIME):
        self.ORIGIN = origin(target)
        self.REPOSITORY = target
        self.repository = Path(repository).resolve()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repository), *args], check=True,
                              text=True, capture_output=True, timeout=30).stdout.rstrip("\n")

    def api(self, path, method='GET', body=None):
        argv = ['gh', 'api', 'repos/' + self.REPOSITORY + '/' + path, '-X', method]
        if body is not None: argv += ['--input', '-']
        result = subprocess.run(argv, input=json.dumps(body) if body is not None else None,
                                check=True, text=True, capture_output=True, timeout=30)
        return json.loads(result.stdout)

    def inspect_candidate(self, task, subject):
        if task.get('target') != self.REPOSITORY:
            raise GateClosed('Publisher and accepted target differ')
        if self.git('remote', 'get-url', 'origin') != self.ORIGIN:
            raise GateClosed('Unauthorized origin')
        base, candidate = subject['base'], subject['candidate']
        parents = self.git('rev-list', '--parents', '-n', '1', candidate).split()
        if parents != [candidate, base]:
            raise GateClosed('Candidate is not one commit on the accepted base')
        paths = [p for p in self.git('diff', '--no-renames', '--name-only', '-z', base, candidate).split('\0') if p]
        allowed = task.get('allowed_paths')
        if (not isinstance(allowed, list) or not allowed or not paths
                or not set(paths).issubset(set(allowed))):
            raise GateClosed('Candidate exceeds accepted file scope')
        for path in paths:
            entry = self.git('ls-tree', '-z', candidate, '--', path)
            if not entry:
                raise GateClosed('Deletion is not enabled for this publication profile')
            mode = entry.split()[0]
            if mode not in ('100644', '100755'):
                raise GateClosed('Only regular source files may be published')
        return self.git('rev-parse', candidate + '^{tree}')

    def require_protection(self):
        protection = self.api('branches/main/protection')
        checks = protection.get('required_status_checks') or {}
        required = {x['context'] for x in checks.get('checks', [])}
        if (checks.get('strict') is not True or required != {'runtime/tests', 'runtime/review'}
                or not protection.get('enforce_admins', {}).get('enabled')
                or protection.get('allow_force_pushes', {}).get('enabled')
                or protection.get('allow_deletions', {}).get('enabled')
                or not protection.get('required_linear_history', {}).get('enabled')
                or protection.get('required_pull_request_reviews') is None):
            raise GateClosed('Required server protection is not active')

    def require_base(self, base):
        self.git('fetch', 'origin', 'main')
        if self.git('rev-parse', 'refs/remotes/origin/main') != base:
            raise GateClosed('Remote main changed; new candidate/test/review required')

    def reconcile(self, pr, subject, tree):
        if not pr.get('merged') or pr.get('head', {}).get('sha') != subject['candidate']:
            raise GateClosed('Remote merge is missing or has wrong head')
        merged = pr.get('merge_commit_sha')
        if not isinstance(merged, str) or not re.fullmatch('[0-9a-f]{40}', merged):
            raise GateClosed('Missing exact merge identity')
        self.git('fetch', 'origin', 'main')
        self.git('merge-base', '--is-ancestor', merged, 'refs/remotes/origin/main')
        if self.git('rev-list', '--parents', '-n', '1', merged).split() != [merged, subject['base']]:
            raise GateClosed('Squash integration base does not match accepted base')
        if self.git('rev-parse', merged + '^{tree}') != tree:
            raise GateClosed('Integrated tree differs from tested/reviewed candidate')
        return {'merged': True, 'candidate': subject['candidate'], 'merge_commit': merged,
                'tree': tree, 'url': pr['html_url']}

    def publish(self, task, subject, tests, review):
        require_gate(task, subject, tests, review)  # MUST precede every publication caller.
        tree = self.inspect_candidate(task, subject)
        self.require_protection()
        candidate = subject['candidate']
        branch = 'runtime/' + candidate
        matches = self.api('pulls?state=all&head=Nortropic:' + branch)
        if len(matches) > 1:
            raise GateClosed('Ambiguous publication identity')
        pr = self.api('pulls/' + str(matches[0]['number'])) if matches else None
        if pr and pr.get('merged'):
            # A lost response never causes a second publication.
            return self.reconcile(pr, subject, tree)
        if pr and (pr.get('state') != 'open' or pr.get('head', {}).get('sha') != candidate):
            raise GateClosed('Existing PR is closed or has changed head')
        self.require_base(subject['base'])
        self.git('push', 'origin', candidate + ':refs/heads/' + branch)  # Ordinary, never force.
        if pr is None:
            pr = self.api('pulls', 'POST', {
                'title': 'Runtime: ' + task['id'], 'head': branch, 'base': 'main',
                'body': 'Accepted task: ' + task['id'] + '\n\nExact candidate: ' + candidate +
                        '\n\nWhole-task tests and independent review passed for the same subject.\n' +
                        'Task SHA256: ' + subject['task_sha256'] + '\n' +
                        'Acceptance SHA256: ' + subject['acceptance_sha256'] + '\n' +
                        'Independent reviewer run: ' + review['reviewer_run']})
        number = pr['number']
        for context, description in (('runtime/tests', 'Whole-task external acceptance passed'),
                                     ('runtime/review', 'Independent exact-candidate review approved')):
            self.api('statuses/' + candidate, 'POST', {'state': 'success', 'context': context,
                                                     'description': description})
        # Re-read server identities immediately before the expected-head merge.
        pr = self.api('pulls/' + str(number))
        if pr.get('head', {}).get('sha') != candidate or pr.get('base', {}).get('ref') != 'main':
            raise GateClosed('PR identity changed')
        self.require_base(subject['base'])
        self.require_protection()
        status = self.api('commits/' + candidate + '/status')
        required = {x['context']: x['state'] for x in reversed(status.get('statuses', []))}
        if status.get('state') != 'success' or any(required.get(x) != 'success' for x in ('runtime/tests', 'runtime/review')):
            raise GateClosed('Required current-SHA statuses are not successful')
        merged = self.api('pulls/' + str(number) + '/merge', 'PUT', {'sha': candidate, 'merge_method': 'squash'})
        if merged.get('merged') is not True:
            raise GateClosed('Server did not confirm merge; reconcile before any retry')
        return self.reconcile(self.api('pulls/' + str(number)), subject, tree)
