"""Automatic Runtime code transitions (D043): a release integrated through protected publication and separate review is
staged, checked, rehearsed in isolation and activated by itself when Runtime is idle, with the same way back.

The owner's agent runs this from the ACTIVE release's copy of model_choice.py (`auto`), after the workplace's choice
(D040). It never acts on a revision it has not proven integrated and reviewed, and it never changes the activator itself:

integrated and reviewed   GitHub, not files a session writes: every first-parent commit from the active revision to
                          main is the squash merge of exactly one pull request; that request's head carries both
                          required checks (runtime/tests, runtime/review) from the one App branch protection names (the
                          protection read as strictly as the publisher reads it), both successful and with one binding;
                          the binding is recomputed here from a sealed issuer request whose review approves with no
                          blocking finding, by a reviewer who did not implement; the head's tree is the merge's tree.
                          Anything else is refused for that revision.
the owner's part          a release whose net difference from the active one changes the activator, its rehearsal, the
                          chain proof's binding, the check issuer, the measurement queue or the service definition
                          (OWNER_FILES), the AP-10 command, the service plist or the web tools is left for the owner's own
                          controlled transition.
same preconditions        model_choice's list, measured before the rehearsal and again before the stop: the staged
                          Runtime code byte for byte git at the proven revision, the AP-10 window (no run, the next more
                          than 20 minutes away, its schedule bound to the active release), the recorded service alive,
                          no web profile run, no busy execution, no AP-11 execution at all, the NEW code's own daemon
                          start requirements (measured by that code), and a way back (the active release's own check).
rehearsal                 before the first stop, and only when the same preconditions pass (Runtime idle): a port- and
                          root-shifted copy of both releases on a consistent copy of the database starts the new release
                          twice and the old one after it, sandboxed off the network beyond this Mac and every write
                          outside its own directory, its connections measured to stay inside the copy
                          (scripts/code_rehearsal.py). A copy holding work in progress waits.
same activation           model_choice's backup, stop, select, start, confirm, restore on failure, and AP-10 rebind.

A revision that ended refused, owner_needed, restored, failed or interrupted is not tried again while the active release
stays the same; a newer revision, or the same one after another activation changed the active release, is looked at anew,
its chain, rehearsal and preconditions proven again.
Status for the workplace: .runtime/ap10/automatic-code-status.json.
"""
import asyncio
import base64
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile

REPOSITORY = 'Nortropic/nortropic-runtime'
STATUS_SCHEMA = 'automatic-code-status/1'
TOOL = 'runtime/scripts/code_transition.py'
FINAL = ('refused', 'owner_needed', 'restored', 'failed', 'interrupted')
CHECKS = ('runtime/tests', 'runtime/review')
# The activator, its rehearsal, the chain proof's binding and the code that issues the checks and seals the requests it
# matches, the agent's measurement queue (the caller of the one sudoers rule) and the service definition: what the owner
# approved once. A release that changes one is the owner's to activate.
OWNER_FILES = ('runtime/scripts/model_choice.py', 'runtime/scripts/code_transition.py',
               'runtime/scripts/code_rehearsal.py', 'runtime/scripts/install_ap10.py',
               'runtime/scripts/measurement_queue.py', 'runtime/runtime/integration.py',
               'runtime/runtime/check_issuer.py', 'runtime/runtime/host_publication.py')
HEX = re.compile(r'[0-9a-f]{40}')
WAITING = ('an AP10 watch run is in progress', 'the next AP10 run is less than 20 minutes away',
           'work is in progress in the engine', 'work started in the engine meanwhile', 'a web profile run is in progress',
           'the running service is not the recorded one', 'an AP-11 execution is running', 'GitHub could not be read',
           'main moved', 'the new revision is not fetched', 'the AP10 schedule could not be read', 'heavy work waits')
# The agent runs under launchd, where no interactive credential helper answers: fetching main uses the owner's gh login,
# the same helper the service's own plist sets for AP-11 (install_ap10.plist). No token is copied or stored.
GIT_ENV = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'LC_ALL': 'C', 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_COUNT': '2',
           'GIT_CONFIG_KEY_0': 'credential.helper', 'GIT_CONFIG_VALUE_0': '',
           'GIT_CONFIG_KEY_1': 'credential.helper', 'GIT_CONFIG_VALUE_1': '!gh auth git-credential'}
# Heavy work (a rehearsal, a measurement) keeps away from the AP-10 watch: its analysis activity's heartbeat margin is
# about two seconds (measured 2026-09-30 07:01Z, when a publication and suites ran beside it). Seconds beyond the
# 20-minute lead a rehearsal may take at most: two guard computations of at most 120 each, phase A 300, three starts of
# at most 90 + 90 + 30 each, and 20 replay queries of at most 60 - 2370 in all, and the copies and the database backup
# before them. The activation after it measures the 20-minute lead again.
REHEARSAL_MARGIN = 2700


