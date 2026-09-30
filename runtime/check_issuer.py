"""Host-owned execution of frozen acceptance and App check issuance.

A separately adopted holder seals relevant input/expected-output cases outside
candidate access. Candidate behavior runs in the native sandbox; this host
process compares its data with the private expectation, then reads the App key.
"""
from datetime import datetime, timezone
from contextlib import ExitStack
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import uuid
import urllib.error
import urllib.request

from .integration import GateClosed, Publisher, digest, require_gate, check_binding
from .release import ROOT
from .failure_ledger import Ledger, Refused as LedgerRefused, require_acl
from .measurement_observer import private_directory, private_output, write_owner
from scripts.bounded import stop_group

NAMES = ('runtime/tests', 'runtime/review')
CODE = ('runtime/__init__.py', 'runtime/check_issuer.py', 'runtime/integration.py',
        'runtime/host_publication.py', 'runtime/decision_guard.py', 'runtime/content_guard.py', 'runtime/failure_ledger.py',
        'runtime/profile.py', 'runtime/release.py', 'runtime/targets.py',
        'runtime/construction_registration.py', 'runtime/development_binding.py',
        'runtime/development_scope.py', 'runtime/snapshot.py',
        'runtime/claude_profile.py', 'runtime/codex_pin.py',
        'scripts/probe_bridge.py', 'scripts/publish_construction.py',
        'scripts/publish_digitala.py', 'scripts/bounded.py', 'scripts/matning_provanvandare.py',
        'runtime/measurement_observer.py', 'scripts/measurement_queue.py')
TARGETS = ('Nortropic/nortropic-runtime', 'Nortropic/nortropic-projektkontor',
           'Nortropic/nortropic-digitala', 'Nortropic/nortropic-kundstart')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binding(task, subject, review):
    """Public opaque identity; no private prompt, path or reviewer prose."""
    return check_binding(task, subject, review)


def private_bytes(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise GateClosed('Issuer authority must not use symlinks')
    try:
        for parent in path.parents:
            info=parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid())
                    or info.st_mode&0o022 and not (info.st_uid==0 and info.st_mode&stat.S_ISVTX)):
                raise GateClosed('Unsafe issuer authority ancestor')
            require_acl(parent)
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or stat.S_IMODE(info.st_mode) not in (0o400,0o600)):
            raise GateClosed('Issuer authority must be a private owner file')
        require_acl(path,private=True)
        identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            if identity(os.fstat(fd))!=identity(info):raise GateClosed('Issuer authority changed before read')
            data=stream.read()
            if identity(os.fstat(fd))!=identity(info) or identity(path.lstat())!=identity(info):
                raise GateClosed('Issuer authority changed during read')
        return data
    except LedgerRefused as error:
        raise GateClosed(str(error)) from None


def read_object(path):
    value = json.loads(private_bytes(path))
    if not isinstance(value, dict):
        raise GateClosed('Issuer authority must be an object')
    return value


def git(repo, *args):
    from .integration import publication_git
    return publication_git(repo, *args, text=False)


def current_main(repository):
    if repository not in TARGETS:
        raise GateClosed('Unknown issuer repository')
    # Existing publisher read authority; the new App needs no Contents access.
    result = subprocess.run(['gh', 'api', 'repos/' + repository + '/commits/main', '--jq', '.sha'],
                            check=True, capture_output=True, text=True, timeout=30)
    value = result.stdout.strip()
    if not re.fullmatch('[0-9a-f]{40}', value):
        raise GateClosed('Current main readback is malformed')
    return value


def construction_import_root(wrapper, host=ROOT):
    """Only integrated main or the existing holder's separately adopted copy.

    This selects code, not a candidate and not a permission to publish. All suite,
    preserved-host, dry-run, exact-source and server gates still run in the wrapper.
    """
    host, wrapper = Path(host).resolve(), Path(wrapper).resolve()
    if wrapper == host / 'scripts/publish_construction.py':
        return host, False
    issuer = HostIssuer(host)
    config = issuer.authority()
    adopted = Path(config['adopted_code_root'])
    if (adopted.parent != issuer.home / 'adopted'
            or not re.fullmatch('[0-9a-f]{40}', adopted.name)
            or wrapper != adopted / 'scripts/publish_construction.py'):
        raise GateClosed('Construction bootstrap must use the separately adopted private holder copy')
    return adopted, True


