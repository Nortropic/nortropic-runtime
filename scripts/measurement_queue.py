"""The queue between sessions and the key-less test user's fixed measurement script (D042).

Sessions cannot run sudo (managed policy), and they need a whole-suite measurement no key can reach. So a session
queues a candidate here. The adopted owner observer invokes the existing fixed
test-account program's prepare/run/stop operations. Only the owner observer
timestamps events and writes primary results, outside every repository. No
provider-owned receipt is accepted as a substitute.

usage (a session, any repository):
    python3 -B scripts/measurement_queue.py begar --repo runtime|kontoret|digitala --git REPO --ref refs/heads/BRANCH [--antal N]
    python3 -B scripts/measurement_queue.py vanta ID [--tid SECONDS] [--till DIRECTORY]
    python3 -B scripts/measurement_queue.py status
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time

try:                                           # the agent imports this from the release (scripts is a package there)
    from scripts import matning_provanvandare as fast
except ImportError:                            # a session runs this file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import matning_provanvandare as fast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.failure_ledger import Ledger, Refused as LedgerRefused, valid_observation
from runtime import measurement_observer as observer

SKRIPT = fast.INSTALLERAD
SUDO = '/usr/bin/sudo'
STATUS_SCHEMA = 'measurement-queue-status/1'
AGENT_BUDGET = 900        # no new measurement starts after this many seconds of a look (one that started runs to its end)
MEASURE_LIMIT = 5400      # one measurement at most: the fixed script's own limits add up to under 4800 s


def refuse(message):
    raise SystemExit('REFUSED: ' + message)


def now():
    return datetime.now(timezone.utc)


def owner_only(path, uid):
    info = os.lstat(str(path))
    return os.path.isdir(str(path)) and not os.path.islink(str(path)) and info.st_uid == uid and not info.st_mode & 0o022


def installed(plats=None, skript=SKRIPT):
    """The owner's one-time installation: the test user, its home, and the fixed script root-owned where the rule names it."""
    plats = plats or fast.Plats()
    try:
        pwd.getpwnam(plats.prov)
        info = os.lstat(str(skript))
    except (KeyError, OSError):
        return False
    return (os.path.isfile(str(skript)) and not os.path.islink(str(skript)) and info.st_uid == 0
            and not info.st_mode & 0o022 and plats.provhem.is_dir()
            and hashlib.sha256(Path(skript).read_bytes()).digest()
                == hashlib.sha256(Path(fast.__file__).read_bytes()).digest())


def pending(plats):
    """Queued ids, oldest first: a request the owner wrote, not yet measured and not yet tried by the agent."""
    uid = os.getuid()
    if not plats.inkorg.is_dir() or not owner_only(plats.inkorg, uid):
        return []
    found = []
    for directory in plats.inkorg.iterdir():
        request = directory / 'begaran.json'
        if (fast.ID.fullmatch(directory.name) and owner_only(directory, uid) and request.is_file()
                and not request.is_symlink() and not (directory / 'agent.json').exists()
                and not (observer.output_directory(plats, directory.name) / 'klar.json').exists()):
            found.append((request.stat().st_mtime, directory.name))
    return [name for _, name in sorted(found)]


def write_json(path, value, mode=0o600):
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')
    temporary.chmod(mode)
    os.replace(str(temporary), str(path))


def durable_exclusion(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        import stat
        info=os.fstat(fd);current=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022
                or (info.st_dev,info.st_ino)!=(current.st_dev,current.st_ino)):
            refuse('private qualification marker identity differs')
        os.fsync(fd)
    finally:os.close(fd)
    # Marker bytes and its name, then the newly created request directory.
    from runtime.failure_ledger import sync_directory
    sync_directory(path.parent);sync_directory(path.parent.parent)