class Wait(Exception):
    """Passes by itself: look again next time."""


class Refused(Exception):
    """This revision is never activated automatically."""


class OwnerNeeded(Exception):
    """Integrated and reviewed, but it changes what only the owner's own controlled transition may change."""


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc)


def paths(host):
    home = Path(host) / '.runtime/ap10'
    return {'records': home / 'code-transitions', 'status': home / 'automatic-code-status.json',
            'lock': home / 'automatic-choice.lock', 'requests': Path(host) / '.runtime/ap11/check-issuer/requests'}


def git(host, *args, timeout=120):
    env = {**GIT_ENV, 'HOME': str(Path.home())}
    return subprocess.check_output(['git', '-C', str(host), *args], timeout=timeout, env=env,
                                   stderr=subprocess.PIPE).decode().strip()


class GitHub:
    """Read-only questions to GitHub through the owner's gh login (the agent runs as the owner)."""

    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def get(self, path):
        env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(Path.home()), 'LC_ALL': 'C',
               'GH_PROMPT_DISABLED': '1', 'GH_NO_UPDATE_NOTIFIER': '1'}
        try:
            done = self.runner(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path],
                               capture_output=True, text=True, timeout=60, env=env)
        except (OSError, subprocess.SubprocessError) as error:
            raise Wait('GitHub could not be read (%r)' % error)
        if done.returncode != 0:
            raise Wait('GitHub could not be read (%s)' % done.stderr.strip()[-200:])
        return json.loads(done.stdout)

    def main_head(self):
        return self.get('repos/%s/branches/main' % REPOSITORY)['commit']['sha']

    def protected_app(self):
        """main's protection, read as runtime.integration.require_protection reads it, with both checks from one App."""
        protection = self.get('repos/%s/branches/main/protection' % REPOSITORY)
        required = protection.get('required_status_checks') or {}
        checks = required.get('checks') or []
        apps = {c.get('app_id') for c in checks}
        if (sorted(c.get('context') for c in checks) != sorted(CHECKS) or len(apps) != 1
                or type(next(iter(apps))) is not int or next(iter(apps)) <= 0):
            raise Refused('main is not protected by exactly the two required checks of one App')
        enabled = lambda name: (protection.get(name) or {}).get('enabled')
        if (required.get('strict') is not True or enabled('enforce_admins') is not True
                or enabled('allow_force_pushes') is not False or enabled('allow_deletions') is not False
                or enabled('required_linear_history') is not True
                or not isinstance(protection.get('required_pull_request_reviews'), dict)):
            raise Refused('main\'s protection is weaker than the publisher requires')
        return next(iter(apps))

    def pulls(self, commit):
        return self.get('repos/%s/commits/%s/pulls' % (REPOSITORY, commit))

    def check_runs(self, commit):
        """The latest check run of each name and App on the commit, every page of them."""
        runs, page = [], 1
        while True:
            value = self.get('repos/%s/commits/%s/check-runs?filter=latest&per_page=100&page=%d' % (REPOSITORY, commit, page))
            runs += value['check_runs']
            if not value['check_runs'] or len(runs) >= value.get('total_count', 0) or page >= 20:
                return runs
            page += 1

    def tree(self, commit):
        return self.get('repos/%s/commits/%s' % (REPOSITORY, commit))['commit']['tree']['sha']