def frozen_snapshot(repo, candidate, destination):
    """Read Git blobs only; no mutable checkout, links, hooks, caches or .git."""
    files = {}
    for entry in git(repo, 'ls-tree', '-rz', candidate).split(b'\0'):
        if not entry:
            continue
        header, name = entry.split(b'\t', 1)
        mode, kind, oid = header.split()
        name = name.decode()
        rel = Path(name)
        if (mode not in (b'100644', b'100755') or kind != b'blob'
                or rel.is_absolute() or '..' in rel.parts or rel.parts[0] == '.git'):
            raise GateClosed('Issuer accepts regular Git source files only')
        data = git(repo, 'cat-file', 'blob', oid.decode())
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o500 if mode == b'100755' else 0o400)
        files[name] = sha(data)
    if not files:
        raise GateClosed('Empty candidate snapshot')
    return files


def run_isolated(workspace, program, input_data=b'', timeout=120):
    """Execute no candidate code in the credential-bearing host process."""
    from .profile import sandbox_command
    home = workspace / '.scratch' / 'home'
    (home / '.codex').mkdir(parents=True, exist_ok=True)
    (home / '.codex/config.toml').write_text('')
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(home),
           'TMPDIR': str(workspace / '.scratch'), 'LANG': 'C',
           'PYTHONDONTWRITEBYTECODE': '1', 'NR_HOST_ROOT': str(ROOT)}
    command = sandbox_command(workspace, [str(ROOT / '.runtime/temporal-venv/bin/python'), '-I', '-B',
                                          str(program), str(workspace / 'source')])
    # Extend only the read table for pinned interpreters/CLIs needed by regression
    # tests. Host evidence, keychain, real HOME, App key and Temporal remain denied.
    index = next(i for i, value in enumerate(command) if value.startswith('permissions.nr.filesystem='))
    from . import claude_profile, codex_pin     # the pinned programs, from their one place each (D046, D047)
    extra = {str(ROOT / '.runtime/temporal-venv'): 'read',
             str(ROOT / '.runtime/bin' / ('claude-' + claude_profile.VERSION)): 'read',
             str((ROOT / codex_pin.BINARY).parent): 'read'}
    command[index] = command[index][:-1] + ',' + ','.join(json.dumps(k)+'='+json.dumps(v)
                                                        for k,v in extra.items()) + '}'
    timed_out, overflow = False, False
    streams = {'output': bytearray(), 'stderr': bytearray()}
    deadline = time.monotonic() + timeout
    pending = memoryview(input_data)
    reader = None
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        reader = selectors.DefaultSelector()
        reader.register(process.stdout, selectors.EVENT_READ, 'output')
        reader.register(process.stderr, selectors.EVENT_READ, 'stderr')
        reader.register(process.stdin, selectors.EVENT_WRITE, 'input')
        while reader.get_map():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            for key, _ in reader.select(min(0.2, max(0, deadline-time.monotonic()))):
                if key.data == 'input':
                    try:
                        pending = pending[os.write(key.fileobj.fileno(), pending[:4096]):] if pending else pending
                    except BrokenPipeError:
                        pending = memoryview(b'')
                    if not pending:
                        reader.unregister(key.fileobj)
                        key.fileobj.close()
                    continue
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    reader.unregister(key.fileobj)
                    continue
                streams[key.data].extend(chunk)
                if sum(map(len, streams.values())) > 8 * 1024 * 1024:
                    overflow = True
                    break
            if overflow:
                break
        if not timed_out and not overflow:
            try:
                process.wait(timeout=max(0.05, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        # A completed parent may have left a detached child in its group.
        try:
            try:removed = stop_group(process)
            finally:process.wait(timeout=10)
        finally:
            from contextlib import ExitStack
            with ExitStack() as handles:
                for stream in (process.stdin, process.stdout, process.stderr):handles.callback(stream.close)
                if reader is not None:handles.callback(reader.close)
        if not removed:
            raise GateClosed('Acceptance process group remains')
    output, stderr = bytes(streams['output']), bytes(streams['stderr'])
    return {'returncode': process.returncode, 'timed_out': timed_out,
            'output_limit_exceeded': overflow, 'output_sha256': sha(output), 'output': output,
            'stderr_sha256': sha(stderr), 'stderr': stderr}


def acceptance_contract(directory):
    """Only data is evaluated here; no candidate module is imported by the host."""
    raw = private_bytes(directory / 'acceptance.json')
    if len(raw) > 1024 * 1024:
        raise GateClosed('Frozen acceptance is too large')
    contract = json.loads(raw)
    if (not isinstance(contract, dict) or set(contract) != {'schema', 'cases'}
            or contract['schema'] != 'nortropic-behavior-acceptance/1'
            or not isinstance(contract['cases'], list) or not 1 <= len(contract['cases']) <= 32):
        raise GateClosed('Frozen acceptance needs bounded behavior cases')
    identifiers = set()
    for case in contract['cases']:
        if (not isinstance(case, dict) or set(case) != {'id', 'input', 'expected', 'timeout_seconds'}
                or not isinstance(case['id'], str) or not re.fullmatch('[a-z0-9-]{1,60}', case['id'])
                or case['id'] in identifiers or type(case['timeout_seconds']) is not int
                or not 1 <= case['timeout_seconds'] <= 120
                or len(json.dumps(case['input']).encode()) > 65536):
            raise GateClosed('Malformed frozen behavior case')
        identifiers.add(case['id'])
    return contract


def assert_behavior(measured, expected):
    """A successful process exit is necessary, never the acceptance decision."""
    if measured['returncode'] != 0 or measured['timed_out'] or measured.get('output_limit_exceeded'):
        raise GateClosed('Frozen acceptance failed or timed out; no successful check issued')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    try:
        actual = json.loads(measured['output'], object_pairs_hook=unique,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        # Canonical serialization keeps booleans distinct from numeric values.
        equal = json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError, UnicodeError):
        equal = False
    if not equal:
        raise GateClosed('Frozen acceptance behavior differs; no successful check issued')


def sealed_construction_suite(repository, candidate, discover, identifier, expected_count, issuer=None, phase='sealed'):
    """Consume an actual whole-suite measurement sealed by the existing holder.

Historical host-fixture tests cannot run in the model filesystem profile. They
are measured in a credential-free environment and sealed only after inspection,
never run as candidate code in this credential-bearing process. The issuer's
separate frozen acceptance ALWAYS executes in the native sandbox afterwards.
"""
    if (not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier) or discover not in ('scripts', 'tools', 'verktyg')
            or type(expected_count) is not int or expected_count <= 0):
        raise GateClosed('Invalid sealed-suite task/profile')
    issuer = issuer or HostIssuer()
    authority = issuer.authority()
    directory = issuer.home / 'requests' / identifier
    request = read_object(directory / 'request.json')
    record_bytes = private_bytes(directory / 'suite.json')
    record = json.loads(record_bytes)
    log = private_bytes(directory / 'suite.log')
    expected_command = ['python', '-B', '-m', 'unittest', 'discover', '-s', discover, '-p', 'test_*.py', '-v']
    if (request.get('suite_sha256') != sha(record_bytes)
            or record.get('schema') != 'nortropic-measured-suite/1'
            or record.get('candidate') != candidate
            or request.get('subject', {}).get('candidate') != candidate
            or record.get('tree') != git(repository, 'rev-parse', candidate+'^{tree}').decode().strip()
            or record.get('command') not in (expected_command, expected_command[:-1])
            or record.get('log_sha256') != sha(log) or record.get('returncode') != 0
            or record.get('test_count') != expected_count
            or record.get('credential_free_execution') is not True):
        raise GateClosed('Sealed suite does not bind an actual credential-free whole-candidate measurement')
    text = log.decode(errors='replace')
    counts = re.findall(r'^Ran (\d+) tests? in ', text, re.M)
    lines = [line for line in text.splitlines() if line.strip()]
    if counts != [str(expected_count)] or not lines or lines[-1] != 'OK':
        raise GateClosed('Sealed suite log does not show every expected test passing without skips')
    try:
        issuer.ledger.consume(candidate, phase, sha(record_bytes), record,
                              authority['code_sha256'])
    except LedgerRefused as error:
        raise GateClosed(str(error)) from None
    return subprocess.CompletedProcess(expected_command, record['returncode'], log)


class DigitalaPublisher(Publisher):
    """Fixed host entry, using the shared protected PR boundary; never publicera.py."""
    ALLOWED_TARGETS = ('Nortropic/nortropic-digitala',)

    def __init__(self, issuer):
        self.issuer = issuer
        self.REPOSITORY = self.ALLOWED_TARGETS[0]
        self.ORIGIN = 'https://github.com/' + self.REPOSITORY + '.git'
        self.repository = issuer.host.parent / 'nortropic-digitala'
        self.effect_guard = None

    def issue_checks(self, task, subject, review):
        return self.issuer.issue(self.repository, task, subject, review)

    def pins(self, candidate):
        """Verify profession coverage and hashes from Git data without candidate code."""
        def blob(path):
            if (not isinstance(path, str) or Path(path).is_absolute() or '..' in Path(path).parts
                    or not path or path.startswith('.git/')):
                raise GateClosed('Invalid Digitala profession path')
            return git(self.repository, 'show', candidate + ':' + path)
        steps = json.loads(blob('steg/steg.json'))
        paths = {entry['fil'] for step in steps['steg'].values() for entry in step['underlag']
                 if entry['klass'] == 'profession'}
        actual = {path: sha(blob(path)) for path in paths}
        pins = {}
        for line in blob('steg/PINNAR.sha256').decode().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            value, path = line.split('  ', 1)
            if path in pins or not re.fullmatch('[0-9a-f]{64}', value):
                raise GateClosed('Malformed or duplicate Digitala pin')
            pins[path] = value
        if not paths or pins != actual:
            raise GateClosed('Digitala profession pins differ from candidate Git bytes')
        return digest(pins)

    def publish_sealed(self, identifier):
        self.issuer.authority()
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier):
            raise GateClosed('Invalid sealed Digitala task')
        directory = self.issuer.home / 'requests' / identifier
        record = read_object(directory / 'request.json')
        task, subject, review = (record.get(key) for key in ('task', 'subject', 'review'))
        if not isinstance(task, dict) or task.get('target') != self.REPOSITORY or task.get('development'):
            raise GateClosed('Sealed task is not the fixed Digitala publication scope')
        self.issuer.request(identifier, task, subject, review)
        # The shared Publisher places this label in public PR text. Keep the
        # construction holder's existing restriction; raw private review paths
        # and prose remain in the sealed record and must never be emitted there.
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,119}', review['reviewer_run']):
            raise GateClosed('Digitala reviewer identity is not a safe public run label')
        sealed_construction_suite(self.repository, subject['candidate'], 'verktyg', identifier,
                                  task.get('expected_test_count'), issuer=self.issuer, phase='publication')
        pin_digest = self.pins(subject['candidate'])
        tests = {key: subject[key] for key in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
        # This gate input is derived only AFTER real holder-sealed measurement and
        # exact pin verification. No caller-supplied success can select this path.
        tests.update(scope='whole_task', terminal_status='completed', passed=True)
        destination = self.issuer.home / 'observations' / ('digitala-publication-' + uuid.uuid4().hex + '.json')
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        # Reconciliation of an already merged PR skips issue_checks, so this
        # entry must establish its own private boundary before any effects.
        from .measurement_observer import private_output
        with private_output(destination) as stream:
            receipt = self._publish(task, subject, tests, review)
            receipt.update(suite_sha256=record['suite_sha256'], pins_sha256=pin_digest)
            stream.write((json.dumps(receipt, indent=2)+'\n').encode())
            stream.flush(); os.fsync(stream.fileno())
        return receipt


class AppTransport:
    """Installation token kept only in memory; never an argv/env/log field."""
    def __init__(self, app_id, installation_id, key):
        self.app_id, self.installation_id, self.key = app_id, installation_id, key
        self.token = None

    @staticmethod
    def request(path, method='GET', body=None, token=None):
        url = 'https://api.github.com/' + path
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                   'User-Agent': 'Nortropic-host-check-issuer'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers,
                                                               method=method), timeout=30) as result:
                return json.load(result)
        except urllib.error.HTTPError as error:
            raise GateClosed('GitHub issuer request rejected: HTTP ' + str(error.code)) from None
        except urllib.error.URLError:
            raise GateClosed('GitHub issuer transport failed; reconcile before retry') from None

    def authenticate(self, repository):
        # Read the private file only after acceptance has finished and children ended.
        private_bytes(self.key)
        encode = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=')
        now = int(time.time())
        message = encode(b'{"alg":"RS256","typ":"JWT"}') + b'.' + encode(json.dumps(
            {'iat': now - 60, 'exp': now + 540, 'iss': str(self.app_id)}).encode())
        signed = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(self.key)],
                                input=message, capture_output=True, timeout=10)
        if signed.returncode:
            raise GateClosed('App signing failed')
        jwt = (message + b'.' + encode(signed.stdout)).decode()
        app = self.request('app', token=jwt)
        if (type(app.get('id')) is not int or app['id'] != self.app_id
                or app.get('permissions') != {'checks': 'write', 'metadata': 'read'}):
            raise GateClosed('Credential is not the adopted App')
        response = self.request('app/installations/' + str(self.installation_id) + '/access_tokens',
                                'POST', {'repositories': [repository.split('/')[1]],
                                         'permissions': {'checks': 'write'}}, jwt)
        if (response.get('permissions', {}).get('checks') != 'write'
                or any(k not in ('checks', 'metadata') for k in response.get('permissions', {}))
                or [r.get('full_name') for r in response.get('repositories', [])] != [repository]
                or not isinstance(response.get('token'), str) or not response['token']):
            raise GateClosed('Installation token lacks required Checks write scope')
        self.token = response['token']

    def api(self, repository, path, method='GET', body=None):
        return self.request('repos/' + repository + '/' + path, method, body, self.token)