def run_pending(host, plats=None, measure=None, budget=AGENT_BUDGET, skript=SKRIPT, quiet=None):
    """The agent's part: each queued request in turn, through the one sudoers rule. No measurement starts after the look's
    budget, and none starts unless quiet(MEASURE_LIMIT) passes: the AP-10 watch is not running and its next run is at
    least the 20-minute lead plus one whole measurement away, so no measurement can still run when the watch starts."""
    plats = plats or fast.Plats()
    measure = measure or observer.measure
    status_path = Path(host) / '.runtime/ap10/measurement-status.json'
    lock = (Path(host) / '.runtime/ap10/measurement.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    with lock:
        queue = pending(plats)
        if not installed(plats, skript):
            state = {'state': 'not_installed', 'queued': queue,
                     'reason': 'the test user, its home or the root-owned fixed script is missing (the owner installs them once)'}
            write_json(status_path, {'schema': STATUS_SCHEMA, 'checked_at': now().isoformat(), **state})
            return state
        start, done, waited = time.monotonic(), [], None
        for ident in queue:
            if time.monotonic() - start > budget:
                break
            if quiet is not None:
                try:
                    quiet(MEASURE_LIMIT)
                except BaseException as error:
                    waited = str(error)
                    break
            began = now().isoformat()
            # Reserve the attempt before the fixed process can execute. A lost
            # process or an old green retry cannot erase this reservation.
            book = Ledger()
            try:
                request, _ = fast.las_begaran(plats, ident)
                source = hashlib.sha256((plats.inkorg / ident / 'begaran.json').read_bytes()).hexdigest()
                diagnostic = read_diagnostic(plats.inkorg / ident / 'diagnostik.json')
                regression = read_regression(plats.inkorg / ident / 'regression.json')
                if diagnostic is not None and regression is not None:
                    raise LedgerRefused('Regression cannot rename a diagnostic')
                if regression is not None:
                    source = hashlib.sha256((source + json.dumps(regression, sort_keys=True)).encode()).hexdigest()
                if diagnostic is None:
                    book.require_publishable(request['candidate'])
                run_id = book.begin(request['candidate'], 'diagnostic' if diagnostic else 'regression' if regression is not None else 'measurement', source,
                                    diagnostic_of=diagnostic)
            except (LedgerRefused, fast.Vagrar, OSError, ValueError):
                write_json(plats.inkorg / ident / 'agent.json',
                           {'id': ident, 'returncode': None, 'state': 'refused',
                            'reason': 'Invalid request or ledger refused this attempt; no measurement started'}, mode=0o644)
                done.append({'id': ident, 'returncode': None})
                continue
            cases, complete, code, cleanup_verified = [], False, None, False
            measured = {}
            try:
                measured = measure(plats, ident, request, plats.inkorg / ident / 'kandidat.bundle', run_id, skript,
                                   selection=regression)
                code = measured.get('returncode')
                cases = measured.get('cases', [])
                cleanup_verified = measured.get('cleanup_verified') is True
                code_root = Path(__file__).resolve().parents[1]
                expected_code = {p: hashlib.sha256((code_root / p).read_bytes()).hexdigest() for p in
                                 ('scripts/matning_provanvandare.py', 'runtime/measurement_observer.py', 'scripts/measurement_queue.py')}
                complete = (measured.get('candidate') == request['candidate'] and measured.get('tree') == request['tree']
                            and valid_observation(measured, expected_code))
            except observer.ObservationInterrupted as error:
                # The trusted owner observer may have completed real cases
                # before a final file write failed. Keep those observations,
                # but the attempt remains incomplete and stops the queue.
                measured=error.observation
                if (measured.get('candidate')==request['candidate'] and measured.get('tree')==request['tree']
                        and measured.get('ledger_run')==run_id):
                    cases=measured.get('cases',[]);code=measured.get('returncode')
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, fast.Vagrar):
                # Already reserved: loss of the observer/helper is a failed,
                # incomplete attempt. Never run the next candidate blindly.
                pass
            try:
                end = book.finish(run_id, cases, code if type(code) is int else 124, complete=complete,
                                  terminal_successful=measured.get('terminal_successful') if type(measured.get('terminal_successful')) is bool else None)
            except (LedgerRefused, ValueError, TypeError):
                end = book.finish(run_id, [], 1, complete=False)
            record = {'id': ident, 'started_at': began, 'finished_at': now().isoformat(), 'returncode': code,
                      'ledger_run': run_id, 'measurement_passed': end['passed'],
                      # Raw process output stays in the owner's private result.
                      'stderr_tail': 'the measurement exceeded its limit' if code is None else '',
                      'failed_cases': [c['name'] for c in end['cases'] if c['status'] != 'success']}
            write_json(plats.inkorg / ident / 'agent.json', record, mode=0o644)
            done.append({'id': ident, 'returncode': code})
            if not cleanup_verified:
                waited = 'Process cleanup is unverified; no later request started'
                break
        state = {'state': 'measured' if done else ('waiting' if waited else 'idle'), 'measured': done, 'queued': pending(plats)}
        if waited:
            state['reason'] = waited
        write_json(status_path, {'schema': STATUS_SCHEMA, 'checked_at': now().isoformat(), **state})
        return state