def sealed_requests(host, check_binding):
    """Every sealed issuer request here, by the binding its checks would carry."""
    found = {}
    root = paths(host)['requests']
    for directory in sorted(root.iterdir()) if root.is_dir() else ():
        try:
            request = json.loads((directory / 'request.json').read_text())
            review_bytes = (directory / 'review.json').read_bytes()
            task, subject, review = request['task'], request['subject'], request['review']
            if sha_bytes(review_bytes) != request.get('review_sha256') or json.loads(review_bytes) != review:
                continue
            found[check_binding(task, subject, review)] = (directory.name, request)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def verify_chain(host, active, target, github, check_binding, target_name):
    """Each first-parent commit active..target: one merged pull request whose head carries both protected checks, bound to
    a sealed request whose separate review approves. Returns what was proven, per commit."""
    if not HEX.fullmatch(active) or not HEX.fullmatch(target):
        raise Refused('revisions must be exact commits')
    try:
        git(host, 'merge-base', '--is-ancestor', active, target)
    except subprocess.CalledProcessError:
        raise Refused('main %s does not descend from the active revision %s' % (target[:12], active[:12]))
    commits = git(host, 'rev-list', '--first-parent', '--reverse', '%s..%s' % (active, target)).split()
    if not commits or commits[-1] != target:
        raise Refused('no first-parent path from the active revision to main')
    app = github.protected_app()
    requests = sealed_requests(host, check_binding)
    proven, parent = [], active
    for commit in commits:
        if git(host, 'rev-parse', commit + '^1') != parent:
            raise Refused('%s is not a squash merge onto the previous main' % commit[:12])
        pulls = [p for p in github.pulls(commit) if p.get('merged_at') and p.get('merge_commit_sha') == commit
                 and (p.get('base') or {}).get('ref') == 'main']
        if len(pulls) != 1:
            raise Refused('%s was not merged through exactly one pull request into main' % commit[:12])
        head = pulls[0]['head']['sha']
        runs = github.check_runs(head)
        bindings = set()
        for name in CHECKS:
            mine = [r for r in runs if r.get('name') == name and (r.get('app') or {}).get('id') == app]
            if not mine:
                raise Refused('pull request #%s has no %s check from the protected App' % (pulls[0]['number'], name))
            newest = max(mine, key=lambda r: r.get('completed_at') or '')
            if newest.get('status') != 'completed' or newest.get('conclusion') != 'success':
                raise Refused('pull request #%s: %s is not a completed success' % (pulls[0]['number'], name))
            bindings.add(newest.get('external_id'))
        if len(bindings) != 1 or not str(next(iter(bindings))).startswith('nortropic-check/1:'):
            raise Refused('pull request #%s: the two checks do not carry one binding' % pulls[0]['number'])
        binding = next(iter(bindings))
        if binding not in requests:
            raise Refused('pull request #%s: no sealed issuer request on this host binds its checks' % pulls[0]['number'])
        ident, request = requests[binding]
        task, subject, review = request['task'], request['subject'], request['review']
        runs_of = subject.get('implementation_runs') or []
        if (task.get('target') != target_name or subject.get('candidate') != head
                or review.get('verdict') != 'approved' or review.get('blocking_findings') != []
                or not review.get('reviewer_run') or review.get('reviewer_run') in runs_of):
            raise Refused('pull request #%s: the sealed request %s is not an approved separate review of its head'
                          % (pulls[0]['number'], ident))
        tree = github.tree(commit)
        if github.tree(head) != tree or git(host, 'rev-parse', commit + '^{tree}') != tree:
            raise Refused('pull request #%s: the merged tree is not the reviewed head tree' % pulls[0]['number'])
        proven.append({'commit': commit, 'pull_request': pulls[0]['number'], 'head': head, 'binding': binding,
                       'sealed_request': ident, 'reviewer_run': review.get('reviewer_run'), 'tree': tree})
        parent = commit
    return proven


# ------------------------------------------------------------------------------------------------ the new release
PROBE = r'''
import asyncio, base64, json, sys
from pathlib import Path
code = Path(sys.argv[1]).resolve(); sys.path.insert(0, str(code))
from runtime import release
assert Path(release.__file__).resolve().is_relative_to(code), release.__file__
what = sys.argv[2]
if what == 'guards':
    print(json.dumps(release.instruction_guards()))
elif what == 'guard_differences':
    print(json.dumps(release.guard_differences(json.loads(Path(sys.argv[3]).read_text())['instruction_guards'])))
elif what == 'ap10_command':
    from runtime import profile
    print(json.dumps(profile.command(Path(sys.argv[3]), writable=False)))
elif what == 'plist':
    from scripts.install_ap10 import plist
    print(json.dumps(base64.b64encode(plist(Path(sys.argv[3]))).decode()))
elif what == 'startup':
    from runtime import daemon
    from runtime.run import check_unfinished_writers
    from runtime.private_stage import check_private_processes
    config = json.loads(Path(sys.argv[3]).read_text()); config['directory'] = str(Path(sys.argv[3]).parent)
    async def go():
        from temporalio.client import Client
        client = await Client.connect('127.0.0.1:7339', namespace='nortropic-runtime')
        found = await daemon.delivered_histories(client, config)
        for name in daemon.HISTORICAL:
            daemon.archived_delivery(config, name)
        check_unfinished_writers(); check_private_processes()
        return found
    print(json.dumps(asyncio.run(go()), default=str))
elif what == 'offline':
    from runtime import daemon
    from runtime.run import check_unfinished_writers
    from runtime.private_stage import check_private_processes
    config = json.loads(Path(sys.argv[3]).read_text()); config['directory'] = str(Path(sys.argv[3]).parent)
    for name in daemon.HISTORICAL:
        daemon.archived_delivery(config, name)
    check_unfinished_writers(); check_private_processes()
    print(json.dumps(True))
'''


