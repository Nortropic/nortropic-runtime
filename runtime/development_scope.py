"""AP11 host-side launch reservations, not a workflow or scheduler.

Temporal owns execution state. This append-only journal closes the gap between
a durable workflow decision and an external model process launch. Reservations
are spent before launch and never refunded on redelivery or task renaming.
Candidates cannot access this directory; callers pin the contract digest.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .snapshot import read_regular


class ScopeClosed(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', value):
        raise ScopeClosed('Invalid scoped identity')
    return value


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ScopeClosed('Duplicate journal key')
            result[key] = value
        return result
    def invalid(_):
        raise ScopeClosed('Non-finite journal value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def validate_contract(value):
    required = {'schema', 'id', 'target', 'authority_sha256', 'acceptance_sha256',
                'runtime_revision', 'office_revision', 'work', 'model_calls',
                'implementation_attempts'}
    if not isinstance(value, dict) or set(value) != required:
        raise ScopeClosed('Exact frozen contract required')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ScopeClosed('Unsupported contract')
    if value['id'] != 'office-ap11' or value['target'] != 'Nortropic/nortropic-projektkontor':
        raise ScopeClosed('Only the accepted AP11 Office application is supported')
    for key, length in [('authority_sha256', 64), ('acceptance_sha256', 64),
                        ('runtime_revision', 40), ('office_revision', 40)]:
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{%d}' % length, value[key]):
            raise ScopeClosed('Unbound accepted input')
    if (type(value['model_calls']) is not int or value['model_calls'] != 48 or
            type(value['implementation_attempts']) is not int or value['implementation_attempts'] != 6):
        raise ScopeClosed('The accepted resource ceilings cannot be changed')
    work = value['work']
    if not isinstance(work, dict) or len(work) != 2:
        raise ScopeClosed('Exactly two accepted logical deliverables required')
    seen = set()
    for key, paths in work.items():
        identifier(key)
        if key == 'goal' or not isinstance(paths, list) or not paths:
            raise ScopeClosed('Explicit logical work paths required')
        for path in paths:
            if (not isinstance(path, str) or not re.fullmatch(r'tools/[A-Za-z0-9_./-]+', path)
                    or any(p in ('', '.', '..') for p in path.split('/'))
                    or path.casefold() in seen
                    or path.casefold() in ('tools/kontor.py', 'tools/assignment_preparation.py')):
                raise ScopeClosed('Unsafe or overlapping logical work path')
            seen.add(path.casefold())
    return value


def initialize(directory, contract):
    """Explicit host action; refuses an existing journal, including spent ones."""
    validate_contract(contract)
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ScopeClosed('Unsafe scope directory')
    directory.mkdir(mode=0o700, exist_ok=False)
    for name, content in [('contract.json', json.dumps(contract).encode()),
                          ('journal.jsonl', b''), ('lock', b''),
                          ('head.json', json.dumps({'sequence': 0, 'sha256': digest(contract)}).encode())]:
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    sync_directory(directory)
    sync_directory(directory.parent)
    return digest(contract)


class Scope:
    def __init__(self, directory, contract_digest):
        self.directory = Path(directory).absolute()
        self.expected = contract_digest

    @contextmanager
    def locked(self):
        if any(p.is_symlink() for p in (self.directory, *self.directory.parents)):
            raise ScopeClosed('Unsafe scope path')
        fd = os.open(self.directory / 'lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ScopeClosed('Unsafe scope lock')
            fcntl.flock(fd, fcntl.LOCK_EX)
            contract = validate_contract(decode(read_regular(self.directory, 'contract.json')))
            if digest(contract) != self.expected:
                raise ScopeClosed('Accepted contract changed')
            raw = read_regular(self.directory, 'journal.jsonl')
            if len(raw) > 1024 * 1024 or (raw and not raw.endswith(b'\n')):
                raise ScopeClosed('Incomplete or oversized journal; preserve and diagnose')
            records, previous = [], self.expected
            for line in raw.splitlines():
                row = decode(line)
                if (not isinstance(row, dict) or set(row) != {'sequence', 'previous', 'event', 'sha256'}
                        or type(row['sequence']) is not int or row['sequence'] != len(records) + 1
                        or row['previous'] != previous
                        or row['sha256'] != digest({k: row[k] for k in ('sequence', 'previous', 'event')})):
                    raise ScopeClosed('Broken reservation history')
                previous = row['sha256']
                records.append(row)
            head = decode(read_regular(self.directory, 'head.json'))
            if head != {'sequence': len(records), 'sha256': previous}:
                raise ScopeClosed('Journal/head mismatch; no rollback or automatic repair')
            yield contract, records
        finally:
            os.close(fd)

    def append(self, records, event):
        row = {'sequence': len(records) + 1,
               'previous': records[-1]['sha256'] if records else self.expected,
               'event': event}
        row['sha256'] = digest(row)
        # Advance the separate witness BEFORE the append. A crash in between
        # leaves an unavailable scope, never a refunded reservation or control.
        # Restoring an entire host snapshot remains an explicit native-history
        # reconciliation operation; this is not protection against a hostile host.
        pending = self.directory / 'head-next.json'
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'sequence': row['sequence'], 'sha256': row['sha256']}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, self.directory / 'head.json')
        sync_directory(self.directory)
        fd = os.open(self.directory / 'journal.jsonl', os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(fd, 'ab') as stream:
            stream.write((json.dumps(row, sort_keys=True) + '\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
        records.append(row)
        return row

    @staticmethod
    def state(contract, records):
        result = {'control': 'active', 'calls': [], 'launches': [], 'started': [], 'tasks': {},
                  'implementations': {key: 0 for key in contract['work']}, 'integrated': {}}
        for row in records:
            e = row['event']
            if e['kind'] == 'control':
                result['control'] = e['value']
            elif e['kind'] == 'task':
                result['tasks'][e['task']] = e
            elif e['kind'] == 'call':
                result['calls'].append(e)
                if e['role'] == 'implementation':
                    result['implementations'][e['work']] += 1
            elif e['kind'] == 'started':
                result['started'].append(e['nonce'])
            elif e['kind'] == 'launch':
                result['launches'].append(e['nonce'])
            elif e['kind'] == 'integrated':
                result['integrated'][e['work']] = e
            else:
                raise ScopeClosed('Unknown journal event')
        return result

    def inspect(self):
        with self.locked() as (contract, records):
            return self.state(contract, records)

    def control(self, value, reason):
        if value not in ('active', 'paused', 'stopped', 'revoked', 'quota', 'exhausted') or not isinstance(reason, str) or not reason.strip():
            raise ScopeClosed('Explicit scoped control and reason required')
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            if state['control'] in ('stopped', 'revoked', 'exhausted'):
                raise ScopeClosed('Terminal gate cannot be reopened')
            self.append(records, {'kind': 'control', 'value': value, 'reason': reason})

    def bind_task(self, work, task, task_digest, paths, review_digest):
        identifier(task)
        if any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in (task_digest, review_digest)):
            raise ScopeClosed('Frozen task and separate review must be bound')
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            if (state['control'] != 'active' or work not in contract['work']
                    or paths != contract['work'][work] or task in state['tasks']
                    or work in state['integrated']):
                raise ScopeClosed('New task is outside remaining accepted work')
            self.append(records, {'kind': 'task', 'work': work, 'task': task,
                                  'task_sha256': task_digest, 'review_sha256': review_digest})

    def reserve(self, work, role, nonce, task=None, task_digest=None):
        identifier(nonce)
        roles = ('driver', 'preparation-review', 'implementation', 'review', 'diagnosis', 'final-review')
        if role not in roles:
            raise ScopeClosed('Unqualified model role')
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            if work not in contract['work'] and work != 'goal':
                raise ScopeClosed('Unknown logical work cannot reset resources')
            if any(e['nonce'] == nonce for e in state['calls']):
                raise ScopeClosed('Launch reservation already spent; no redelivery')
            # Pause lets an already started child finish its review, but no new implementation.
            if state['control'] != 'active' and not (state['control'] == 'paused' and role == 'review'):
                raise ScopeClosed('New model work is paused or stopped')
            if role in ('implementation', 'review'):
                bound = state['tasks'].get(task)
                if not bound or bound['work'] != work or bound['task_sha256'] != task_digest or work in state['integrated']:
                    raise ScopeClosed('Model call is not bound to remaining accepted task')
                if role == 'review' and not any(e['task'] == task and e['role'] == 'implementation'
                                               and e['nonce'] in state['started'] for e in state['calls']):
                    raise ScopeClosed('No started child implementation to review')
            exhausted = len(state['calls']) >= contract['model_calls']
            if role == 'implementation':
                exhausted = exhausted or state['implementations'][work] >= contract['implementation_attempts']
            if exhausted:
                self.append(records, {'kind': 'control', 'value': 'exhausted', 'reason': 'Accepted launch ceiling reached'})
                raise ScopeClosed('Accepted resource ceiling reached')
            return self.append(records, {'kind': 'call', 'work': work, 'role': role,
                                         'nonce': nonce, 'task': task})['sha256']

    def launch(self, nonce, launcher):
        """Recheck controls and call the trusted host Popen under the same lock.

        A reservation alone never allows a later start. Stop either precedes
        this transaction (no launch) or follows a recorded active process and
        must cancel it. The callback is host code, never model-generated code.
        Failure spends the reservation without fabricating a successful start.
        """
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            call = next((e for e in state['calls'] if e['nonce'] == nonce), None)
            if not call or nonce in state['launches']:
                raise ScopeClosed('Start needs a unique consumed reservation')
            if state['control'] != 'active' and not (state['control'] == 'paused' and call['role'] == 'review'):
                raise ScopeClosed('Reserved start is now paused or stopped')
            if call['work'] in state['integrated']:
                raise ScopeClosed('Reserved work has already been integrated')
            self.append(records, {'kind': 'launch', 'nonce': nonce})
            process = launcher()
            self.append(records, {'kind': 'started', 'nonce': nonce})
            return process

    def permit_publication(self, work, task, task_digest):
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            bound = state['tasks'].get(task)
            if (state['control'] not in ('active', 'paused') or not bound or
                    bound['work'] != work or bound['task_sha256'] != task_digest or work in state['integrated']):
                raise ScopeClosed('Publication not permitted for this accepted work')

    def record_integration(self, work, task, task_digest, receipt):
        """Host records actual remote receipt even if stop raced with its response."""
        with self.locked() as (contract, records):
            state = self.state(contract, records)
            bound = state['tasks'].get(task)
            if (not bound or bound['work'] != work or bound['task_sha256'] != task_digest
                    or not isinstance(receipt, dict) or not receipt):
                raise ScopeClosed('Unbound integration receipt')
            if work in state['integrated']:
                if state['integrated'][work]['receipt'] == receipt:
                    return
                raise ScopeClosed('Conflicting integration; preserve and reconcile')
            self.append(records, {'kind': 'integrated', 'work': work, 'task': task, 'receipt': receipt})
