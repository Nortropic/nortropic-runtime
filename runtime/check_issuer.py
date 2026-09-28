"""Host-owned execution of frozen acceptance and App check issuance.

No candidate-supplied result is accepted. A separately adopted holder seals a
request outside candidate access; this module measures its program in the native
no-network sandbox, then reads the App credential. It cannot adopt itself.
"""
from datetime import datetime, timezone
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

from .integration import GateClosed, digest, require_gate, check_binding
from .release import ROOT

NAMES = ('runtime/tests', 'runtime/review')
CODE = ('runtime/__init__.py', 'runtime/check_issuer.py', 'runtime/integration.py',
        'runtime/profile.py', 'runtime/release.py', 'runtime/targets.py',
        'runtime/claude_profile.py', 'scripts/probe_bridge.py', 'scripts/publish_construction.py')
TARGETS = ('Nortropic/nortropic-runtime', 'Nortropic/nortropic-projektkontor',
           'Nortropic/nortropic-digitala', 'Nortropic/nortropic-kundstart')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binding(task, subject, review):
    """Public opaque identity; no private prompt, path or reviewer prose."""
    return check_binding(task, subject, review)


def private_bytes(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise GateClosed('Issuer authority must not use symlinks')
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)):
        raise GateClosed('Issuer authority must be a private owner file')
    return path.read_bytes()


def read_object(path):
    value = json.loads(private_bytes(path))
    if not isinstance(value, dict):
        raise GateClosed('Issuer authority must be an object')
    return value


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, timeout=30).stdout


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