def probe(host, code_root, what, *args, timeout=300):
    """A question answered by the given release's OWN code, in its own interpreter process."""
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(Path.home()), 'LC_ALL': 'C', 'NR_HOST_ROOT': str(host),
           'PYTHONDONTWRITEBYTECODE': '1'}
    for key in ('USER', 'LOGNAME', 'TMPDIR'):
        if os.environ.get(key):
            env[key] = os.environ[key]
    python = str(Path(host) / '.runtime/temporal-venv/bin/python')
    done = subprocess.run([python, '-B', '-c', PROBE, str(code_root), what, *map(str, args)], cwd=str(code_root),
                          env=env, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError('%s under %s: %s' % (what, code_root, done.stderr.strip()[-600:]))
    return json.loads(done.stdout)


def only_code_differs(old, new):
    """Equal once the Runtime revision, the runtime/ files and the guards (computed by each release's own code) are set
    aside. The office revision, the choice, context, history archives and everything else are carried unchanged."""
    a, b = copy.deepcopy(old), copy.deepcopy(new)
    for value in (a, b):
        value.pop('runtime_revision', None)
        value.pop('instruction_guards', None)
        value['files'] = {k: v for k, v in value['files'].items() if not k.startswith('runtime/')}
    if a != b:
        changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        raise Refused('the new configuration differs from the active one beyond the Runtime code: ' + ', '.join(changed))


def released(name):
    return name in ('AGENTS.md', 'docs/runtime-v0.1.md') or name.startswith(('runtime/', 'scripts/', 'tools/', 'acceptance/', 'config/'))


def changed_files(host, active, target):
    names = git(host, 'diff', '--name-only', active, target).split('\n')
    return sorted('runtime/' + n for n in names if n and released(n))


def code_is_the_revision(host, revision, directory, files):
    """The staged release's Runtime code is git at the proven revision, byte for byte: the same released names, each the
    same blob. Binds what is activated to what the chain proved, whatever wrote the staged record."""
    listed = {}
    for row in git(host, 'ls-tree', '-r', revision).split('\n'):
        meta, name = row.split('\t', 1)
        if released(name):
            listed['runtime/' + name] = meta.split()[2]
    staged = sorted(name for name in files if name.startswith('runtime/'))
    if sorted(listed) != staged:
        raise Refused('the staged release holds other Runtime files than the proven revision %s' % revision[:12])
    done = subprocess.run(['git', '-C', str(host), 'hash-object', '--no-filters', '--stdin-paths'],
                          input=''.join(str(Path(directory) / name) + '\n' for name in staged), capture_output=True,
                          text=True, timeout=300, env={**GIT_ENV, 'HOME': str(Path.home())})
    if done.returncode != 0 or done.stdout.split() != [listed[name] for name in staged]:
        raise Refused('the staged Runtime code is not byte for byte the proven revision %s' % revision[:12])


def stage(host, mc, copy_code, target, proven, stamp=None):
    """The new release: Runtime code copied from git at the target, everything else carried from the active release."""
    old, raw = mc.active_release(host); config = json.loads(raw); directory = Path(old['directory'])
    stamp = stamp or now().strftime('%Y%m%dT%H%M%SZ')
    releases = Path(old['directory']).parent
    new_directory = releases / ('%s-%s-code-%s' % (target, config['office_revision'], stamp))
    record_directory = paths(host)['records'] / stamp
    for existing in (new_directory, record_directory):
        if existing.exists() or existing.is_symlink():
            raise Wait('%s exists already; it is never overwritten' % existing)
    record_directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    new_directory.mkdir(mode=0o700); record_directory.mkdir(mode=0o700)
    files = {'runtime/' + name: digest for name, digest in copy_code(host, target, new_directory / 'runtime').items()}
    for name, expected in sorted(config['files'].items()):
        if name.startswith('runtime/'):
            continue
        source, copied = directory / name, new_directory / name
        data = source.read_bytes()
        if source.is_symlink() or sha_bytes(data) != expected:
            raise Refused('carried file differs in the active release: ' + name)
        copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with copied.open('xb') as stream:
            stream.write(data)
        copied.chmod(source.stat().st_mode & 0o777)
        files[name] = expected
    new = copy.deepcopy(config); new['runtime_revision'] = target; new['files'] = files
    new['instruction_guards'] = probe(host, new_directory / 'runtime', 'guards')
    only_code_differs(config, new)
    path = new_directory / 'config.json'
    with path.open('x') as stream:
        stream.write(json.dumps(new, indent=2) + '\n')
    path.chmod(0o400)
    mc.verify_files(new_directory, new['files'], 'the new release differs: ')
    present = {p.relative_to(new_directory).as_posix() for p in new_directory.rglob('*') if not p.is_dir()}
    if present != set(new['files']) | {'config.json'}:
        raise Refused('the new release holds other files than its configuration binds')
    choice = mc.choice_of(config)
    record = {'staged_at': now().isoformat(), 'tool_sha256': sha_bytes(Path(__file__).read_bytes()),
              'kind': 'code', 'old_config': str(directory / 'config.json'), 'old_config_sha256': old['config_sha256'],
              'config': str(path), 'sha256': sha_bytes(path.read_bytes()),
              'runtime_revision': target, 'old_runtime_revision': config['runtime_revision'],
              'office_revision': config['office_revision'], 'proven': proven,
              'changed_runtime_files': sorted(k for k in files if k.startswith('runtime/') and config['files'].get(k) != files[k]),
              'removed_runtime_files': sorted(k for k in config['files'] if k.startswith('runtime/') and k not in files),
              # model_choice.forward reports these; a code transition carries the choice unchanged
              'previous_selection': config['development'].get('models'), 'selection': new['development'].get('models'),
              'models_before': choice['models'], 'models_after': choice['models'], 'efforts_before': choice['efforts'],
              'efforts_after': choice['efforts'], 'executors_before': choice['executors'], 'executors': choice['executors'],
              'watch_before': choice['watch'], 'watch_after': choice['watch'], 'request_id': 'code-' + target}
    mc.write(record_directory / 'staged.json', record)
    return record_directory, record


def latest_for(host, target, old_sha):
    root = paths(host)['records']
    for directory in sorted(root.glob('2*Z'), reverse=True) if root.is_dir() else ():
        try:
            staged = json.loads((directory / 'staged.json').read_text())
        except (OSError, ValueError):
            continue
        if (staged.get('runtime_revision') == target and staged.get('old_config_sha256') == old_sha
                and staged.get('tool_sha256') == sha_bytes(Path(__file__).read_bytes())
                and Path(staged['config']).is_file() and sha_bytes(Path(staged['config']).read_bytes()) == staged['sha256']):
            return directory, staged
    return None


def static_checks(host, mc, record_directory, staged):
    """What cannot change while the two releases stay as staged, measured once per staged record: the AP-10 command, the
    service definition and the web tools under the new code. A difference is the owner's (OwnerNeeded)."""
    path = record_directory / 'static.json'
    try:
        value = json.loads(path.read_text())
        if value.get('sha256') == staged['sha256'] and value.get('old_config_sha256') == staged['old_config_sha256']:
            return value
    except (OSError, ValueError):
        pass
    new_path = Path(staged['config']); new_code = new_path.parent / 'runtime'
    old_code = Path(staged['old_config']).parent / 'runtime'
    with tempfile.TemporaryDirectory() as workspace:
        if probe(host, old_code, 'ap10_command', workspace) != probe(host, new_code, 'ap10_command', workspace):
            raise OwnerNeeded('the AP-10 command differs under the new code')
    if base64.b64decode(probe(host, new_code, 'plist', new_path)) != mc.plist(new_path):
        raise OwnerNeeded('the service definition differs under the new code')
    tools = subprocess.run([str(Path(host) / '.runtime/temporal-venv/bin/python'), '-B',
                            str(new_code / 'scripts/install_web_tools.py'), '--check'], cwd=str(new_code),
                           env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(Path.home()), 'LC_ALL': 'C',
                                'NR_HOST_ROOT': str(host), 'PYTHONDONTWRITEBYTECODE': '1'},
                           capture_output=True, text=True, timeout=300)
    if tools.returncode != 0:
        raise OwnerNeeded('the web profiles\' pinned tools do not verify under the new code: ' + (tools.stdout + tools.stderr)[-300:])
    value = {'sha256': staged['sha256'], 'old_config_sha256': staged['old_config_sha256'], 'checked_at': now().isoformat(),
             'ap10_command_unchanged': True, 'service_definition_unchanged': True, 'web_tools_verified': True}
    mc.replace(path, (json.dumps(value, indent=2) + '\n').encode())
    return value