# ------------------------------------------------------------------------------------------------ the session's part
def git(repo, *args):
    return subprocess.run(['git', '--no-replace-objects', '-C', str(repo), *args], check=True, capture_output=True, text=True, timeout=600).stdout.strip()


def read_diagnostic(path):
    if not path.exists():
        return None
    info = path.lstat()
    if path.is_symlink() or not path.is_file() or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1024:
        raise LedgerRefused('Invalid diagnostic request')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or set(value) != {'diagnostic_of'} or not re.fullmatch('[0-9a-f]{32}', value['diagnostic_of']):
        raise LedgerRefused('Invalid diagnostic binding')
    return value['diagnostic_of']


def read_regression(path):
    if not path.exists():
        return None
    info = path.lstat()
    if path.is_symlink() or not path.is_file() or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 65536:
        raise LedgerRefused('Invalid regression request')
    value = json.loads(path.read_bytes())
    if (not isinstance(value, dict) or set(value) != {'schema', 'names'}
            or value['schema'] != 'nortropic-planned-regression/1'
            or not isinstance(value['names'], list) or len(value['names']) > 100
            or any(not isinstance(n, str) or not observer.NAME.fullmatch(n) for n in value['names'])
            or len(set(value['names'])) != len(value['names'])):
        raise LedgerRefused('Invalid regression selection')
    return value


def begar(repo_kind, repo, ref, antal=None, plats=None, diagnostic_of=None, regression=False, names=(), qualification_run=None):
    """Queue a candidate: its branch as a bundle and a request of exactly the shape the fixed script accepts."""
    plats = plats or fast.Plats()
    if qualification_run is not None and (not isinstance(qualification_run,str) or not re.fullmatch('[0-9a-f]{32}',qualification_run)):
        refuse('a private qualification names its already reserved ledger run')
    if diagnostic_of is not None and regression or names and not regression:
        refuse('planned regression and explicit diagnostics are separate')
    if any(not isinstance(n, str) or not observer.NAME.fullmatch(n) for n in names) or len(names) > 100 or len(set(names)) != len(names):
        refuse('invalid regression names')
    if repo_kind not in fast.PROFILER:
        refuse('--repo is one of ' + ', '.join(sorted(fast.PROFILER)))
    if not fast.REF.fullmatch(ref) or '..' in ref:
        refuse('--ref must be a full branch name, refs/heads/...')
    candidate = git(repo, 'rev-parse', '--verify', ref + '^{commit}')
    tree = git(repo, 'rev-parse', candidate + '^{tree}')
    stamp = now().strftime('%Y%m%dt%H%M%Sz')
    ident = '%s-%s-%s' % (repo_kind, candidate[:12], stamp)
    uid = os.getuid()
    for directory in (plats.inkorg.parent, plats.inkorg):
        if not directory.exists():
            directory.mkdir(mode=0o755)
        if not owner_only(directory, uid):
            refuse('%s must be a directory only you can write' % directory)
    target = plats.inkorg / ident
    target.mkdir(mode=0o755)
    if qualification_run is not None:
        # Before begaran.json can become visible, permanently exclude this
        # private request from every agent generation. A lost caller must not
        # turn a diagnostic with a private selection into an ordinary job.
        write_json(target/'agent.json',{'id':ident,'ledger_run':qualification_run,
                   'state':'qualification_reserved'},mode=0o644)
        durable_exclusion(target/'agent.json')
    bundle = target / 'kandidat.bundle'
    # Every branch: some suites read historical commits by id that only other branches hold, as in a worktree.
    git(repo, 'bundle', 'create', str(bundle), '--branches')
    bundle.chmod(0o644)
    heads = git(repo, 'bundle', 'list-heads', str(bundle), ref).split()
    if heads[:1] != [candidate]:
        refuse('the bundle does not carry %s at %s' % (ref, candidate))
    if repo_kind == 'digitala':
        runtime_view(plats.runtime, target / 'runtime-vy')
    request = {'schema': fast.BEGARAN, 'id': ident, 'repo': repo_kind, 'candidate': candidate, 'tree': tree, 'ref': ref,
               'expected_test_count': antal, 'requested_at': now().isoformat()}
    if diagnostic_of is not None:
        if not re.fullmatch('[0-9a-f]{32}', diagnostic_of):
            refuse('a diagnostic names the exact failed ledger run')
        write_json(target / 'diagnostik.json', {'diagnostic_of': diagnostic_of}, mode=0o600)
    if regression:
        write_json(target / 'regression.json', {'schema': 'nortropic-planned-regression/1', 'names': list(names)}, mode=0o600)
    write_json(target / 'begaran.json', request, mode=0o644)     # last: the agent takes only a complete request
    return ident


