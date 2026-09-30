"""The isolated rehearsal before an automatic code transition (D043), the pattern of transitions 17-19 written once.

Before the live service is stopped, both releases run on a private, port- and root-shifted copy:
prepare   a consistent copy of the database (SQLite online backup from a read-only connection); both releases copied
          with the engine's port literals shifted (7339-7341 -> 27339-27341) in their Python code - a literal in any
          other file than Python code and Markdown text refuses - the host root, office root and database re-keyed,
          every changed file re-hashed, and the instruction guards computed by each copy's own code. The live engine,
          schedule, service and files are read, never written.
A         the engine alone through the NEW code's own LocalService: every schedule in the copy is paused, so none fires,
          and the copy's open executions are read. One with a pending activity or workflow task would be handed to the
          copy's worker: the rehearsal then waits (the look comes back) rather than start a worker on it.
B, C      the NEW release's real daemon starts twice, each time confirmed the way the activation's started() confirms
          (a fresh receipt, three live processes, the identity query); every open DevelopmentTask is queried through
          the new worker the first time, so its history replays under the new code; each start ends with SIGTERM.
D         the way back: the OLD release's daemon starts on the same copy after the new one ran, and is confirmed.

Every child - the copies' guard computation, phase A and every daemon - runs under a sandbox profile (profile()) that
allows no network beyond this Mac (no name lookup either), no binding of the live engine's ports, no write anywhere but
this rehearsal's own directory, and no launchctl, sudo or su; its HOME and TMPDIR lie in that directory. So even an
activity the copy's worker ran for real could reach neither a model nor GitHub, nor write into a repository or the live
host. On this Mac's sandbox a rule for one port on this Mac has no effect once a rule names all of them (measured
2026-09-30), so the live engine is kept away by the port shift and measured, not by the profile: at every confirmed start
each TCP connection of the copy's daemon, engine and worker must end at a port one of them listens on (own_connections).
Nothing here calls launchctl. The copy is removed afterwards; the record stays.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import time

PORT = re.compile(r'(?<![0-9A-Za-z])(7339|7340|7341)(?![0-9A-Za-z])')
PORT_BYTES = re.compile(rb'(?<![0-9A-Za-z])(7339|7340|7341)(?![0-9A-Za-z])')
LIVE_PORTS = (7339, 7340, 7341)
ADDRESS = '127.0.0.1:27339'
NAMESPACE = 'nortropic-runtime'
START_SECONDS = 90
QUERY_LIMIT = 20

PHASE_A = r'''
import asyncio, json, os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
from runtime.service import LocalService
async def main():
    base, root = Path(sys.argv[1]), Path(sys.argv[2]); out = {'schedules': {}, 'open': []}
    async with LocalService(root / '.runtime/runtime.sqlite', base / 'phase-a-engine') as client:
        async for listed in await client.list_schedules():
            handle = client.get_schedule_handle(listed.id)
            if not (await handle.describe()).schedule.state.paused:
                await handle.pause(note='rehearsal copy: must never fire')
            out['schedules'][listed.id] = (await handle.describe()).schedule.state.paused
        async for execution in client.list_workflows('ExecutionStatus = "Running"'):
            described = await client.get_workflow_handle(execution.id, run_id=execution.run_id).describe()
            raw = described.raw_description
            out['open'].append({'id': execution.id, 'type': execution.workflow_type, 'history_length': described.history_length,
                                'pending_activities': len(raw.pending_activities),
                                'pending_workflow_task': raw.HasField('pending_workflow_task')})
    print(json.dumps(out))
asyncio.run(main())
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def profile(base):
    """No network beyond this Mac, no binding of the live engine's ports, no write outside base, no launchctl, sudo or su.
    Every rule is a deny with its exception inside its own filter, so no rule's effect rests on the order of rules."""
    writable = '(require-any (subpath %s) (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))' \
        % json.dumps(str(base), ensure_ascii=False)
    lines = ['(version 1)', '(allow default)', '(allow process-exec (literal "/bin/ps") (with no-sandbox))',
             '(deny process-exec (literal "/bin/launchctl") (literal "/usr/bin/sudo") (literal "/usr/bin/su"))',
             '(deny network-outbound (require-not (remote ip "localhost:*")))']
    lines += ['(deny network-bind (local ip "*:%d"))' % port for port in LIVE_PORTS]
    lines += ['(deny file-write* (require-not %s))' % writable]
    return '\n'.join(lines) + '\n'