async def preconditions(host, mc, record_directory, staged):
    """model_choice's preconditions for a code change, each measured now. Raises SystemExit (refuse), OwnerNeeded or Refused."""
    if staged.get('tool_sha256') != sha_bytes(Path(__file__).read_bytes()):
        mc.refuse('this tool is not the one that staged the transition')
    new_path = Path(staged['config'])
    if new_path.is_symlink() or not new_path.is_file() or sha_bytes(new_path.read_bytes()) != staged['sha256']:
        mc.refuse('the staged configuration changed since staging')
    old, raw = mc.active_release(host); active = json.loads(raw)
    if old['config_sha256'] != staged['old_config_sha256']:
        mc.refuse('the active selection changed since staging')
    new = json.loads(new_path.read_text()); only_code_differs(active, new)
    mc.verify_files(new_path.parent, new['files'], 'staged file differs: ')
    code_is_the_revision(host, staged['runtime_revision'], new_path.parent, new['files'])
    if mc.choice_of(new) != mc.choice_of(active):
        raise Refused('the choice would change; a code transition carries it unchanged')
    static_checks(host, mc, record_directory, staged)
    new_code, new_plist = new_path.parent / 'runtime', mc.plist(new_path)
    client = await mc.temporal()
    async for execution in client.list_workflows('ExecutionStatus = "Running"'):
        if execution.id.startswith(('office-ap11', 'ap11-')):
            mc.refuse('an AP-11 execution is running (%s); a code transition waits' % execution.id)
    before = await mc.raw_schedule(client)
    if before['info'].get('running_workflows'):
        mc.refuse('an AP10 watch run is in progress; activate later')
    upcoming = (before['info'].get('future_action_times') or [None])[0]
    if not upcoming or (datetime.fromisoformat(upcoming.replace('Z', '+00:00')) - now()).total_seconds() < mc.LEAD_SECONDS:
        mc.refuse('the next AP10 run is less than 20 minutes away (or unknown); activate later')
    reference, old_arg = await mc.schedule_argument(client)
    if old_arg != [{'config_sha256': old['config_sha256'], 'mode': 'daily', 'obligation': mc.WATCH}]:
        mc.refuse('the AP10 schedule action is not bound to the active selection')
    old_service = mc.read_json(mc.paths(host)['service'], 'service receipt')
    if old_service.get('config_sha256') != old['config_sha256'] or len(mc.alive(old_service)) != 3:
        mc.refuse('the running service is not the recorded one')
    running = mc.web_profile_runs()
    if running:
        mc.refuse('a web profile run is in progress (%s); activate later' % ', '.join(running))
    busy, idle = await mc.work_in_progress(client)
    if busy:
        mc.refuse('work is in progress in the engine: %s; activate later' % json.dumps(busy))
    differences = probe(host, new_code, 'guard_differences', new_path)
    if differences:
        mc.refuse('native instruction inputs differ from what the new code binds: %s' % differences)
    try:
        startup = probe(host, new_code, 'startup', new_path)
    except Exception as error:
        mc.refuse('the NEW release could not pass its own daemon start requirements right now: %s' % error)
    if not mc.startable(old):
        mc.refuse('the active release could not start again after a stop, so there would be no way back; nothing was changed')
    return dict(new_path=new_path, new=new, old=old, new_plist=new_plist, client=client, before=before,
                reference=reference, old_arg=old_arg, old_service=old_service, busy=busy, idle=idle,
                next_ap10=upcoming, startup=startup)