def runtime_view(host, view):
    """The active Runtime release as Digitala's tests read it: its configuration byte for byte and its runtime/ code
    under a pointer into the view (kor_profil.aktiv_release), the same code at the view's root as a checkout would have
    it (test_repo_konsistens), and the host's interpreter linked. Private context and history archives are not copied;
    the configuration only names them."""
    host = Path(host)
    pointer = json.loads((host / '.runtime/ap10/active.json').read_text())
    config = Path(pointer['config']); data = config.read_bytes()
    if hashlib.sha256(data).hexdigest() != pointer['sha256']:
        refuse('the active Runtime configuration is not the one its pointer names')
    release = view / '.runtime/ap10/releases' / config.parent.name
    release.mkdir(parents=True, mode=0o755)
    for name, expected in json.loads(data)['files'].items():
        if not name.startswith('runtime/'):
            continue
        content = (config.parent / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            refuse('the active Runtime release differs from its configuration: ' + name)
        for target in (release / name, view / name[len('runtime/'):]):
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            target.write_bytes(content); target.chmod(0o644)
    (release / 'config.json').write_bytes(data); (release / 'config.json').chmod(0o644)
    (view / '.runtime/temporal-venv').symlink_to(host / '.runtime/temporal-venv')
    write_json(view / '.runtime/ap10/active.json', {'config': str(release / 'config.json'), 'sha256': pointer['sha256']}, mode=0o644)
    for directory in [view, *view.rglob('*')]:
        if directory.is_dir() and not directory.is_symlink():
            directory.chmod(0o755)


def vanta(ident, tid=5400, till=None, plats=None, sov=10):
    """Wait for the fixed script's result; copy what sealing needs into a directory of the session's own."""
    plats = plats or fast.Plats()
    if not fast.ID.fullmatch(ident):
        refuse('not a measurement id')
    output = observer.output_directory(plats, ident)
    klar, agent = output / 'klar.json', plats.inkorg / ident / 'agent.json'
    end = time.monotonic() + tid
    while not klar.is_file():
        if agent.is_file():
            refuse('the agent ran the measurement but it left no result: ' + agent.read_text()[-2000:])
        if time.monotonic() > end:
            refuse('no result for %s after %d s; the agent looks every five minutes when it is installed' % (ident, tid))
        time.sleep(sov)
    value = json.loads(klar.read_text())
    if till:
        destination = Path(till)
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        observer.private_directory(destination)
        for name in ('suite.json', 'suite.log', 'gransprob.json', 'klar.json', 'cases.jsonl'):
            source = output / name
            if source.is_file():
                with observer.private_output(destination / name) as stream:
                    stream.write(source.read_bytes())
    return value


def status(host=None, plats=None):
    plats = plats or fast.Plats()
    value = {'installed': installed(plats), 'queued': pending(plats)}
    if host:
        path = Path(host) / '.runtime/ap10/measurement-status.json'
        value['agent'] = json.loads(path.read_text()) if path.is_file() else None
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='action', required=True)
    one = sub.add_parser('begar')
    one.add_argument('--repo', required=True); one.add_argument('--git', required=True)
    one.add_argument('--ref', required=True); one.add_argument('--antal', type=int)
    one.add_argument('--diagnostik-av', help='explicit diagnostic of an exact failed ledger run; never repair evidence')
    one.add_argument('--regression', action='store_true', help='planned F3 series; refuses any previous failed or unfinished attempt')
    one.add_argument('--provnamn', nargs='+', default=[], help='ordered unittest names in a planned regression; omitted means whole suite')
    two = sub.add_parser('vanta')
    two.add_argument('id'); two.add_argument('--tid', type=int, default=5400); two.add_argument('--till')
    sub.add_parser('status')
    arguments = parser.parse_args(argv)
    os.umask(0o022)
    if arguments.action == 'begar':
        print(begar(arguments.repo, arguments.git, arguments.ref, arguments.antal, diagnostic_of=arguments.diagnostik_av,
                    regression=arguments.regression, names=arguments.provnamn))
    elif arguments.action == 'vanta':
        print(json.dumps(vanta(arguments.id, arguments.tid, arguments.till), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(status(Path(__file__).resolve().parents[1]), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
