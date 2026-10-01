"""Host-only publication boundary. Receipts are evidence, never candidate authority.

The caller supplies frozen host task/evidence. Git object identities, whole-task
completion and both mandatory decisions are checked before any remote mutation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .targets import TARGETS, RUNTIME, origin


class GateClosed(ValueError):
    pass


def publication_git(repository, *args, text=True):
    """No inherited Git redirection or candidate hooks; keep gh's existing login."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_LITERAL_PATHSPECS='1')
    return subprocess.run(['git', '--no-replace-objects', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
                           '-c', 'core.fsmonitor=false', '-c', 'core.pager=cat',
                           '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
                           '-C', str(repository), *args], env=env, check=True,
                          text=text, capture_output=True, timeout=30).stdout


def require_git_origin(repository, expected):
    """Check actual push destinations and all effective URL rewrite settings."""
    # A repository-local credential helper, proxy, remote helper or include can
    # redirect execution/credentials even while get-url still names GitHub.
    # Authentication settings may come from the account's existing global gh
    # setup, never from a candidate repository. Worktree configuration is read
    # separately when Git's own boolean parser says it is enabled.
    allowed = re.compile(r'^(?:core\.(?:repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|hookspath|fsmonitor)|user\.(?:name|email)|remote\.origin\.(?:url|fetch|pushurl)|branch\..+\.(?:remote|merge|vscode-merge-base)|diff\.renames|extensions\.worktreeconfig)$')
    raw = publication_git(repository, 'config', '--null', '--list')
    # Git's parser handles valueless keys and nonzero integers. Asking for
    # --worktree while it is disabled can itself fail with linked worktrees.
    active = publication_git(repository, 'config', '--type=bool', '--default=false',
                             '--get', 'extensions.worktreeConfig').strip()
    if active not in ('true', 'false'):
        raise GateClosed('Unknown worktree configuration state')
    scopes = ('--local', '--worktree') if active == 'true' else ('--local',)
    for scope in scopes:
        local = publication_git(repository, 'config', scope, '--includes', '--null', '--list')
        if any(not allowed.fullmatch(entry.partition('\n')[0].lower()) for entry in local.split('\0') if entry):
            raise GateClosed('Unsafe repository-local publication Git configuration')
    for entry in raw.split('\0'):
        key, _, value = entry.partition('\n')
        key = key.lower()
        if key.startswith('url.') and key.endswith(('.insteadof', '.pushinsteadof')):
            # Fail closed even for an apparently redundant rewrite: interpreting
            # longest-prefix and overlapping replacements is not this gate's job.
            raise GateClosed('URL rewriting is not allowed in publication Git configuration')
        if key == 'remote.origin.pushurl' and value != expected:
            raise GateClosed('Unauthorized explicit push URL')
    if (publication_git(repository, 'remote', 'get-url', '--all', 'origin').splitlines() != [expected]
            or publication_git(repository, 'remote', 'get-url', '--push', '--all', 'origin').splitlines() != [expected]):
        raise GateClosed('Unauthorized fetch or push destination')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_binding(task, subject, review):
    return 'nortropic-check/1:' + digest({'target': task['target'], 'task': digest(task),
                                        'subject': subject, 'review': digest(review)})


def require_publication_history(candidate):
    """The permanent owner ledger must permit this commit before remote effects."""
    from .failure_ledger import Ledger
    try:
        Ledger().require_publishable(candidate)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise GateClosed('Permanent publication history refused: ' + str(error)) from None