async def activate(host, mc, record_directory, staged):
    """model_choice's activation of exactly this staged record: backup, stop, select, start, confirm or restore, rebind."""
    p = await preconditions(host, mc, record_directory, staged)
    target = mc.paths(host)['plist']
    mc.say('Ny Runtime-version: %s -> %s (%s). Valet av modeller och bevakning följer med oförändrat.'
           % (staged['old_runtime_revision'][:12], staged['runtime_revision'][:12],
              ', '.join('#%s' % row['pull_request'] for row in staged['proven'])))
    directory = record_directory / ('activation-' + now().strftime('%Y%m%dT%H%M%SZ')); directory.mkdir(mode=0o700)
    summary = {'would_activate': staged['sha256'], 'replacing': p['old']['config_sha256'],
               'runtime_revision': {'from': staged['old_runtime_revision'], 'to': staged['runtime_revision']},
               'proven': staged['proven'], 'idle_development_workflows': p['idle'], 'next_ap10_run': p['next_ap10'],
               'new_daemon_start_requirements_now': p['startup']}
    mc.write(directory / 'before.json', summary); mc.write(directory / 'before-schedule.json', p['before'])
    mc.write(directory / 'old-service.json', p['old_service']); mc.write(directory / 'staged.json', staged)
    for name, source in (('old-active.json', mc.paths(host)['active']), ('old-config.json', Path(p['old']['config_path'])),
                         ('old.plist', target)):
        (directory / name).write_bytes(Path(source).read_bytes())
    (directory / 'new.plist').write_bytes(p['new_plist'])
    try:
        mc.write(directory / 'online-backup.json', mc.backup(host, directory / 'before-online.sqlite'))
    except Exception as error:
        mc.refuse('backup before the stop failed (%r); nothing was stopped or selected' % error)
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(number, signal.SIG_IGN)
    busy, _ = await mc.work_in_progress(p['client'])
    if busy:
        mc.refuse('work started in the engine meanwhile: %s; nothing was stopped or selected' % json.dumps(busy))
    state = {'staged': staged, 'old_config_sha256': p['old']['config_sha256'], 'old_service': p['old_service'],
             'old_arg': p['old_arg'], 'stop_completed': False, 'old_worker_gone_at': None}
    mc.write(directory / 'state.json', state)
    progress = {'point': 'stop requested; nothing selected'}
    try:
        await mc.stop_service(state, directory, progress)
        state['stop_completed'] = True
        mc.replace(directory / 'state.json', (json.dumps(state, indent=2, default=str) + '\n').encode())
        await mc.forward(host, state, directory, progress)
    except SystemExit:
        raise
    except BaseException as error:
        mc.unexpected(error, progress, directory)