def lsof(*args):
    """lsof's (pid, name) rows; nothing found is no rows."""
    done = subprocess.run(['/usr/sbin/lsof', '-nP', *args, '-F', 'pn'], capture_output=True, text=True, timeout=30,
                          env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin:/usr/sbin'})
    rows, pid = [], None
    for line in done.stdout.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('n') and pid is not None:
            rows.append((pid, line[1:]))
    return rows


def own_connections(pids):
    """The given processes' TCP connections: how many were seen, and those that neither end at nor were accepted on a
    port one of them listens on - a connection out of the copy, e.g. to the live engine."""
    selected = ('-a', '-p', ','.join(str(p) for p in sorted(pids)), '-iTCP')
    own = {name.rsplit(':', 1)[1] for _, name in lsof(*selected, '-sTCP:LISTEN')}
    port = lambda address: address.rsplit(':', 1)[1]
    connections = [(pid, name) for pid, name in lsof(*selected) if '->' in name]
    return {'seen': len(connections), 'outside': sorted('%s %s' % (pid, name) for pid, name in connections
                                                        if not {port(end) for end in name.split('->')} & own)}


def shift(source, target):
    """A content copy of a release with the port literals in its Python code shifted. Refuses a literal in any other file
    but Markdown text, where no tool reads it as an address."""
    shutil.copytree(source, target, symlinks=True, copy_function=shutil.copyfile)
    changes, remaining = [], []
    for path in sorted(p for p in target.rglob('*') if p.is_file() and not p.is_symlink()):
        if path.suffix == '.py':
            text = path.read_text()
            shifted = PORT.sub(lambda m: '2' + m.group(1), text)
            if shifted != text:
                changes.append(str(path.relative_to(target)))
                path.write_text(shifted)
        elif path.suffix != '.md' and PORT_BYTES.search(path.read_bytes()):
            remaining.append(str(path.relative_to(target)))
    if remaining:
        raise ValueError('a live engine port literal lies outside Python code: %s' % remaining)
    return changes


def rekey(host, root, release, python, env, sandbox):
    """The copy's configuration: roots re-keyed, files re-hashed, guards by the copy's own code; the copy's pointer."""
    config = json.loads((release / 'config.json').read_text())
    config['host_root'] = str(root); config['office_root'] = str(root.parent / 'nortropic-projektkontor')
    config['database'] = str(root / '.runtime/runtime.sqlite')
    config['files'] = {name: sha(release / name) for name in config['files']}
    guards = subprocess.run(wrap([python, '-B', '-c', 'import json; from runtime.release import instruction_guards; '
                                  'print(json.dumps(instruction_guards()))'], sandbox), cwd=str(release / 'runtime'), env=env,
                            capture_output=True, text=True, timeout=120)
    if guards.returncode != 0:
        raise ValueError('the copy could not compute its guards: ' + guards.stderr[-400:])
    config['instruction_guards'] = json.loads(guards.stdout)
    (release / 'config.json').chmod(0o600)
    (release / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    return sha(release / 'config.json')


def point(root, release, digest):
    (root / '.runtime/ap10/active.json').write_text(json.dumps({'config': str(release / 'config.json'), 'sha256': digest}) + '\n')


def environment(root, digest=None):
    """The children's environment: HOME and TMPDIR in the rehearsal's own directory (root's parent), never the owner's."""
    base = Path(root).parent
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': str(base / 'home'), 'TMPDIR': str(base / 'tmp') + '/',
           'NR_HOST_ROOT': str(root), 'PYTHONDONTWRITEBYTECODE': '1', 'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'}
    for key in ('USER', 'LOGNAME'):
        if os.environ.get(key):
            env[key] = os.environ[key]
    if digest:
        env['NR_CONFIG_SHA256'] = digest
    return env


def identity(pid):
    done = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True,
                          timeout=5, env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})
    return done.stdout.strip() if done.returncode == 0 else ''


def alive(receipt):
    return {k: receipt[k]['pid'] for k in ('daemon', 'engine', 'worker')
            if receipt.get(k, {}).get('identity') and identity(receipt[k]['pid']) == receipt[k]['identity']}


def wrap(argv, sandbox):
    return (['/usr/bin/sandbox-exec', '-f', str(sandbox)] + argv) if sandbox else argv