def require_gate(task, subject, tests, review, *, allowed_targets=TARGETS):
    if not all(isinstance(x, dict) for x in (task, subject, tests, review)):
        raise GateClosed('Missing or non-object mandatory evidence')
    if task.get('target') not in allowed_targets:
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
    # Completeness first, and named: an unfinished review carries no identity fields at all, and reporting that as a
    # stale or mismatched identity misdescribes a host failure to the diagnosis role (measured 2026-09-22).
    for name, evidence in (('tests', tests), ('review', review)):
        if not isinstance(evidence, dict) or evidence.get('terminal_status') != 'completed' or evidence.get('scope') != 'whole_task':
            raise GateClosed('Mandatory %s evidence unfinished or wrong scope: %s' % (name, evidence.get('terminal_status') if isinstance(evidence, dict) else 'absent'))
        for field in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256'):
            if evidence.get(field) != subject.get(field):
                raise GateClosed('Stale or mismatched %s evidence: %s' % (name, field))
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
    ALLOWED_TARGETS = TARGETS

    def __init__(self, repository, target=RUNTIME):
        self.ORIGIN = origin(target)
        self.REPOSITORY = target
        self.repository = Path(repository).resolve()
        self.effect_guard = None

    def git(self, *args):
        def invoke():
            if args and args[0] == 'push':
                require_git_origin(self.repository, self.ORIGIN)
            return publication_git(self.repository, *args).rstrip("\n")
        if args and args[0] == 'push' and self.effect_guard:
            return self.effect_guard({'git': list(args)}, invoke)
        return invoke()

    def api(self, path, method='GET', body=None):
        argv = ['gh', 'api', 'repos/' + self.REPOSITORY + '/' + path, '-X', method]
        if body is not None: argv += ['--input', '-']
        def invoke():
            result = subprocess.run(argv, input=json.dumps(body) if body is not None else None,
                                    check=True, text=True, capture_output=True, timeout=30)
            return json.loads(result.stdout)
        if method != 'GET' and self.effect_guard:
            return self.effect_guard({'api': path, 'method': method, 'body': body}, invoke)
        return invoke()

    def inspect_candidate(self, task, subject):
        if task.get('target') != self.REPOSITORY:
            raise GateClosed('Publisher and accepted target differ')
        require_git_origin(self.repository, self.ORIGIN)
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
                from .content_guard import require_deletion, ContentRefused
                try:require_deletion(self.repository,base,path,task['target'])
                except ContentRefused as error:raise GateClosed(str(error)) from None
                continue
            mode = entry.split()[0]
            if mode not in ('100644', '100755'):
                raise GateClosed('Only regular source files may be published')
        from .content_guard import require_content, ContentRefused
        try:
            self.content_receipt = require_content(self.repository, base, candidate, task['target'])
            from .decision_guard import require_decisions
            self.decision_receipt = require_decisions(self.repository, base, candidate, task['target'])
        except ContentRefused as error:
            raise GateClosed(str(error)) from None
        return self.git('rev-parse', candidate + '^{tree}')

    def require_protection(self):
        # Trust is selected by the host-controlled server rule, never by task,
        # receipt, installed-app discovery or the candidate's check name.
        protection = self.api('branches/main/protection')
        if not isinstance(protection, dict):
            raise GateClosed('Required server protection is not active')
        checks = protection.get('required_status_checks')
        if not isinstance(checks, dict):
            raise GateClosed('Required server protection is not active')
        entries = checks.get('checks')
        if (not isinstance(entries, list) or len(entries) != 2
                or not all(isinstance(x, dict) for x in entries)
                or {x.get('context') for x in entries} != {'runtime/tests', 'runtime/review'}):
            raise GateClosed('Exact mandatory server checks are missing or ambiguous')
        issuers = {x['context']: x.get('app_id') for x in entries}
        if any(type(app) is not int or app <= 0 for app in issuers.values()):
            raise GateClosed('Mandatory checks lack an explicit trusted server App issuer')
        def enabled(name):
            value = protection.get(name)
            return value.get('enabled') if isinstance(value, dict) else None
        if (checks.get('strict') is not True
                or enabled('enforce_admins') is not True
                or enabled('allow_force_pushes') is not False
                or enabled('allow_deletions') is not False
                or enabled('required_linear_history') is not True
                or not isinstance(protection.get('required_pull_request_reviews'), dict)):
            raise GateClosed('Required server protection is not active')
        return issuers

    def require_checks(self, candidate, issuers, expected_binding):
        # Commit statuses (including PAT-written success) do not prove an App
        # identity. Only GitHub's authenticated check-run fields are accepted.
        result = self.api('commits/' + candidate + '/check-runs?filter=latest&per_page=100')
        runs = result.get('check_runs') if isinstance(result, dict) else None
        if (not isinstance(runs, list) or type(result.get('total_count')) is not int
                or result['total_count'] != len(runs)
                or not all(isinstance(run, dict) for run in runs)):
            raise GateClosed('Check-run readback is incomplete or malformed')
        verified = {}
        for name, issuer in issuers.items():
            matches = [run for run in runs if run.get('name') == name]
            # Do not choose an old green run among ambiguous/latest suites.
            if len(matches) != 1:
                raise GateClosed('Mandatory check-run missing or ambiguous: ' + name)
            run = matches[0]
            app = run.get('app')
            if (not isinstance(app, dict) or type(app.get('id')) is not int
                    or app['id'] != issuer or run.get('head_sha') != candidate
                    or run.get('status') != 'completed' or run.get('conclusion') != 'success'
                    or run.get('external_id') != expected_binding
                    or type(run.get('id')) is not int or run['id'] <= 0):
                raise GateClosed('Mandatory check lacks trusted exact-head success: ' + name)
            verified[name] = {'app_id': issuer, 'check_run_id': run['id'], 'head_sha': candidate,
                              'binding': expected_binding}
        return verified

    def issue_checks(self, task, subject, review):
        from .host_publication import issue
        return issue(task, subject, review)

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
        from .development_binding import for_task
        scope = for_task(task)
        if scope is not None:
            self.effect_guard = lambda operation, invoke: scope.publication_effect(
                task['development']['work'], task['id'], digest(task), operation, invoke)
        else:
            self.effect_guard = None
        receipt = self._publish(task, subject, tests, review)
        if scope is not None:
            scope.record_integration(task['development']['work'], task['id'], digest(task), receipt)
        return receipt

    def _publish(self, task, subject, tests, review):
        require_gate(task, subject, tests, review, allowed_targets=self.ALLOWED_TARGETS)  # MUST precede effects.
        require_publication_history(subject['candidate'])
        tree = self.inspect_candidate(task, subject)
        issuers = self.require_protection()
        candidate = subject['candidate']
        branch = 'runtime/' + candidate
        matches = self.api('pulls?state=all&head=Nortropic:' + branch)
        if len(matches) > 1:
            raise GateClosed('Ambiguous publication identity')
        pr = self.api('pulls/' + str(matches[0]['number'])) if matches else None
        if pr and pr.get('merged'):
            # A lost response never causes a second publication.
            checks = self.require_checks(candidate, issuers, check_binding(task, subject, review))
            return {**self.reconcile(pr, subject, tree), 'checks': checks}
        if pr and (pr.get('state') != 'open' or pr.get('head', {}).get('sha') != candidate):
            raise GateClosed('Existing PR is closed or has changed head')
        self.require_base(subject['base'])
        require_publication_history(candidate)
        self.git('push', 'origin', candidate + ':refs/heads/' + branch)  # Ordinary, never force.
        if pr is None:
            require_publication_history(candidate)
            pr = self.api('pulls', 'POST', {
                'title': 'Runtime: ' + task['id'], 'head': branch, 'base': 'main',
                'body': 'Accepted task: ' + task['id'] + '\n\nExact candidate: ' + candidate +
                        '\n\nWhole-task tests and independent review passed for the same subject.\n' +
                        'Task SHA256: ' + subject['task_sha256'] + '\n' +
                        'Acceptance SHA256: ' + subject['acceptance_sha256'] + '\n' +
                        'Independent reviewer run: ' + review['reviewer_run']})
        number = pr['number']
        # Re-read server identities immediately before the expected-head merge.
        pr = self.api('pulls/' + str(number))
        if pr.get('head', {}).get('sha') != candidate or pr.get('base', {}).get('ref') != 'main':
            raise GateClosed('PR identity changed')
        self.require_base(subject['base'])
        if self.require_protection() != issuers:
            raise GateClosed('Mandatory server issuers changed during publication')
        self.issue_checks(task, subject, review)
        # Issuance may take time. Re-read source and server trust after it too.
        self.require_base(subject['base'])
        if self.require_protection() != issuers:
            raise GateClosed('Mandatory server issuers changed during issuance')
        checks = self.require_checks(candidate, issuers, check_binding(task, subject, review))
        require_publication_history(candidate)
        merged = self.api('pulls/' + str(number) + '/merge', 'PUT', {'sha': candidate, 'merge_method': 'squash'})
        if merged.get('merged') is not True:
            raise GateClosed('Server did not confirm merge; reconcile before any retry')
        return {**self.reconcile(self.api('pulls/' + str(number)), subject, tree), 'checks': checks}