def run_isolated(workspace, program, timeout=1200):
    """Execute no candidate code in the credential-bearing host process."""
    from .profile import sandbox_command
    home = workspace / '.scratch' / 'home'
    (home / '.codex').mkdir(parents=True)
    (home / '.codex/config.toml').write_text('')
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(home),
           'TMPDIR': str(workspace / '.scratch'), 'LANG': 'C',
           'PYTHONDONTWRITEBYTECODE': '1', 'NR_HOST_ROOT': str(ROOT)}
    command = sandbox_command(workspace, [str(ROOT / '.runtime/temporal-venv/bin/python'), '-I', '-B',
                                          str(program), str(workspace / 'source')])
    # Extend only the read table for pinned interpreters/CLIs needed by regression
    # tests. Host evidence, keychain, real HOME, App key and Temporal remain denied.
    index = next(i for i, value in enumerate(command) if value.startswith('permissions.nr.filesystem='))
    extra = {str(ROOT / '.runtime/temporal-venv'): 'read',
             str(ROOT / '.runtime/bin/claude-2.1.257'): 'read',
             str(ROOT / '.runtime/bin/codex-0.155.1'): 'read'}
    command[index] = command[index][:-1] + ',' + ','.join(json.dumps(k)+'='+json.dumps(v)
                                                        for k,v in extra.items()) + '}'
    process = subprocess.Popen(command, cwd=workspace, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    timed_out, overflow = False, False
    output = bytearray()
    deadline = time.monotonic() + timeout
    reader = selectors.DefaultSelector()
    reader.register(process.stdout, selectors.EVENT_READ)
    try:
        while reader.get_map():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            for key, _ in reader.select(min(0.2, max(0, deadline-time.monotonic()))):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    reader.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > 8 * 1024 * 1024:
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
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        reader.close()
        process.stdout.close()
    output = bytes(output)
    return {'returncode': process.returncode, 'timed_out': timed_out,
            'output_limit_exceeded': overflow, 'output_sha256': sha(output), 'output': output}


def isolated_suite(repository, candidate, discover):
    """Construction's whole suite uses the same credential-denying boundary."""
    if discover not in ('scripts', 'tools'):
        raise GateClosed('Unknown construction test profile')
    work = ROOT / '.runtime/ap11/issuer-suite-workspaces'
    work.mkdir(mode=0o700, exist_ok=True)
    if any(p.is_symlink() for p in (work, *work.parents)):
        raise GateClosed('Suite workspace must not use symlinks')
    with tempfile.TemporaryDirectory(prefix='suite-', dir=work) as temporary:
        workspace = Path(temporary).resolve()
        (workspace / 'source').mkdir(); (workspace / '.scratch').mkdir()
        frozen_snapshot(repository, candidate, workspace / 'source')
        program = workspace / 'acceptance.py'
        program.write_text('import os,sys,unittest\n'
                           'os.chdir(sys.argv[1]);sys.path.insert(0,sys.argv[1])\n'
                           'suite=unittest.defaultTestLoader.discover(' + repr(discover) + ")\n"
                           'result=unittest.TextTestRunner(verbosity=2).run(suite)\n'
                           'raise SystemExit(not result.wasSuccessful())\n')
        program.chmod(0o400)
        result = run_isolated(workspace, program)
        return subprocess.CompletedProcess(['native-sandbox', 'unittest', discover],
                                           result['returncode'], result['output'])


def sealed_construction_suite(repository, candidate, discover, identifier, expected_count):
    """Consume an actual whole-suite measurement sealed by the existing holder.

Historical host-fixture tests cannot run in the model filesystem profile. They
are measured in a credential-free environment and sealed only after inspection,
never run as candidate code in this credential-bearing process. The issuer's
separate frozen acceptance ALWAYS executes in the native sandbox afterwards.
"""
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier) or discover not in ('scripts', 'tools'):
        raise GateClosed('Invalid sealed-suite task/profile')
    issuer = HostIssuer()
    issuer.authority()
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
            or record.get('command') != expected_command
            or record.get('log_sha256') != sha(log) or record.get('returncode') != 0
            or record.get('test_count') != expected_count
            or record.get('credential_free_execution') is not True):
        raise GateClosed('Sealed suite does not bind an actual credential-free whole-candidate measurement')
    text = log.decode(errors='replace')
    counts = re.findall(r'^Ran (\d+) tests? in ', text, re.M)
    lines = [line for line in text.splitlines() if line.strip()]
    if counts != [str(expected_count)] or not lines or lines[-1] != 'OK':
        raise GateClosed('Sealed suite log does not show every expected test passing without skips')
    return subprocess.CompletedProcess(expected_command, record['returncode'], log)


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
    def __init__(self, host=ROOT):
        self.host = Path(host).resolve()
        self.home = self.host / '.runtime/ap11/check-issuer'

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
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier):
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
                or record.get('acceptance_program_sha256') != sha(private_bytes(directory / 'acceptance.py'))):
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
        if repository != expected.resolve():
            raise GateClosed('Issuer candidate repository is not the fixed host mapping')
        head, base = subject['candidate'], subject['base']
        if git(repository, 'remote', 'get-url', 'origin').decode().strip() != 'https://github.com/' + task['target'] + '.git':
            raise GateClosed('Issuer candidate origin differs')
        if git(repository, 'rev-list', '--parents', '-n', '1', head).decode().split() != [head, base]:
            raise GateClosed('Issuer candidate is not one commit on accepted base')
        changes = set(filter(None, git(repository, 'diff', '--name-only', '--no-renames', '-z', base, head).decode().split('\0')))
        if not changes or not changes.issubset(set(task['allowed_paths'])):
            raise GateClosed('Issuer candidate exceeds accepted paths')
        client = transport or AppTransport(config['app_id'], config['installation_id'], self.home / 'app.pem')
        # Read-only main freshness before expensive work; PAT never issues a status.
        remote = current_main(task['target']) if transport is None else client.api(task['target'], 'commits/main').get('sha')
        if remote != base:
            raise GateClosed('Issuer base is no longer current main')
        work = self.home / 'workspaces'
        work.mkdir(mode=0o700, exist_ok=True)
        if any(p.is_symlink() for p in (work, *work.parents)):
            raise GateClosed('Issuer workspace must not use symlinks')
        with tempfile.TemporaryDirectory(prefix='acceptance-', dir=work) as temporary:
            workspace = Path(temporary).resolve()
            (workspace / 'source').mkdir(); (workspace / '.scratch').mkdir()
            files = frozen_snapshot(repository, head, workspace / 'source')
            program = workspace / 'acceptance.py'
            program.write_bytes(private_bytes(directory / 'acceptance.py')); program.chmod(0o400)
            measured = run_isolated(workspace, program)
            observations = self.home / 'observations'
            observations.mkdir(mode=0o700, exist_ok=True)
            attempt = observations / uuid.uuid4().hex
            attempt.mkdir(mode=0o700)
            (attempt / 'acceptance.log').write_bytes(measured['output'])
            (attempt / 'acceptance.log').chmod(0o600)
            record = {'task_sha256': digest(task), 'candidate': head,
                      'acceptance_program_sha256': request['acceptance_program_sha256'],
                      **{k:v for k,v in measured.items() if k != 'output'}}
            (attempt / 'measurement.json').write_text(json.dumps(record, indent=2)+'\n')
            (attempt / 'measurement.json').chmod(0o600)
            if measured['returncode'] != 0 or measured['timed_out'] or measured.get('output_limit_exceeded'):
                raise GateClosed('Frozen acceptance failed or timed out; no successful check issued')
            if any(sha((workspace / 'source' / p).read_bytes()) != value for p, value in files.items()):
                raise GateClosed('Candidate snapshot changed during acceptance')
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
                   'acceptance_program_sha256': request['acceptance_program_sha256'],
                   'review_sha256': request['review_sha256'], 'measured_output_sha256': measured['output_sha256'],
                   'app_id': config['app_id'], 'checks': {}}
        runs = client.api(task['target'], 'commits/' + head + '/check-runs?filter=latest&per_page=100')
        if (not isinstance(runs, dict) or not isinstance(runs.get('check_runs'), list)
                or type(runs.get('total_count')) is not int or runs['total_count'] != len(runs['check_runs'])
                or not all(isinstance(r, dict) and isinstance(r.get('app'), dict) for r in runs['check_runs'])):
            raise GateClosed('Incomplete prior check readback; no blind reissue')
        for name in NAMES:
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
        (attempt / 'issued.json').write_text(json.dumps(receipt, indent=2)+'\n')
        (attempt / 'issued.json').chmod(0o600)
        return receipt