# ------------------------------------------------------------------------------------------------ the agent's look
def read_status(host):
    try:
        value = json.loads(paths(host)['status'].read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_status(host, mc, **fields):
    value = {'schema': STATUS_SCHEMA, 'checked_at': now().isoformat(), **fields}
    mc.replace(paths(host)['status'], (json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n').encode())
    return value


async def quiet(mc, margin):
    """Wait (raise Wait) while the AP-10 watch runs or its next run is closer than the 20-minute lead plus margin
    (model_choice.ap10_quiet, the same rule the measurements keep)."""
    try:
        return await mc.ap10_quiet(margin)
    except SystemExit as refusal:
        raise Wait(str(refusal))


def rehearsal_passed(record_directory, staged):
    try:
        value = json.loads((record_directory / 'rehearsal.json').read_text())
    except (OSError, ValueError):
        return False
    return value.get('passed') is True and value.get('new_config_sha256') == staged['sha256'] \
        and value.get('old_config_sha256') == staged['old_config_sha256']


async def automatic(host, mc, github=None, rehearse=None, copy_code=None, check_binding=None, target_name=REPOSITORY):
    """One look: the newest integrated and reviewed Runtime main, activated when Runtime is idle, or why not."""
    github = github or GitHub()
    if rehearse is None:
        from scripts import code_rehearsal
        rehearse = code_rehearsal.rehearse
    if copy_code is None:
        from scripts.install_ap10 import copy_code
    if check_binding is None:
        from runtime.integration import check_binding
    handle = paths(host)['lock'].open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close(); return None
    with handle:
        try:
            old, raw = mc.active_release(host)
        except SystemExit as refusal:
            return write_status(host, mc, state='refused', reason=str(refusal), target_revision=None)
        config = json.loads(raw)
        base = {'active_config_sha256': old['config_sha256'], 'active_revision': config['runtime_revision']}
        previous = read_status(host)
        try:
            target = github.main_head()
        except (Wait, Refused, KeyError, ValueError) as error:
            return write_status(host, mc, state='waiting', reason=str(error), target_revision=None, **base)
        base['target_revision'] = target
        if target == config['runtime_revision']:
            carried = {k: previous[k] for k in ('activated_at', 'record', 'proven') if previous and previous.get(k)
                       and previous.get('target_revision') == target}
            return write_status(host, mc, state='current', reason=None, **base, **carried)
        if (previous and previous.get('target_revision') == target and previous.get('state') in FINAL
                and previous.get('active_config_sha256') == old['config_sha256']):
            return previous
        if previous and previous.get('target_revision') == target and previous.get('state') == 'activating':
            return write_status(host, mc, state='interrupted', record=previous.get('record'), **base,
                                reason='an automatic activation of this revision was cut off before it reported; nothing more '
                                       'is tried automatically. Read the record; if the service is down, run '
                                       'model_choice.py code-forward in your own Terminal')
        record_directory = staged = None
        try:
            try:
                git(host, 'fetch', '--quiet', 'origin', 'main', timeout=180)
            except (subprocess.SubprocessError, OSError) as error:
                raise Wait('the new revision is not fetched (%r)' % error)
            if git(host, 'rev-parse', 'origin/main') != target:
                raise Wait('main moved while this look ran')
            proven = verify_chain(host, config['runtime_revision'], target, github, check_binding, target_name)
            owners = [n for n in changed_files(host, config['runtime_revision'], target) if n in OWNER_FILES]
            if owners:
                raise OwnerNeeded('the release changes the activator or the service definition (%s); the owner activates '
                                  'it with a controlled transition' % ', '.join(owners))
            found = latest_for(host, target, old['config_sha256'])
            record_directory, staged = found if found else stage(host, mc, copy_code, target, proven)
            static_checks(host, mc, record_directory, staged)
            if not rehearsal_passed(record_directory, staged):
                await quiet(mc, REHEARSAL_MARGIN)
                await preconditions(host, mc, record_directory, staged)      # the rehearsal, too, only while Runtime is idle
                attempt = now().strftime('%Y%m%dT%H%M%SZ')
                # rehearse runs an event loop of its own (asyncio.run); this look already runs in one (model_choice.tick),
                # so the rehearsal runs in a thread of its own (D045).
                result = await asyncio.to_thread(rehearse, host, Path(staged['old_config']).parent, Path(staged['config']).parent,
                                                 record_directory / ('rehearsal-' + attempt))
                result = {**result, 'new_config_sha256': staged['sha256'], 'old_config_sha256': staged['old_config_sha256']}
                mc.replace(record_directory / 'rehearsal.json',       # a waited rehearsal is run again: never 'x'
                           (json.dumps(result, indent=2, default=str) + '\n').encode())
                if result.get('waiting') is True:
                    raise Wait('the rehearsal waits: %s' % result.get('reason'))
                if result.get('passed') is not True:
                    raise Refused('the isolated rehearsal of the new release did not pass: %s' % result.get('reason'))
            await preconditions(host, mc, record_directory, staged)
        except Wait as error:
            return write_status(host, mc, state='waiting', reason=str(error), record=str(record_directory or '') or None, **base)
        except OwnerNeeded as error:
            return write_status(host, mc, state='owner_needed', reason=str(error), record=str(record_directory or '') or None, **base)
        except Refused as error:
            return write_status(host, mc, state='refused', reason=str(error), record=str(record_directory or '') or None, **base)
        except SystemExit as refusal:
            text = str(refusal)
            return write_status(host, mc, state='waiting' if any(f in text for f in WAITING) else 'refused', reason=text,
                                record=str(record_directory or '') or None, **base)
        except Exception as error:
            return write_status(host, mc, state='waiting', reason='unexpected before any stop: %r' % (error,),
                                record=str(record_directory or '') or None, **base)
        write_status(host, mc, state='activating', reason=None, record=str(record_directory), proven=staged['proven'], **base)
        try:
            await activate(host, mc, record_directory, staged)
        except (OwnerNeeded, Refused) as error:                             # raised by the re-check, before any stop
            return write_status(host, mc, state='owner_needed' if isinstance(error, OwnerNeeded) else 'refused',
                                reason=str(error), record=str(record_directory), proven=staged['proven'], **base)
        except SystemExit as refusal:
            state = mc.outcome(host, record_directory, staged, str(refusal))
            if state in ('waiting', 'refused'):                              # nothing was stopped: this tool's words decide
                state = 'waiting' if any(f in str(refusal) for f in WAITING) else 'refused'
            now_sha = mc.active_release(host)[0]['config_sha256']
            return write_status(host, mc, state=state, reason=str(refusal), record=str(record_directory), proven=staged['proven'],
                                **{**base, 'active_config_sha256': now_sha},
                                **({'activated_at': now().isoformat()} if state == 'activated' else {}))
        except Exception as error:
            state = mc.outcome(host, record_directory, staged, 'unexpected: %r' % (error,), unexpected=True)
            now_sha = mc.active_release(host)[0]['config_sha256']
            return write_status(host, mc, state=state, reason='unexpected: %r' % (error,), record=str(record_directory),
                                proven=staged['proven'], **{**base, 'active_config_sha256': now_sha})
        return write_status(host, mc, state='activated', reason=None, record=str(record_directory), proven=staged['proven'],
                            activated_at=now().isoformat(),
                            **{**base, 'active_config_sha256': mc.active_release(host)[0]['config_sha256']})


async def owner_forward(host, mc):
    """The owner's continuation of an automatic code activation whose stop completed (model_choice.py code-forward)."""
    root = paths(host)['records']
    records = sorted(d for d in root.glob('2*Z') if (d / 'staged.json').is_file()) if root.is_dir() else []
    if not records:
        mc.refuse('no automatic code transition is recorded')
    record_directory = records[-1]; staged = json.loads((record_directory / 'staged.json').read_text())
    directory = mc.latest_activation(record_directory); state = json.loads((directory / 'state.json').read_text())
    if staged.get('tool_sha256') != sha_bytes(Path(__file__).read_bytes()):
        mc.refuse('this tool is not the one that staged the transition')
    if state['staged'] != staged or sha_bytes(Path(staged['config']).read_bytes()) != staged['sha256']:
        mc.refuse('the saved state does not belong to the newest staged code transition')
    if not state.get('stop_completed') and mc.alive(state['old_service']):
        mc.refuse('the old service processes still live; forward is only for a stopped service')
    if mc.alive(mc.read_json(mc.paths(host)['service'], 'service receipt')):
        mc.refuse('service processes are alive; forward is only for a stopped service')
    new_path = Path(staged['config']); new = json.loads(new_path.read_text())
    mc.verify_files(new_path.parent, new['files'], 'staged file differs: ')
    try:
        code_is_the_revision(host, staged['runtime_revision'], new_path.parent, new['files'])
    except Refused as error:
        mc.refuse(str(error))
    try:                                                    # model_choice.do_forward's offline checks, by the NEW code
        probe(host, new_path.parent / 'runtime', 'offline', new_path)
    except Exception as error:
        mc.refuse('the staged release could not pass its offline daemon start requirements: %s' % error)
    state['old_worker_gone_at'] = now().isoformat()
    mc.replace(directory / 'state.json', (json.dumps(state, indent=2, default=str) + '\n').encode())
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(number, signal.SIG_IGN)
    progress = {'point': 'forward requested on a stopped service'}
    try:
        await mc.forward(host, state, directory, progress)
    except SystemExit:
        raise
    except BaseException as error:
        mc.unexpected(error, progress, directory)