async def start(root, release, digest, python, sandbox, record, label):
    """The real daemon, confirmed like the activation's started(): fresh receipt, three live processes, identity query."""
    from temporalio.client import Client
    entry = record.setdefault(label, {'spawned_at': now()})
    out = (root / '.runtime/ap10/launchd.stdout.log').open('ab'); err = (root / '.runtime/ap10/launchd.stderr.log').open('ab')
    daemon = subprocess.Popen(wrap([python, '-B', '-m', 'runtime.daemon'], sandbox), cwd=str(release / 'runtime'),
                              env=environment(root, digest), stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                              start_new_session=True)
    entry['daemon_pid'] = daemon.pid
    began, deadline = time.monotonic(), time.monotonic() + START_SECONDS
    while True:
        try:
            if daemon.poll() is not None:
                raise RuntimeError('the daemon exited with %s' % daemon.returncode)
            receipt = json.loads((root / '.runtime/ap10/service.json').read_text())
            if receipt['config_sha256'] != digest or len(alive(receipt)) != 3 or receipt['daemon']['pid'] == entry.get('previous_pid'):
                raise ValueError('no fresh live receipt yet')
            client = await asyncio.wait_for(Client.connect(ADDRESS, namespace=NAMESPACE), 3)
            described = await asyncio.wait_for(client.get_workflow_handle(receipt['identity_workflow']).query('describe'), 5)
            if described != receipt['native_identity']:
                raise ValueError('native identity differs')
            entry['confirmed_after_seconds'] = round(time.monotonic() - began, 2)
            return daemon, client, receipt
        except Exception as error:
            if daemon.poll() is not None or time.monotonic() > deadline:
                entry['start_failed'] = repr(error)[:400]
                entry['stderr_tail'] = (root / '.runtime/ap10/launchd.stderr.log').read_text(errors='replace')[-2000:]
                return daemon, None, None
            await asyncio.sleep(.5)


async def stop(daemon, receipt, record, label):
    entry = record[label]; began = time.monotonic()
    if daemon.poll() is None:
        daemon.send_signal(signal.SIGTERM)
    try:
        daemon.wait(timeout=90)
    except subprocess.TimeoutExpired:
        entry['stop_problem'] = 'the daemon still lives 90 s after SIGTERM'
        os.killpg(daemon.pid, signal.SIGKILL); daemon.wait()
    end = time.monotonic() + 30
    while receipt and alive(receipt) and time.monotonic() < end:
        await asyncio.sleep(.5)
    entry['stopped_after_seconds'] = round(time.monotonic() - began, 2)
    entry['left_after_stop'] = alive(receipt) if receipt else {}
    return not entry.get('stop_problem') and not entry['left_after_stop']


async def replay(client, open_executions, record, label):
    """Each open DevelopmentTask queried through the new worker: its history replays under the new code."""
    found = {}
    for row in [r for r in open_executions if r['type'] == 'DevelopmentTask'][:QUERY_LIMIT]:
        try:
            state = await asyncio.wait_for(client.get_workflow_handle(row['id']).query('state'), 60)
            found[row['id']] = {'phase': state.get('phase') if isinstance(state, dict) else None}
        except Exception as error:
            found[row['id']] = {'QUERY_FAILED': repr(error)[:300]}
    record[label]['development_queries'] = found
    return not any('QUERY_FAILED' in v for v in found.values())


def copy_busy(open_executions):
    """Open executions in the copy that a worker would be handed work for: a pending activity or workflow task."""
    return [row['id'] for row in open_executions if row.get('pending_activities') or row.get('pending_workflow_task')]


