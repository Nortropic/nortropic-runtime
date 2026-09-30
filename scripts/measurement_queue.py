"""The queue between sessions and the key-less test user's fixed measurement script (D042).

Sessions cannot run sudo (managed policy), and they need a whole-suite measurement no key can reach. So a session
queues a candidate here, and the owner's agent (scripts/model_choice.py auto, which runs as the owner outside that
policy) runs the ONE sudoers rule for it: `sudo -n -u _nortropicprov /usr/local/libexec/nortropic/matning mat ID`.
Nothing else is run as anyone else; the fixed script judges the request again and writes its result in the test
user's home, where sessions read it.

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
            and not info.st_mode & 0o022 and plats.provhem.is_dir())


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
                and not (plats.ut / directory.name / 'klar.json').exists()):
            found.append((request.stat().st_mtime, directory.name))
    return [name for _, name in sorted(found)]


def write_json(path, value, mode=0o600):
    temporary = Path(str(path) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')
    temporary.chmod(mode)
    os.replace(str(temporary), str(path))


def run_pending(host, plats=None, runner=subprocess.run, budget=AGENT_BUDGET, skript=SKRIPT, quiet=None):
    """The agent's part: each queued request in turn, through the one sudoers rule. No measurement starts after the look's
    budget, and none starts unless quiet(MEASURE_LIMIT) passes: the AP-10 watch is not running and its next run is at
    least the 20-minute lead plus one whole measurement away, so no measurement can still run when the watch starts."""
    plats = plats or fast.Plats()
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
            try:
                result = runner([SUDO, '-n', '-u', plats.prov, str(skript), 'mat', ident], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=MEASURE_LIMIT, cwd='/')
                code, out, err = result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                code, out, err = None, '', 'the measurement exceeded %d s' % MEASURE_LIMIT
            except OSError as error:
                code, out, err = None, '', 'the measurement could not be run or ended: %r' % (error,)
            record = {'id': ident, 'started_at': began, 'finished_at': now().isoformat(), 'returncode': code,
                      'stdout_tail': (out or '')[-4000:], 'stderr_tail': (err or '')[-2000:]}
            write_json(plats.inkorg / ident / 'agent.json', record, mode=0o644)
            done.append({'id': ident, 'returncode': code})
        state = {'state': 'measured' if done else ('waiting' if waited else 'idle'), 'measured': done, 'queued': pending(plats)}
        if waited:
            state['reason'] = waited
        write_json(status_path, {'schema': STATUS_SCHEMA, 'checked_at': now().isoformat(), **state})
        return state


# ------------------------------------------------------------------------------------------------ the session's part
def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True, timeout=600).stdout.strip()


def begar(repo_kind, repo, ref, antal=None, plats=None):
    """Queue a candidate: its branch as a bundle and a request of exactly the shape the fixed script accepts."""
    plats = plats or fast.Plats()
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
    klar, agent = plats.ut / ident / 'klar.json', plats.inkorg / ident / 'agent.json'
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
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('suite.json', 'suite.log', 'gransprob.json', 'klar.json'):
            source = plats.ut / ident / name
            if source.is_file():
                with (destination / name).open('xb') as stream:
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
    two = sub.add_parser('vanta')
    two.add_argument('id'); two.add_argument('--tid', type=int, default=5400); two.add_argument('--till')
    sub.add_parser('status')
    arguments = parser.parse_args(argv)
    os.umask(0o022)
    if arguments.action == 'begar':
        print(begar(arguments.repo, arguments.git, arguments.ref, arguments.antal))
    elif arguments.action == 'vanta':
        print(json.dumps(vanta(arguments.id, arguments.tid, arguments.till), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(status(Path(__file__).resolve().parents[1]), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