class HostIssuer:
    def __init__(self, host=ROOT, ledger=None):
        self._ledger = ledger
        self.host = Path(host).resolve()
        self.home = self.host / '.runtime/ap11/check-issuer'

    @property
    def ledger(self):
        if self._ledger is None:
            self._ledger = Ledger()
        return self._ledger

    def authority(self):
        config = read_object(self.home / 'authority.json')
        code_root = Path(__file__).resolve().parents[1]
        if (code_root / 'scripts/__init__.py').exists():
            raise GateClosed('Unqualified scripts package initializer')
        if (config.get('schema') != 'nortropic-issuer-authority/1'
                or config.get('adopted_code_root') != str(code_root)
                or config.get('code_sha256') != {p: sha((code_root / p).read_bytes()) for p in CODE}
                or any(type(config.get(k)) is not int or config[k] <= 0
                       for k in ('app_id', 'installation_id'))):
            raise GateClosed('Issuer has not been adopted by the existing independent holder')
        review = read_object(self.home / 'adoption-review.json')
        if (sha(private_bytes(self.home / 'adoption-review.json')) != config.get('adoption_review_sha256')
                or review.get('verdict') != 'approved' or review.get('blocking_findings') != []
                or review.get('code_sha256') != config['code_sha256']
                or not review.get('reviewer_run') or review.get('reviewer_run') == review.get('implementation_run')):
            raise GateClosed('Issuer adoption lacks separate review of these exact bytes')
        return config

    def request(self, identifier, task, subject, review):
        if (not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier)
                or not isinstance(task, dict) or task.get('id') != identifier):
            raise GateClosed('Invalid issuer task identity')
        directory = self.home / 'requests' / identifier
        record = read_object(directory / 'request.json')
        now = datetime.now(timezone.utc)
        try:
            issued = datetime.fromisoformat(record['accepted_at'])
            until = datetime.fromisoformat(record['expires_at'])
            fresh = issued <= now < until and 0 < (until - issued).total_seconds() <= 86400
        except (ValueError, KeyError, TypeError):
            fresh = False
        if (not fresh or record.get('schema') != 'nortropic-issuer-request/1'
                or record.get('task') != task or record.get('subject') != subject
                or task.get('target') not in TARGETS or record.get('review') != review):
            raise GateClosed('Issuer request absent, stale or not bound to this task/candidate/review')
        source = private_bytes(directory / 'review.json')
        if (sha(source) != record.get('review_sha256') or json.loads(source) != review
                or record.get('probe_program_sha256') != sha(private_bytes(directory / 'probe.py'))
                or record.get('acceptance_contract_sha256') != sha(private_bytes(directory / 'acceptance.json'))):
            raise GateClosed('Frozen independent review or acceptance program changed')
        # Validate the existing whole-task gate; its target allowlist is not widened
        # for ordinary Runtime callers. This holder has four explicit repositories.
        proof = {k: subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
        proof.update(scope='whole_task', terminal_status='completed', passed=True)
        require_gate(task, subject, proof, review, allowed_targets=TARGETS)
        return directory, record

    def issue(self, repository, task, subject, review, transport=None):
        config = self.authority()
        directory, request = self.request(task['id'], task, subject, review)
        # Fixed repository mapping comes from the host, never from request paths.
        expected = self.host if task['target'] == TARGETS[0] else self.host.parent / task['target'].split('/')[1]
        repository = Path(repository).resolve()
        common = Path(git(repository, 'rev-parse', '--git-common-dir').decode().strip())
        expected_common = Path(git(expected, 'rev-parse', '--git-common-dir').decode().strip())
        if ((repository / common).resolve() != (expected / expected_common).resolve()
                or git(repository, 'rev-parse', '--show-toplevel').decode().strip() != str(repository)):
            raise GateClosed('Issuer candidate repository is not the fixed host mapping')
        head, base = subject['candidate'], subject['base']
        from .integration import require_git_origin
        require_git_origin(repository, 'https://github.com/' + task['target'] + '.git')
        if git(repository, 'rev-list', '--parents', '-n', '1', head).decode().split() != [head, base]:
            raise GateClosed('Issuer candidate is not one commit on accepted base')
        changes = set(filter(None, git(repository, 'diff', '--name-only', '--no-renames', '-z', base, head).decode().split('\0')))
        if not changes or not changes.issubset(set(task['allowed_paths'])):
            raise GateClosed('Issuer candidate exceeds accepted paths')
        from .content_guard import require_content, require_deletion, ContentRefused
        try:
            for path in changes:
                if not git(repository,'ls-tree','-z',head,'--',path):require_deletion(repository,base,path,task['target'])
            content_receipt = require_content(repository, base, head, task['target'])
            from .decision_guard import require_decisions
            decision_receipt = require_decisions(repository, base, head, task['target'])
        except ContentRefused as error:
            raise GateClosed(str(error)) from None
        client = transport or AppTransport(config['app_id'], config['installation_id'], self.home / 'app.pem')
        # Read-only main freshness before expensive work; PAT never issues a status.
        remote = current_main(task['target']) if transport is None else client.api(task['target'], 'commits/main').get('sha')
        if remote != base:
            raise GateClosed('Issuer base is no longer current main')
        contract = acceptance_contract(directory)
        work = self.home / 'workspaces'
        work.mkdir(mode=0o700, exist_ok=True)
        private_directory(work)
        if any(p.is_symlink() for p in (work, *work.parents)):
            raise GateClosed('Issuer workspace must not use symlinks')
        with tempfile.TemporaryDirectory(prefix='acceptance-', dir=work) as temporary:
            workspace = Path(temporary).resolve()
            (workspace / 'source').mkdir(); (workspace / '.scratch').mkdir()
            files = frozen_snapshot(repository, head, workspace / 'source')
            program = workspace / 'probe.py'
            program.write_bytes(private_bytes(directory / 'probe.py')); program.chmod(0o400)
            observations = self.home / 'observations'
            observations.mkdir(mode=0o700, exist_ok=True)
            private_directory(observations)
            attempt = observations / uuid.uuid4().hex
            attempt.mkdir(mode=0o700)
            private_directory(attempt)
            with ExitStack() as outputs:
                # Validate every inherited file ACL before the first candidate starts.
                logs={(case['id'],stream):outputs.enter_context(private_output(attempt/(case['id']+'.'+stream+'.log')))
                      for case in contract['cases'] for stream in ('output','stderr')}
                observation=outputs.enter_context(private_output(attempt/'measurement.json'))
                measurements = []
                cases = []
                try:
                    self.ledger.require_publishable(head)
                    run_id = self.ledger.begin(head, 'host', request['acceptance_contract_sha256'])
                except LedgerRefused as error:
                    raise GateClosed(str(error)) from None
                passed = False
                try:
                    for case in contract['cases']:
                        # The private expectation NEVER enters the readable workspace,
                        # argv, input, environment or candidate process. Only actual
                        # task input and the reviewed observation adapter cross over.
                        began = time.monotonic()
                        case_status = 'error'
                        try:
                            measured = run_isolated(workspace, program, json.dumps(case['input']).encode(),
                                                    timeout=case['timeout_seconds'])
                            for stream in ('output', 'stderr'):
                                log=logs[(case['id'],stream)]
                                log.write(measured.get(stream,b''));log.flush();os.fsync(log.fileno())
                            record = {'id': case['id'], 'task_sha256': digest(task), 'candidate': head,
                                      'probe_program_sha256': request['probe_program_sha256'],
                                      'acceptance_contract_sha256': request['acceptance_contract_sha256'],
                                      **{k:v for k,v in measured.items() if k not in ('output', 'stderr')}}
                            measurements.append(record)
                            observation.seek(0);observation.truncate()
                            observation.write((json.dumps(measurements,indent=2)+'\n').encode())
                            observation.flush();os.fsync(observation.fileno())
                            case_status = 'timeout' if measured.get('timed_out') else 'failure'
                            assert_behavior(measured, case['expected'])
                            case_status = 'success'
                        finally:
                            cases.append({'name': case['id'], 'file': 'probe.py', 'status': case_status,
                                          'seconds': time.monotonic() - began})
                    if any(sha((workspace / 'source' / p).read_bytes()) != value for p, value in files.items()):
                        raise GateClosed('Candidate snapshot changed during acceptance')
                    passed = True
                finally:
                    self.ledger.finish(run_id, cases, 0 if passed else 1, complete=passed)
        # Authority and request are re-read after candidate execution, before credentials.
        if self.authority() != config or self.request(task['id'], task, subject, review)[1] != request:
            raise GateClosed('Issuer authority changed during acceptance')
        client.authenticate(task['target'])
        remote = current_main(task['target']) if transport is None else client.api(task['target'], 'commits/main').get('sha')
        if remote != base:
            raise GateClosed('Issuer base changed during acceptance')
        opaque = binding(task, subject, review)
        receipt = {'schema': 'nortropic-issued-checks/1', 'binding': opaque, 'candidate': head,
                   'task_sha256': digest(task), 'acceptance_sha256': task['acceptance_sha256'],
                   'probe_program_sha256': request['probe_program_sha256'],
                   'acceptance_contract_sha256': request['acceptance_contract_sha256'],
                   'review_sha256': request['review_sha256'], 'decision_history':decision_receipt,
                   'measured_behavior_sha256': digest([{k:v for k,v in item.items() if k != 'stderr_sha256'}
                                                      for item in measurements]),
                   'app_id': config['app_id'], 'content_guard': content_receipt, 'checks': {}}
        runs = client.api(task['target'], 'commits/' + head + '/check-runs?filter=latest&per_page=100')
        if (not isinstance(runs, dict) or not isinstance(runs.get('check_runs'), list)
                or type(runs.get('total_count')) is not int or runs['total_count'] != len(runs['check_runs'])
                or not all(isinstance(r, dict) and isinstance(r.get('app'), dict) for r in runs['check_runs'])):
            raise GateClosed('Incomplete prior check readback; no blind reissue')
        for name in NAMES:
            # Acceptance and server reads take time. A later negative or
            # unfinished attempt must stop the next externally visible effect.
            try:
                self.ledger.require_publishable(head)
            except LedgerRefused as error:
                raise GateClosed(str(error)) from None
            matches = [r for r in runs['check_runs'] if r.get('name') == name
                       and r.get('app', {}).get('id') == config['app_id']]
            if len(matches) > 1:
                raise GateClosed('Ambiguous previous check; no blind reissue')
            if matches:
                run = matches[0]
            else:
                run = client.api(task['target'], 'check-runs', 'POST',
                                 {'name': name, 'head_sha': head, 'status': 'completed', 'conclusion': 'success',
                                  'external_id': opaque, 'output': {'title': 'Nortropic frozen acceptance and review',
                                  'summary': 'Host acceptance executed; independent review and exact task/candidate bound.'}})
            if (run.get('name') != name or run.get('head_sha') != head
                    or run.get('external_id') != opaque or type(run.get('app', {}).get('id')) is not int
                    or run['app']['id'] != config['app_id']
                    or run.get('status') != 'completed' or run.get('conclusion') != 'success'
                    or type(run.get('id')) is not int or run['id'] <= 0):
                raise GateClosed('Issued check differs from trusted task/candidate binding')
            receipt['checks'][name] = {'id': run['id'], 'app_id': config['app_id']}
        write_owner(attempt/'issued.json',receipt)
        return receipt