async def phases(host, base, root, old_release, new_release, old_digest, new_digest, python, sandbox, record):
    engine = subprocess.run(wrap([python, '-B', '-c', PHASE_A, str(base), str(root)], sandbox), cwd=str(new_release / 'runtime'),
                            env=environment(root, new_digest), capture_output=True, text=True, timeout=300)
    if engine.returncode != 0:
        return 'phase A: the engine alone did not start or pause the copy: ' + engine.stderr[-500:]
    record['phase_a'] = json.loads(engine.stdout)
    if not all(record['phase_a']['schedules'].values()):
        return 'phase A: a schedule in the copy is not paused'
    busy = copy_busy(record['phase_a']['open'])
    if busy:
        record['waiting'] = True
        return ('work is in progress in the engine copy (%s): a worker would run it, so the rehearsal waits'
                % ', '.join(busy))
    previous = None
    for label, release, digest in (('new_first', new_release, new_digest), ('new_second', new_release, new_digest),
                                   ('old_after_new', old_release, old_digest)):
        point(root, release, digest)
        record[label] = {'spawned_at': now(), 'previous_pid': previous}
        daemon, client, receipt = await start(root, release, digest, python, sandbox, record, label)
        if client is None:
            await stop(daemon, None, record, label)
            return '%s: the daemon was not confirmed running (%s)' % (label, record[label].get('start_failed'))
        previous = receipt['daemon']['pid']
        replayed = await replay(client, record['phase_a']['open'], record, label) if label == 'new_first' else True
        connections = record[label]['connections'] = own_connections(alive(receipt).values())
        stopped = await stop(daemon, receipt, record, label)
        if connections['outside']:
            return '%s: the copy connected to a port outside itself: %s' % (label, connections['outside'])
        if not connections['seen']:                     # the worker holds the engine's; none seen is an unread list
            record['waiting'] = True
            return '%s: the copy\'s connections could not be read, so the rehearsal waits' % label
        if not replayed:
            return '%s: an open development task did not replay under the new code' % label
        if not stopped:
            return '%s: the daemon did not stop cleanly' % label
    return None


def end_everything(root):
    """Whatever the copy's last receipt names and still lives - daemon, engine, worker - is ended; the live host's are
    never named there (the receipt lies in the copy)."""
    ended = {}
    try:
        receipt = json.loads((root / '.runtime/ap10/service.json').read_text())
    except (OSError, ValueError):
        return ended
    for name, pid in alive(receipt).items():
        try:
            os.kill(pid, signal.SIGKILL); ended[name] = pid
        except OSError:
            pass
    return ended


def rehearse(host, old_release, new_release, base, sandbox=True):
    """Rehearse the transition old -> new on a private copy; return {'passed': bool, 'reason': ..., 'waiting': bool, ...}.
    waiting: the copy held work in progress, so no worker was started; nothing is decided about the release."""
    host, old_release, new_release, base = Path(host), Path(old_release), Path(new_release), Path(base)
    base.mkdir(mode=0o700)
    base = base.resolve()
    root = base / 'root'
    record = {'started_at': now(), 'old_release': str(old_release), 'new_release': str(new_release)}
    python = str(host / '.runtime/temporal-venv/bin/python')
    policy = None
    try:
        for directory in ('.runtime/ap10/releases', '.runtime/ap10/service-launches', '.runtime/ap11'):
            (root / directory).mkdir(parents=True, mode=0o700, exist_ok=True)
        for directory in ('home', 'tmp'):
            (base / directory).mkdir(mode=0o700)
        if sandbox:
            policy = base / 'rehearsal.sb'
            policy.write_text(profile(base))
        for name in ('bin', 'web-tools', 'temporal-venv'):
            if (host / '.runtime' / name).exists():
                (root / '.runtime' / name).symlink_to(host / '.runtime' / name)
        if (host / '.runtime/ap11/application').is_dir():
            shutil.copytree(host / '.runtime/ap11/application', root / '.runtime/ap11/application', symlinks=True)
        with sqlite3.connect('file:' + str(host / '.runtime/runtime.sqlite') + '?mode=ro', uri=True, timeout=10) as source, \
                sqlite3.connect(root / '.runtime/runtime.sqlite') as target:
            source.backup(target)
        with sqlite3.connect('file:' + str(root / '.runtime/runtime.sqlite') + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('the database copy failed its integrity check')
        digests, copies = {}, {}
        for label, source in (('old', old_release), ('new', new_release)):
            copy = root / '.runtime/ap10/releases' / source.name
            record['port_shift_' + label] = shift(source, copy)
            digests[label] = rekey(host, root, copy, python, environment(root), policy)
            copies[label] = copy
        record['copy_digests'] = digests
        reason = asyncio.run(phases(host, base, root, copies['old'], copies['new'], digests['old'], digests['new'],
                                    python, policy, record))
    except Exception as error:
        reason = 'the rehearsal could not be prepared or run: %r' % (error,)
    finally:
        leftover = end_everything(root)
        if leftover:
            record['ended_leftovers'] = leftover
    record.update(passed=reason is None, reason=reason, waiting=record.get('waiting') is True, ended_at=now())
    (base / 'rehearsal-record.json').write_text(json.dumps(record, indent=2, default=str) + '\n')
    for directory in (root, base / 'home', base / 'tmp'):
        shutil.rmtree(directory, ignore_errors=True)
    return record
