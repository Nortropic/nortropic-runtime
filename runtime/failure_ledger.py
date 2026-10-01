"""Private append-only observations; diagnostic reruns never establish a repair.

The ledger is evidence and a refusal rule, never publication authority. No raw
test output, traceback, arbitrary test parameter or exception is stored here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import grp
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import uuid
from .content_guard import PATTERNS, load_policy

PHASES = {'measurement', 'dry-run', 'publication', 'sealed', 'host', 'diagnostic', 'regression'}
CLASSES = {'fixtur', 'ordning', 'produkt', 'infrastruktur', 'okänd'}
STATUSES = {'success', 'failure', 'error', 'timeout', 'skipped', 'unknown'}
HEX = re.compile(r'[0-9a-f]{40}')
SHA = re.compile(r'[0-9a-f]{64}')
RUN = re.compile(r'[0-9a-f]{32}')


class Refused(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def default_directory():
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / 'Library/Application Support/Nortropic/test-ledger'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def safe_name(value, literals=()):
    # Test.id() can contain user data through parameterization. A normal Python
    # dotted identifier is safe to retain; everything else is only a digest.
    raw = str(value).encode()
    unsafe = any(pattern.search(raw) for pattern in PATTERNS.values()) or any(lit in raw for lit in literals)
    if isinstance(value, str) and re.fullmatch(r'masked-[0-9a-f]{64}', value):
        if unsafe:
            raise Refused('A display digest collides with private policy')
        return value
    if not unsafe and isinstance(value, str) and re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}|[a-z][a-z0-9-]{0,59})', value) and len(value) <= 512:
        return value
    return 'masked-' + hashlib.sha256(str(value).encode()).hexdigest()


def acl_entry(line, *, trusted_uids=None, private=False):
    """Read-only ACEs for another resolved OS principal do not empower tests.

    Never grant an exception by account name. Resolve actual test UID/groups;
    unknown principals or rights, matching test access and untrusted writes fail.
    Deny ACEs cannot enlarge access and are never used to cancel an allow here.
    """
    match = re.fullmatch(r'\s*\d+: (user|group):([^ ]+) (?:inherited )?(allow|deny) ([a-z_,]+)', line)
    if not match:
        raise Refused('Unknown ACL representation')
    kind, principal, effect, rights = match.groups()
    if effect == 'deny':
        return
    try:
        test = pwd.getpwnam('_nortropicprov')
        test_groups = set(os.getgrouplist(test.pw_name, test.pw_gid)) | {test.pw_gid}
        trusted = {0, os.getuid()} if trusted_uids is None else set(trusted_uids)
        if kind == 'user':
            uid = pwd.getpwnam(principal).pw_uid
            applies = uid == test.pw_uid
            if uid in trusted and not applies:
                return
        else:
            applies = principal == 'everyone' or grp.getgrnam(principal).gr_gid in test_groups
    except (KeyError, OSError):
        raise Refused('ACL principal or test membership is unknown') from None
    readonly = {'read', 'list', 'search', 'execute', 'readattr', 'readextattr', 'readsecurity',
                'file_inherit', 'directory_inherit', 'only_inherit', 'limit_inherit'}
    if private or applies or not set(rights.split(',')) <= readonly:
        raise Refused('ACL permits test-account access or untrusted modification')


def require_acl(path, *, private=False):
    """Check effective test-account access, including inherited delete_child."""
    result = subprocess.run(['/bin/ls', '-lde', str(path)], capture_output=True,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}, timeout=10)
    if result.returncode:
        raise Refused('Ledger ACL observation unavailable')
    for line in result.stdout.decode('utf-8', 'strict').splitlines()[1:]:
        acl_entry(line,private=private)


def sync_directory(path):
    path=Path(path);before=path.lstat()
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode) or (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino):
            raise Refused('Ledger directory identity changed')
        os.fsync(fd)
        after=path.lstat()
        if (opened.st_dev,opened.st_ino)!=(after.st_dev,after.st_ino):raise Refused('Ledger directory replaced')
    finally:os.close(fd)


HOST_FIELDS = ('candidate', 'module', 'clean_tree', 'source_sha256', 'host_root', 'scope', 'journal_head', 'runner_sha256')


def host_binding(receipt):
    return digest({key: receipt[key] for key in HOST_FIELDS})


def clean_cases(cases, literals=()):
    if not isinstance(cases, list) or len(cases) > 100000:
        raise Refused('Invalid case list')
    result = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or case.get('status') not in STATUSES:
            raise Refused('Invalid test observation')
        seconds = case.get('seconds')
        if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
            raise Refused('Invalid test duration')
        name = safe_name(case.get('name'), literals)
        file = case.get('file')
        if file is not None and (not isinstance(file, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', file)
                                 or file.startswith('/') or '..' in Path(file).parts
                                 or any(lit in file.encode() for lit in literals)
                                 or any(p.search(file.encode()) for p in PATTERNS.values())):
            file = 'masked-' + hashlib.sha256(str(file).encode()).hexdigest()
        result.append({'order': index + 1, 'name': name,
                       'file': file,
                       'seconds': seconds, 'status': case['status'],
                       'classification': 'okänd' if case['status'] != 'success' else None})
    return result


class Ledger:
    def __init__(self, directory=None, policy=None):
        self.policy = load_policy() if policy is None else policy
        self.directory = Path(directory) if directory is not None else default_directory()
        if any(path.is_symlink() or (path / '.git').exists() for path in (self.directory, *self.directory.parents)):
            raise Refused('The ledger must be outside every repository and symlink')
        missing=[p for p in (self.directory,*self.directory.parents) if not p.exists()]
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refused('The ledger must be owner-private')
        self.protected()
        for path in missing:
            sync_directory(path);sync_directory(path.parent)

    def protected(self):
        for path in (self.directory, *self.directory.parents):
            info = path.lstat()
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or info.st_mode & 0o022 and not sticky_root):
                raise Refused('Unsafe ledger ancestor')
            require_acl(path,private=path==self.directory)
        info = self.directory.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refused('The ledger must remain owner-private')

    @contextmanager
    def locked(self):
        self.protected()
        fd = os.open(self.directory / 'lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise Refused('Unsafe ledger lock')
            require_acl(self.directory / 'lock',private=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def read(self, name):
        if not re.fullmatch(r'[0-9a-f]{32}-(?:begin|finish|class-[0-9a-f]{32})\.json', name):
            raise Refused('Invalid ledger record')
        require_acl(self.directory / name,private=True)
        fd = os.open(self.directory / name, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 64 * 1024 * 1024:
                raise Refused('Unsafe ledger record')
            return json.load(stream)

    def write(self, name, value):
        # The final name is the commit point. All fallible content/ACL checks
        # happen before it exists; a post-write ACL failure must not leave an
        # apparently completed green attempt. link is atomic and never replaces
        # an existing record. begin additionally syncs the directory before
        # returning permission to start. Loss of a later finish leaves that
        # durable reservation unfinished, never synthesizes success.
        temporary=self.directory/('.pending-'+uuid.uuid4().hex)
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb') as stream:
                stream.write(encoded(value));stream.flush();os.fsync(stream.fileno())
            require_acl(temporary,private=True)
            os.link(temporary,self.directory/name,follow_symlinks=False)
        finally:
            # This private staging name is not a ledger record. Its cleanup
            # cannot turn an already committed record into an aborted write.
            try:temporary.unlink()
            except OSError:pass

    def require_host(self, commit, receipt):
        self.require_publishable(commit)
        identifier = receipt.get('ledger_run')
        if not isinstance(identifier, str) or not RUN.fullmatch(identifier):
            raise Refused('Host receipt lacks its permanent attempt')
        begin = self.begin_record(identifier + '-begin.json')
        end = self.ending(begin)
        if (begin['commit'] != commit or begin['phase'] != 'host'
                or begin['source_sha256'] != host_binding(receipt)
                or digest(end) != receipt.get('ledger_finish_sha256')
                or not end['passed'] or end['cases'] != receipt.get('cases')
                or type(receipt.get('run')) is not int or receipt['run'] != len(end['cases'])
                or any(c['status'] != 'success' for c in end['cases'])):
            raise Refused('Host receipt differs from its permanent observation')
        return identifier

    def begin_record(self, name):
        value = self.read(name)
        identifier = name.removesuffix('-begin.json')
        if (not isinstance(value, dict) or value.get('schema') != 'nortropic-test-run/1'
            or value.get('id') != identifier or not RUN.fullmatch(identifier)
            or not isinstance(value.get('commit'), str) or not HEX.fullmatch(value['commit'])
            or value.get('phase') not in PHASES
            or not isinstance(value.get('source_sha256'), str) or not SHA.fullmatch(value['source_sha256'])
            or type(value.get('attempt')) is not int or value['attempt'] < 1
            or not isinstance(value.get('started_at'), str)
            or (value['phase'] == 'diagnostic' and not RUN.fullmatch(str(value.get('diagnostic_of', ''))))
            or (value['phase'] != 'diagnostic' and value.get('diagnostic_of') is not None)):
            raise Refused('Invalid beginning binding')
        return value

    def ending(self, begin):
        """Validate stored primary fields again; passed is never trusted alone."""
        end = self.read(begin['id'] + '-finish.json')
        if (not isinstance(end, dict) or end.get('id') != begin['id']
            or end.get('begin_sha256') != digest(begin)
            or type(end.get('returncode')) is not int or type(end.get('complete')) is not bool
            or type(end.get('passed')) is not bool
            or 'terminal_successful' in end and type(end['terminal_successful']) is not bool
            or not isinstance(end.get('finished_at'), str)):
            raise Refused('Invalid terminal binding')
        if 'observation_sha256' in end and (not isinstance(end['observation_sha256'],str)
                or not SHA.fullmatch(end['observation_sha256'])):
            raise Refused('Invalid primary observation binding')
        cases = end.get('cases')
        if not isinstance(cases, list):raise Refused('Invalid terminal cases')
        normalized = clean_cases(cases, self.policy['literals'])
        for original, checked in zip(cases, normalized):
            if (original.get('order') != checked['order'] or type(original.get('order')) is not int
                or any(original.get(k) != checked[k] for k in ('name','file','seconds','status'))):
                raise Refused('Invalid terminal case binding')
        passed = (end['returncode'] == 0 and end['complete'] and end.get('terminal_successful') is not False and bool(cases)
                  and all(c['status'] == 'success' for c in cases))
        if end['passed'] is not passed:
            raise Refused('Terminal success contradicts primary fields')
        return end

    def begins(self, commit):
        rows = [self.begin_record(p.name) for p in sorted(self.directory.glob('*-begin.json'))]
        selected = [r for r in rows if r['commit'] == commit]
        if len({r['attempt'] for r in selected}) != len(selected):raise Refused('Duplicate attempt binding')
        return selected

    def begin(self, commit, phase, source_sha256, diagnostic_of=None):
        if not isinstance(commit, str) or not HEX.fullmatch(commit) or phase not in PHASES or not SHA.fullmatch(source_sha256):
            raise Refused('Invalid run binding')
        with self.locked():
            previous = self.begins(commit)
            if phase == 'measurement' and any(row['phase'] == 'measurement' for row in previous):
                raise Refused('A repeated whole suite must be an explicit diagnostic')
            if phase == 'diagnostic':
                if not isinstance(diagnostic_of, str) or not RUN.fullmatch(diagnostic_of):
                    raise Refused('A diagnostic needs an explicit failed run')
                original = self.begin_record(diagnostic_of + '-begin.json')
                failure = self.ending(original)
                if original['commit'] != commit or failure['passed']:
                    raise Refused('The diagnostic must bind a failed run on this commit')
                if sum(row['phase'] == 'diagnostic' for row in previous) >= 2:
                    raise Refused('Two diagnostic reruns already booked for this commit')
            elif diagnostic_of is not None:
                raise Refused('Only a diagnostic names a prior run')
            identifier = uuid.uuid4().hex
            value = {'schema': 'nortropic-test-run/1', 'id': identifier, 'commit': commit,
                     'attempt': len(previous) + 1, 'phase': phase, 'source_sha256': source_sha256,
                     'diagnostic_of': diagnostic_of, 'started_at': timestamp()}
            self.write(identifier + '-begin.json', value)
            # A failed sync leaves a visible incomplete reservation and refuses
            # transport. No run may start on an unsynced directory entry.
            sync_directory(self.directory)
            return identifier

    def finish(self, identifier, cases, returncode, complete=True, *, observation_sha256=None, terminal_successful=None):
        if (type(returncode) is not int or type(complete) is not bool
                or terminal_successful is not None and type(terminal_successful) is not bool):
            raise Refused('Invalid terminal observation')
        if observation_sha256 is not None and (not isinstance(observation_sha256,str) or not SHA.fullmatch(observation_sha256)):
            raise Refused('Invalid primary observation binding')
        rows = clean_cases(cases, self.policy['literals'])
        with self.locked():
            begin = self.begin_record(identifier + '-begin.json')
            passed = (returncode == 0 and complete is True and terminal_successful is not False
                      and bool(rows) and all(c['status'] == 'success' for c in rows))
            value = {'id': identifier, 'begin_sha256': digest(begin), 'finished_at': timestamp(),
                     'cases': rows, 'returncode': returncode, 'complete': complete is True,
                     'passed': passed, 'repair_proven': False if begin['phase'] == 'diagnostic' else None}
            if terminal_successful is not None:value['terminal_successful']=terminal_successful
            if observation_sha256 is not None:value['observation_sha256']=observation_sha256
            self.write(identifier + '-finish.json', value)
            return value

    def classify(self, identifier, order, category, intermittent=False):
        if category not in CLASSES or type(order) is not int or type(intermittent) is not bool:
            raise Refused('Invalid failure classification')
        with self.locked():
            begin = self.begin_record(identifier + '-begin.json'); end = self.ending(begin)
            if order < 1 or order > len(end['cases']) or end['cases'][order - 1]['status'] == 'success':
                raise Refused('The named failure does not exist')
            if intermittent:
                original=begin;seen=set()
                while original['phase']=='diagnostic':
                    if original['id'] in seen or len(seen)>=2:
                        raise Refused('Invalid diagnostic ancestry')
                    seen.add(original['id'])
                    parent=self.begin_record(original['diagnostic_of']+'-begin.json')
                    if (parent['commit']!=begin['commit'] or parent['attempt']>=original['attempt']
                            or self.ending(parent)['passed']):
                        raise Refused('Invalid diagnostic ancestry')
                    original=parent
                if original['phase'] in ('sealed', 'host', 'measurement', 'dry-run', 'publication'):
                    raise Refused('Sealed suites and host controls cannot be called intermittent')
            value = {'run': identifier, 'attempt': begin['attempt'], 'commit': begin['commit'],
                     'finish_sha256': digest(end), 'case_order': order, 'classification': category,
                     'intermittent': intermittent, 'at': timestamp()}
            self.write(identifier + '-class-' + uuid.uuid4().hex + '.json', value)
            return value

    def publishable(self, commit):
        """A later green attempt does not erase an observed failure or lost run."""
        with self.locked():
            runs = self.begins(commit)
            for run in runs:
                try:
                    end = self.ending(run)
                except (FileNotFoundError, Refused, ValueError, TypeError, KeyError):
                    return False
                if not end['passed']:
                    return False
            return True

    def require_publishable(self, commit):
        if not self.publishable(commit):
            raise Refused('An earlier failed or unfinished run remains on this commit; a green rerun is not a repair')

    def consume(self, commit, phase, source_sha256, record, expected_code):
        """Record consumption of a sealed measurement, never pretend it ran again.

        Its source digest and measured case timings remain distinct from this
        consumption's time. Legacy measurements without timings are incomplete.
        """
        self.require_publishable(commit)
        identifier = self.begin(commit, phase, source_sha256)
        cases = record.get('cases', [])
        complete = valid_observation(record, expected_code)
        result = self.finish(identifier, cases, record.get('returncode', 1), complete=complete,
                             terminal_successful=record.get('terminal_successful') if type(record.get('terminal_successful')) is bool else None)
        if not result['passed']:
            failed = [c['name'] for c in result['cases'] if c['status'] != 'success']
            raise Refused('Sealed measurement failed or lacks case timing: ' + ', '.join(failed[:20]))
        return identifier


def valid_observation(record, expected_code):
    """Validate the adopted producer closure and primary fields, not its green bit.

    The caller must already hold the exact sealed, owner-produced bytes. These
    fields cannot turn an arbitrary candidate-authored document into authority.
    """
    paths = {'script_sha256': 'scripts/matning_provanvandare.py',
             'observer_sha256': 'runtime/measurement_observer.py',
             'queue_sha256': 'scripts/measurement_queue.py'}
    boundary = record.get('credential_boundary')
    cases = record.get('cases')
    if not (isinstance(expected_code, dict) and isinstance(boundary, dict)
            and all(isinstance(expected_code.get(path), str) and SHA.fullmatch(expected_code[path])
                    and boundary.get(field) == expected_code[path] for field, path in paths.items())
            and type(boundary.get('owner_uid')) is int and boundary['owner_uid'] > 0
            and type(boundary.get('test_uid')) is int and boundary['test_uid'] > 0
            and boundary['owner_uid'] != boundary['test_uid']
            and record.get('credential_free_execution') is True
            and type(record.get('case_timing_schema')) is int and record['case_timing_schema'] == 3
            and record.get('observation_kind') == 'owner-received-events/1'
            and record.get('protected_primary_files') is True
            and record.get('shared_interpreter_state') is True
            and record.get('complete') is True and record.get('cleanup_verified') is True
            and record.get('timed_out') is False and record.get('overflow') is False
            and record.get('fixture_errors') == []
            and type(record.get('terminal_successful')) is bool and type(record.get('passed')) is bool
            and type(record.get('returncode')) is int
            and type(record.get('test_count')) is int and record['test_count'] > 0
            and isinstance(cases, list) and len(cases) == record['test_count']
            and all(isinstance(c, dict) and type(c.get('order')) is int and c['order'] == i + 1
                    and type(c.get('seconds')) in (int, float) and math.isfinite(c['seconds']) and c['seconds'] >= 0
                    and isinstance(c.get('name'), str) and isinstance(c.get('file'), str)
                    and not c['file'].startswith('/') and '..' not in Path(c['file']).parts
                    for i, c in enumerate(cases))
            and len({c['name'] for c in cases}) == len(cases)):
        return False
    rows = [{'id': c['order'], 'name': c['name'], 'file': c['file']} for c in cases]
    raw = (json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()
    passed = (record['returncode']==0 and record['terminal_successful'] is True
              and all(c.get('status')=='success' for c in cases))
    return (record.get('manifest_sha256') == hashlib.sha256(raw).hexdigest()
            and record['passed'] is passed)
