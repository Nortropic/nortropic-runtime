"""Change the release's model choice through one reviewed, reusable controlled transition (D029).

usage, as the owner of the Runtime directory, with the active release's own copy of this file:
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py show
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py stage [--claude MODEL] [--codex MODEL]
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py check | activate | forward | rebind
`show` and `stage` print the exact paths; docs/runbook.md has the whole sequence.

D022 made the model an explicit part of the frozen release configuration, changed only through a controlled release
transition, and every change so far needed its own derived transition script and its own review. This is that
transition written once, with the model as its parameter and `development.models` as the ONLY thing it can change.

stage     copies the ACTIVE release byte for byte into a new release directory and writes its configuration with only
          `development.models` replaced. The release's own code judges the choice, so a selection that release could
          not run is refused here. Nothing is stopped or selected.
check     every precondition of activate against the live engine and service; nothing is changed.
activate  (the owner) backs up the database, stops the service, selects the staged release, starts and confirms it,
          rebinds ONLY the config hash of the AP-10 schedule, and reads everything back. If the new release does not
          start, the previous one is restored and restarted; activate refuses to begin without that way back.
forward   continues an activation whose stop completed; rebind completes only the AP-10 schedule binding.

Why it runs from the active release: every module it uses, and this file itself, are then bytes that release's
configuration binds (installed() verifies them), and the staged copy carries the same tool. A copy of this file in a
checkout would judge a choice by code the release does not run.

The activation sequence is the one the reviewed AP-11 transitions used (executor-transition-13), without their AP-11
checks: it starts no model, sends no signal to any run, and changes no ceiling, role, executor, revision, scope or AP-10
setting. Running workflows are allowed only when idle (no pending activity or workflow task); idle development tasks are
listed, because a choice binds at activation and a resumed task would run the new model.
"""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

CODE_ROOT = Path(__file__).resolve().parents[1]
WATCH = 'office-python-temporal'
LEAD_SECONDS = 1200                 # the next AP-10 run must be at least this far away, as for every earlier transition
ENGINE = ('127.0.0.1:7339', 'nortropic-runtime')
TOOL = 'runtime/scripts/model_choice.py'


def refuse(message):
    raise SystemExit('REFUSED: ' + message)


def say(text):
    print('\n>>> ' + text, flush=True)


def host_root(code_root=CODE_ROOT):
    """The host a release belongs to: <host>/.runtime/ap10/releases/<release>/runtime."""
    parents = Path(code_root).parent.parents
    if (len(parents) < 4 or parents[0].name != 'releases' or parents[1].name != 'ap10' or parents[2].name != '.runtime'
            or Path(code_root).name != 'runtime'):
        refuse('run the active release own copy of this tool: <host>/.runtime/ap10/releases/<release>/runtime/scripts/model_choice.py')
    return parents[3]


if __name__ == '__main__':
    # Before anything imports runtime.release, whose ROOT is fixed at import time. Process identities are compared in the
    # C locale the service records them in, whatever the owner's terminal uses. No bytecode may appear inside a release
    # directory, whose file map binds exactly what is there.
    sys.dont_write_bytecode = True
    if sys.flags.optimize:
        raise SystemExit('REFUSED: optimized interpreter mode is not accepted')
    os.environ['NR_HOST_ROOT'] = str(host_root())
    os.environ.pop('NR_CONFIG_SHA256', None)
    os.environ['LC_ALL'] = 'C'
    sys.path.insert(0, str(CODE_ROOT))

from runtime import daemon, model_question, release                           # noqa: E402
from runtime.development_model import executors, models                      # noqa: E402
from runtime.private_stage import check_private_processes                    # noqa: E402
from runtime.run import check_unfinished_writers                             # noqa: E402
from runtime.shared import process_identity                                  # noqa: E402
from scripts.install_ap10 import LABEL, plist, select                        # noqa: E402


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, default=str); stream.write('\n')


def replace(path, content):
    temporary = Path(str(path) + '.transition-tmp'); temporary.write_bytes(content); temporary.chmod(0o600)
    os.replace(temporary, path)


def read_json(path, what):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        refuse(what + ' is missing or unreadable: ' + str(path))


def paths(host):
    home = Path(host) / '.runtime/ap10'
    return {'active': home / 'active.json', 'releases': home / 'releases', 'transitions': home / 'model-transitions',
            'service': home / 'service.json', 'database': Path(host) / '.runtime/runtime.sqlite',
            'plist': Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')}


def active_release(host):
    """The active selection through installed()'s own checks, and the exact bytes of its configuration."""
    try:
        value = release.installed()
    except (OSError, ValueError, KeyError) as error:
        refuse('the active release does not pass its own integrity checks: %s' % error)
    if value is None:
        refuse('no active release is selected')
    directory = Path(value['directory'])
    if directory.parent != paths(host)['releases']:
        refuse('the active release is not one of this host releases')
    raw = (directory / 'config.json').read_bytes()
    if sha_bytes(raw) != value['config_sha256']:
        refuse('the active configuration changed while it was read')
    return value, raw


def require_active_copy(host, code_root=CODE_ROOT):
    """Every action runs as the copy inside the release the active pointer names, never another release's copy."""
    pointer = read_json(paths(host)['active'], 'active selection')
    directory = Path(pointer.get('config', '')).parent
    if Path(code_root) != directory / 'runtime':
        refuse('this is not the active release own copy of the tool; run ' + str(directory / TOOL))
    return directory


def only_models_differ(old, new):
    """The one invariant of this transition: the configurations are equal once development.models is set aside."""
    a, b = copy.deepcopy(old), copy.deepcopy(new)
    for value in (a, b):
        if not isinstance(value.get('development'), dict):
            refuse('a configuration without a development selection has no model choice to change')
        value['development'].pop('models', None)
    if a != b:
        refuse('the staged configuration differs from the active one beyond development.models')


def verify_files(directory, files, what):
    for name, expected in files.items():
        path = Path(directory) / name
        if path.is_symlink() or not path.is_file() or sha_bytes(path.read_bytes()) != expected:
            refuse(what + name)


def copy_release(source, target, files):
    """Every bound file, byte for byte and with its mode, checked against the configuration on both sides."""
    for name, expected in sorted(files.items()):
        origin, copied = Path(source) / name, Path(target) / name
        if origin.is_symlink() or not origin.is_file():
            refuse('bound file is not a regular file in the active release: ' + name)
        data = origin.read_bytes()
        if sha_bytes(data) != expected:
            refuse('bound file differs in the active release: ' + name)
        copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with copied.open('xb') as stream:
            stream.write(data)
        copied.chmod(origin.stat().st_mode & 0o777)
    verify_files(target, files, 'the copy differs: ')
    present = {p.relative_to(target).as_posix() for p in Path(target).rglob('*') if not p.is_dir()}
    if present != set(files):
        refuse('the copy holds other files than the configuration binds')


def questions(config):
    """The newest model-choice questions (D030), each marked by whether the model it is about is still the one chosen."""
    running = models(config)
    return [{**q, 'still_selected': q.get('model') is not None and running.get(q.get('executor')) == q.get('model')}
            for q in model_question.recent()]


def show(host):
    old, raw = active_release(host); config = json.loads(raw)
    development = config.get('development') or {}
    print(json.dumps({'active_config_sha256': old['config_sha256'], 'release': old['directory'],
                      'selection': development.get('models'), 'models_run': models(config),
                      'executors': executors(config), 'tool': str(Path(old['directory']) / TOOL),
                      'questions': questions(config)}, indent=2, ensure_ascii=False))


def stage(host, requested, code_root=CODE_ROOT, now=None):
    old, raw = active_release(host); directory = Path(old['directory'])
    if Path(code_root) != directory / 'runtime':
        refuse('this is not the active release own copy of the tool; run ' + str(directory / TOOL))
    config = json.loads(raw)
    if config['files'].get(TOOL) != sha_bytes((Path(code_root) / 'scripts/model_choice.py').read_bytes()):
        refuse('the active release does not bind these tool bytes')
    development = config.get('development')
    if not isinstance(development, dict):
        refuse('the active release has no development selection to change')
    requested = {executor: name for executor, name in requested.items() if name is not None}
    if not requested:
        refuse('name at least one model: --claude MODEL and/or --codex MODEL')
    previous = development.get('models')
    selection = {**(previous or {}), **requested}
    if selection == previous:
        refuse('the selection is already %s; nothing to change' % json.dumps(previous))
    new = copy.deepcopy(config); new['development']['models'] = selection
    try:
        before, after = models(config), models(new)          # the release's own rule, applied by the release's own code
        roles = executors(new)
    except ValueError as error:
        refuse('this release refuses the selection: %s' % error)
    only_models_differ(config, new)
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')
    target = paths(host)['releases'] / ('%s-%s-models-%s' % (config['runtime_revision'], config['office_revision'], stamp))
    record_directory = paths(host)['transitions'] / stamp
    for existing in (target, record_directory):             # both names free before either is made: never overwritten
        if existing.exists() or existing.is_symlink():
            refuse('%s exists already; it is never overwritten' % existing)
    record_directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.mkdir(mode=0o700); record_directory.mkdir(mode=0o700)
    copy_release(directory, target, config['files'])
    path = target / 'config.json'
    with path.open('x') as stream:
        stream.write(json.dumps(new, indent=2) + '\n')
    path.chmod(0o400)
    record = {'staged_at': (now or datetime.now(timezone.utc)).isoformat(), 'tool_sha256': config['files'][TOOL],
              'old_config': str(directory / 'config.json'), 'old_config_sha256': old['config_sha256'],
              'config': str(path), 'sha256': sha_bytes(path.read_bytes()),
              'previous_selection': previous, 'selection': selection, 'models_before': before, 'models_after': after,
              'executors': roles, 'runtime_revision': new['runtime_revision'], 'office_revision': new['office_revision']}
    write(record_directory / 'staged.json', record)
    return record, record_directory


def latest_staged(host):
    directories = sorted(d for d in paths(host)['transitions'].glob('2*Z') if (d / 'staged.json').is_file())
    if not directories:
        refuse('nothing is staged; run stage first')
    return directories[-1], read_json(directories[-1] / 'staged.json', 'staged record')


async def temporal():
    from temporalio.client import Client
    return await Client.connect(ENGINE[0], namespace=ENGINE[1])


async def raw_schedule(client):
    from google.protobuf.json_format import MessageToDict
    from temporalio.api.workflowservice.v1 import DescribeScheduleRequest
    return MessageToDict(await client.workflow_service.describe_schedule(
        DescribeScheduleRequest(namespace=ENGINE[1], schedule_id=WATCH)), preserving_proto_field_name=True)


async def schedule_argument(client):
    described = await client.get_schedule_handle(WATCH).describe()
    return described, await client.data_converter.decode(described.schedule.action.args)


async def work_in_progress(client):
    """Running executions that are doing something now, and the idle development ones a resumed step would run under."""
    busy, idle = [], []
    async for execution in client.list_workflows('ExecutionStatus = "Running"'):
        raw = (await client.get_workflow_handle(execution.id, run_id=execution.run_id).describe()).raw_description
        entry = {'id': execution.id, 'type': execution.workflow_type}
        if len(raw.pending_activities) or raw.HasField('pending_workflow_task'):
            busy.append(entry)
        elif execution.workflow_type != 'ServiceIdentity':
            idle.append(entry)
    return busy, idle


def alive(service):
    return {k: service[k]['pid'] for k in ('daemon', 'engine', 'worker')
            if service[k].get('identity') and process_identity(service[k]['pid']) == service[k]['identity']}


def backup(host, dest):
    with sqlite3.connect(paths(host)['database'], timeout=10) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    with sqlite3.connect('file:' + str(dest) + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('database backup failed its integrity check')
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return {'sha256': sha_bytes(Path(dest).read_bytes()), 'integrity': 'ok', 'tables': tables}


def startable(config):
    """Can this release's daemon start without the engine's help? Its own offline archive check, on its own bytes."""
    try:
        for name in daemon.HISTORICAL:
            daemon.archived_delivery(config, name)
        return True
    except Exception:
        return False


async def preconditions(host, record_directory, staged):
    """Everything activate needs, measured now. Refuses before anything is stopped or selected."""
    if staged.get('tool_sha256') != sha_bytes(Path(__file__).read_bytes()):
        refuse('this tool is not the one that staged the transition; stage again with this release own copy')
    new_path = Path(staged['config'])
    if new_path.is_symlink() or not new_path.is_file() or sha_bytes(new_path.read_bytes()) != staged['sha256']:
        refuse('the staged configuration changed since staging; stage again')
    old, raw = active_release(host)
    if old['config_sha256'] != staged['old_config_sha256']:
        refuse('the active selection changed since staging; stage again')
    new = json.loads(new_path.read_text()); only_models_differ(json.loads(raw), new)
    verify_files(new_path.parent, new['files'], 'staged file differs: ')
    try:
        resolved = models(new)
    except ValueError as error:
        refuse('this release refuses the staged selection: %s' % error)
    if resolved != staged['models_after'] or new['development'].get('models') != staged['selection']:
        refuse('the staged selection is not the one recorded at staging')
    new_plist = plist(new_path)
    client = await temporal(); before = await raw_schedule(client)
    if before['info'].get('running_workflows'):
        refuse('an AP10 watch run is in progress; activate later')
    upcoming = (before['info'].get('future_action_times') or [None])[0]
    if not upcoming or (datetime.fromisoformat(upcoming.replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() < LEAD_SECONDS:
        refuse('the next AP10 run is less than 20 minutes away (or unknown); activate later')
    reference, old_arg = await schedule_argument(client)
    if old_arg != [{'config_sha256': old['config_sha256'], 'mode': 'daily', 'obligation': WATCH}]:
        refuse('the AP10 schedule action is not bound to the active selection')
    old_service = read_json(paths(host)['service'], 'service receipt')
    if old_service.get('config_sha256') != old['config_sha256'] or len(alive(old_service)) != 3:
        refuse('the running service is not the recorded one')
    busy, idle = await work_in_progress(client)
    if busy:
        refuse('work is in progress in the engine: %s; activate later' % json.dumps(busy))
    try:
        startup = await daemon.delivered_histories(client, {**new, 'directory': str(new_path.parent)})
        for name in daemon.HISTORICAL:
            daemon.archived_delivery({**new, 'directory': str(new_path.parent)}, name)
        check_unfinished_writers(); check_private_processes()
    except Exception as error:
        refuse('the staged release could not pass its own daemon start requirements right now: %r' % error)
    if not startable(old):
        refuse('the active release could not start again after a stop, so there would be no way back; nothing was changed')
    return dict(new_path=new_path, new=new, old=old, new_plist=new_plist, client=client, before=before,
                reference=reference, old_arg=old_arg, old_service=old_service, busy=busy, idle=idle,
                next_ap10=upcoming, startup=startup)


def summary_of(staged, p):
    return {'would_activate': staged['sha256'], 'replacing': p['old']['config_sha256'],
            'selection': {'from': staged['previous_selection'], 'to': staged['selection']},
            'models_run': {'from': staged['models_before'], 'to': staged['models_after']}, 'executors': staged['executors'],
            'idle_development_workflows': p['idle'], 'next_ap10_run': p['next_ap10'],
            'new_daemon_start_requirements_now': p['startup'],
            'way_back': 'restore and restart the previous release (its own offline start check passed on its own bytes)'}


async def do_check(host):
    record_directory, staged = latest_staged(host); p = await preconditions(host, record_directory, staged)
    print(json.dumps({'check': 'every precondition holds; nothing was selected or stopped', 'staged': str(record_directory),
                      **summary_of(staged, p)}, indent=2, default=str))


async def do_activate(host):
    record_directory, staged = latest_staged(host); p = await preconditions(host, record_directory, staged)
    target = paths(host)['plist']; summary = summary_of(staged, p)
    say('Modellbyte: %s -> %s. Rollerna enligt releasen: %s. %s'
        % (json.dumps(staged['models_before']), json.dumps(staged['models_after']), json.dumps(staged['executors']),
           ('Vilande utvecklingskörningar som vid en återupptagning kör det nya valet: %s.' % json.dumps(p['idle'])) if p['idle']
           else 'Inga vilande utvecklingskörningar.'))
    say('En återgång FINNS: startar inte den nya versionen återställs och startas den nuvarande. AP10:s schema binds om först '
        'när den nya versionen bekräftats köra, och dess nästa körning %s ligger mer än 20 minuter bort.' % p['next_ap10'])
    directory = record_directory / ('activation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')); directory.mkdir(mode=0o700)
    write(directory / 'before.json', summary); write(directory / 'before-schedule.json', p['before'])
    write(directory / 'old-service.json', p['old_service']); write(directory / 'staged.json', staged)
    for name, source in (('old-active.json', paths(host)['active']), ('old-config.json', Path(p['old']['config_path'])), ('old.plist', target)):
        (directory / name).write_bytes(Path(source).read_bytes())
    (directory / 'new.plist').write_bytes(p['new_plist'])
    try:
        write(directory / 'online-backup.json', backup(host, directory / 'before-online.sqlite'))
    except Exception as error:
        refuse('backup before the stop failed (%r); nothing was stopped or selected' % error)
    # No write to the active selection before this exact controlled stop. From here on, never die silently.
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(number, signal.SIG_IGN)
    busy, _ = await work_in_progress(p['client'])              # again, immediately before the stop
    if busy:
        refuse('work started in the engine meanwhile: %s; nothing was stopped or selected' % json.dumps(busy))
    state = {'staged': staged, 'old_config_sha256': p['old']['config_sha256'], 'old_service': p['old_service'],
             'old_arg': p['old_arg'], 'stop_completed': False, 'old_worker_gone_at': None}
    write(directory / 'state.json', state)
    progress = {'point': 'stop requested; nothing selected'}
    try:
        await stop_service(state, directory, progress)
        state['stop_completed'] = True; replace(directory / 'state.json', (json.dumps(state, indent=2, default=str) + '\n').encode())
        await forward(host, state, directory, progress)
    except SystemExit:
        raise
    except BaseException as error:
        unexpected(error, progress, directory)


def unexpected(error, progress, directory):
    # Never die silently after the stop: say what is known. No start command is offered on a guess.
    say('VERKTYGET AVBRÖTS OVÄNTAT (%r) vid läget: %s. Det är INTE bekräftat att tjänsten kör. Kör INGET startkommando på egen '
        'hand; rapportera denna utskrift till Claude. Underlag: %s' % (error, progress['point'], directory))
    refuse('unexpected failure after the stop; see ' + str(directory))


async def stop_service(state, directory, progress):
    domain = 'gui/' + str(os.getuid()); old_service = state['old_service']
    write(directory / 'interruption.json', {'requested_at': datetime.now(timezone.utc).isoformat()})
    say('Tjänsten stoppas nu. Stäng inte terminalen förrän verktyget sagt sitt sista ord (Ctrl-C är avstängt).')
    stop = None
    try:
        stop = subprocess.run(['launchctl', 'bootout', domain + '/' + LABEL], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        pass
    write(directory / 'bootout.json', {'returncode': None if stop is None else stop.returncode, 'stderr': None if stop is None else stop.stderr})
    end = time.monotonic() + 90
    while alive(old_service) and time.monotonic() < end:
        await asyncio.sleep(.5)
    survivors = alive(old_service)
    if len(survivors) == 3 and (stop is None or stop.returncode != 0):
        say('STOPPET VÄGRADES AV SYSTEMET (%s). Tjänsten KÖR OFÖRÄNDRAD med sina tre processer %s. Ingenting har valts eller '
            'ändrats och inget behöver göras. Kör verktyget i en vanlig terminal i din egen inloggade session (inte via ssh eller '
            'sudo) och rapportera till Claude.' % ((stop.stderr.strip() if stop else 'tidsgräns'), survivors))
        refuse('the stop was refused; the service runs unchanged; see ' + str(directory))
    if survivors:
        say('STOPPET BLEV INTE KLART. Ingenting har valts. Dessa gamla processer lever kvar: %s. Tjänsten är troligen NERE. '
            'Starta INGENTING själv. Rapportera till Claude; när processerna är borta (kontroll: ps -p %s) fortsätter du med samma '
            'verktyg och ordet  forward.' % (survivors, ','.join(str(v) for v in survivors.values())))
        refuse('old service processes still present after the stop; see ' + str(directory))
    state['old_worker_gone_at'] = datetime.now(timezone.utc).isoformat()
    progress['point'] = 'stopped; nothing selected'


async def started(host, expected, not_pids):
    deadline = time.monotonic() + 90
    while True:
        try:
            receipt = json.loads(paths(host)['service'].read_text())
            pids = {(receipt[k]['pid'], receipt[k]['identity']) for k in ('daemon', 'engine', 'worker')}
            if receipt['config_sha256'] != expected or pids & not_pids or len(alive(receipt)) != 3:
                raise ValueError('no fresh live service receipt for the expected selection yet')
            fresh = await asyncio.wait_for(temporal(), 3)
            identity = await asyncio.wait_for(fresh.get_workflow_handle(receipt['identity_workflow']).query('describe'), 5)
            if identity != receipt['native_identity']:
                raise ValueError('native identity differs')
            return fresh, receipt
        except Exception:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(1)


def bootstrap(host):
    target = paths(host)['plist']; domain = 'gui/' + str(os.getuid())
    for attempt in range(4):
        result = subprocess.run(['launchctl', 'bootstrap', domain, str(target)], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return
        subprocess.run(['launchctl', 'bootout', domain + '/' + LABEL], capture_output=True, timeout=30)   # a loaded but dead label blocks bootstrap
        time.sleep(3)
    raise RuntimeError('launchctl bootstrap failed: ' + result.stderr.strip())


def start_diagnostics(host):
    found = {}
    try:
        log = Path(host) / '.runtime/ap10/launchd.stderr.log'
        found['launchd_stderr_tail'] = log.read_text(errors='replace')[-3000:] if log.is_file() else None
        launches = sorted((Path(host) / '.runtime/ap10/service-launches').iterdir(), key=lambda q: q.stat().st_mtime)
        found['newest_launch_directory'] = str(launches[-1]) if launches else None
    except Exception as error:
        found['diagnostics_error'] = repr(error)
    return found


async def rebind(client, old_arg, new_sha, reference):
    """ONLY the config hash of the AP10 schedule action changes; bounded retry; exact readback."""
    from temporalio.client import ScheduleUpdate
    handle = client.get_schedule_handle(WATCH); target_arg = [{**old_arg[0], 'config_sha256': new_sha}]

    async def update(inp):
        observed = inp.description.schedule; arg = await client.data_converter.decode(observed.action.args)
        if arg == target_arg:
            return None
        if (arg != old_arg or observed.spec != reference.schedule.spec or observed.policy != reference.schedule.policy
                or observed.state != reference.schedule.state or inp.description.info.running_actions):
            raise ValueError('AP10 schedule changed or is running; config hash NOT rebound')
        changed = copy.deepcopy(observed); changed.action.args = target_arg
        return ScheduleUpdate(schedule=changed)
    error = None
    for attempt in range(3):
        try:
            await asyncio.wait_for(handle.update(update), 30); error = None; break
        except Exception as caught:
            error = repr(caught); await asyncio.sleep(3)
    _, actual = await schedule_argument(client)
    return actual == target_arg, actual, error


async def complete_rebind(client, directory, staged):
    """Rebind ONLY the config hash, judged against the schedule as it was BEFORE the stop (saved by activate)."""
    before = json.loads((directory / 'before-schedule.json').read_text()); now = await raw_schedule(client)
    expected = copy.deepcopy(before['schedule']); actual = copy.deepcopy(now['schedule'])
    expected['action']['start_workflow']['input'] = actual['action']['start_workflow']['input']
    if expected != actual or now['info'].get('running_workflows'):
        return False, None, 'the AP10 schedule differs from the one before the stop beyond its input, or a run is in progress'
    reference, current = await schedule_argument(client)
    old_arg = [{'config_sha256': staged['old_config_sha256'], 'mode': 'daily', 'obligation': WATCH}]
    if current == [{**old_arg[0], 'config_sha256': staged['sha256']}]:
        return True, current, None
    return await rebind(client, old_arg, staged['sha256'], reference)


async def forward(host, state, directory, progress):
    staged = state['staged']; new_path = Path(staged['config']); target = paths(host)['plist']; domain = 'gui/' + str(os.getuid())
    stamp = lambda: datetime.now(timezone.utc).strftime('%H%M%S')
    old_pids = set((state['old_service'][k]['pid'], state['old_service'][k]['identity']) for k in ('daemon', 'engine', 'worker'))
    try:
        write(directory / ('stopped-backup-%s.json' % stamp()), backup(host, directory / ('after-stop-%s.sqlite' % stamp())))
        select(new_path); progress['point'] = 'NEW release selected on disk; service not yet confirmed'
        replace(target, plist(new_path)); bootstrap(host)
        client, receipt = await started(host, staged['sha256'], old_pids); progress['point'] = 'NEW release selected and its service confirmed running'
    except BaseException as error:
        problem = repr(error); restored = None
        try:
            write(directory / ('start-failure-%s.json' % stamp()), {'error': problem, **start_diagnostics(host)})
        except Exception:
            pass
        try:
            subprocess.run(['launchctl', 'bootout', domain + '/' + LABEL], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            pass
        try:
            replace(paths(host)['active'], (directory / 'old-active.json').read_bytes())
            replace(target, (directory / 'old.plist').read_bytes()); progress['point'] = 'PREVIOUS release restored on disk; service not yet confirmed'
        except BaseException as broken:
            say('ÅTERSTÄLLNINGEN PÅ DISK MISSLYCKADES (%r). Kopior av den tidigare versionen finns i %s (old-active.json, old.plist). '
                'Tjänsten är troligen nere. Rapportera till Claude innan något startas.' % (broken, directory))
            refuse('restore of the previous selection failed; see ' + str(directory))
        try:
            failed = json.loads(paths(host)['service'].read_text()); end = time.monotonic() + 45
            while failed.get('config_sha256') == staged['sha256'] and alive(failed) and time.monotonic() < end:
                time.sleep(.5)
            bootstrap(host); _, restored = await started(host, state['old_config_sha256'], old_pids)
        except BaseException as second:
            problem += ' | restore start: ' + repr(second)
        try:
            write(directory / 'rollback.json', {'error': problem, 'restored_service': restored, 'ap10_schedule': 'never rebound; bound to the previous selection'})
        except Exception:
            pass
        if restored:
            say('NYA TJÄNSTEN STARTADE INTE. Den tidigare versionen är återställd och KÖR igen (kontrollerat: nya processer, rätt '
                'konfiguration). AP10:s schema är orört. Inget mer behöver göras av dig; rapportera till Claude.')
        else:
            say('NYA TJÄNSTEN STARTADE INTE OCH ÅTERSTARTEN AV DEN GAMLA KUNDE INTE BEKRÄFTAS. Den tidigare versionen är återställd på '
                'disk. Tjänsten kan vara nere. Rapportera till Claude innan något startas.')
        refuse('activation failed (%s); see %s' % (problem, directory))
    problems = []
    try:
        done, actual, error = await complete_rebind(client, directory, staged)
        write(directory / ('rebind-%s.json' % stamp()), {'rebound': done, 'schedule_argument': actual, 'last_error': error})
        if not done:
            problems.append('AP10 schedule is still bound to %s while %s runs (%s)' % (actual, staged['sha256'], error))
    except Exception as error:
        problems.append('AP10 schedule rebind could not be completed or read back: %r' % error)
    try:
        before = json.loads((directory / 'before-schedule.json').read_text()); after = await raw_schedule(client)
        write(directory / ('after-schedule-%s.json' % stamp()), after)
        expected = copy.deepcopy(before['schedule']); actual = copy.deepcopy(after['schedule'])
        expected['action']['start_workflow']['input'] = actual['action']['start_workflow']['input']
        info_before = {k: v for k, v in before['info'].items() if k != 'update_time'}
        info_after = {k: v for k, v in after['info'].items() if k != 'update_time'}
        if expected != actual or info_before != info_after:
            problems.append('AP10 schedule differs beyond the config hash')
        if json.loads(paths(host)['active'].read_text()).get('sha256') != staged['sha256']:
            problems.append('the active selection is not the staged release')
        write(directory / ('after-service-%s.json' % stamp()), receipt)
    except Exception as error:
        problems.append('readback incomplete: %r' % error)
    final = {'completed': not problems, 'problems': problems, 'observed_at': datetime.now(timezone.utc).isoformat(),
             'config_sha256': staged['sha256'], 'replaced_config_sha256': state['old_config_sha256'],
             'selection': staged['selection'], 'models_run': staged['models_after'], 'executors': staged['executors'],
             'note': 'A model choice changes which model a development role starts; it starts no model and qualifies none.'}
    try:
        write(directory / ('transition-result-%s.json' % stamp()), final)
    except Exception:
        pass
    print(json.dumps(final, indent=2, default=str))
    if len(alive(receipt)) != 3:
        say('NYA VERSIONEN ÄR VALD men dess tjänst kunde INTE bekräftas köra vid slutkontrollen. Starta INGENTING själv; rapportera '
            'till Claude. Underlag: %s' % directory)
        refuse('the new service is not confirmed alive at the end; see ' + str(directory))
    if problems:
        say('NYA VERSIONEN KÖR (bekräftat nu), men efterkontrollen fann: %s. Om AP10-schemat inte är ombundet: kör den nya '
            'versionens kopia av verktyget,  %s -B %s rebind  (kräver inte launchctl). Rapportera till Claude.'
            % ('; '.join(problems), sys.executable, new_path.parent / TOOL))
        refuse('activated with readback problems; see ' + str(directory))
    say('KLART. Den nya versionen kör (bekräftat nu) med modellvalet %s, och AP10:s schema pekar på den. Inget mer behöver göras '
        'av dig.' % json.dumps(staged['models_after']))


def latest_activation(record_directory):
    directories = sorted(d for d in record_directory.glob('activation-2*Z') if (d / 'state.json').is_file())
    if not directories:
        refuse('no activation of the staged transition saved its state before a stop')
    return directories[-1]


async def do_forward(host):
    record_directory, staged = latest_staged(host); directory = latest_activation(record_directory)
    state = json.loads((directory / 'state.json').read_text())
    if staged.get('tool_sha256') != sha_bytes(Path(__file__).read_bytes()):
        refuse('this tool is not the one that staged the transition')
    if (state['staged'] != staged or sha_bytes(Path(staged['config']).read_bytes()) != staged['sha256']
            or not state.get('stop_completed') and alive(state['old_service'])):
        refuse('the saved state does not belong to the staged release, or the old service processes still live')
    if alive(read_json(paths(host)['service'], 'service receipt')):
        refuse('service processes are alive; forward is only for a stopped service')
    new_path = Path(staged['config']); new = json.loads(new_path.read_text())
    verify_files(new_path.parent, new['files'], 'staged file differs: ')
    if not startable({**new, 'directory': str(new_path.parent)}):
        refuse('the staged release could not pass its offline daemon start requirements')
    try:
        check_unfinished_writers(); check_private_processes()
    except Exception as error:
        refuse('an unfinished writer or private stage is recorded: %r' % error)
    state['old_worker_gone_at'] = datetime.now(timezone.utc).isoformat()
    replace(directory / 'state.json', (json.dumps(state, indent=2, default=str) + '\n').encode())
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(number, signal.SIG_IGN)
    progress = {'point': 'forward requested on a stopped service'}
    try:
        await forward(host, state, directory, progress)
    except SystemExit:
        raise
    except BaseException as error:
        unexpected(error, progress, directory)


async def do_rebind(host):
    record_directory, staged = latest_staged(host)
    if staged.get('tool_sha256') != sha_bytes(Path(__file__).read_bytes()):
        refuse('this tool is not the one that staged the transition')
    pointer = read_json(paths(host)['active'], 'active selection'); service = read_json(paths(host)['service'], 'service receipt')
    if pointer['sha256'] != staged['sha256'] or service.get('config_sha256') != staged['sha256'] or len(alive(service)) != 3:
        refuse('the staged release is not the active, verifiably running one; nothing to complete')
    directory = latest_activation(record_directory); client = await temporal()
    done, actual, error = await complete_rebind(client, directory, staged)
    write(directory / ('rebind-%s.json' % datetime.now(timezone.utc).strftime('%H%M%S')), {'rebound': done, 'schedule_argument': actual, 'last_error': error})
    print(json.dumps({'rebound': done, 'schedule_argument': actual, 'last_error': error, 'record': str(directory)}, indent=2))
    if not done:
        refuse('the AP10 schedule is still not bound to the active release')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=['show', 'stage', 'check', 'activate', 'forward', 'rebind'])
    parser.add_argument('--claude'); parser.add_argument('--codex')
    arguments = parser.parse_args(argv)
    if arguments.action != 'stage' and (arguments.claude or arguments.codex):
        refuse('a model is named only when staging')
    os.umask(0o077); host = host_root()
    if os.getuid() != host.stat().st_uid:
        refuse('run this as the owner of the Runtime directory, never with sudo')
    require_active_copy(host)
    if arguments.action == 'show':
        show(host)
    elif arguments.action == 'stage':
        record, record_directory = stage(host, {'claude': arguments.claude, 'codex': arguments.codex})
        tool = Path(record['old_config']).parent / TOOL
        print(json.dumps(record, indent=2))
        say('Förberett, ingenting är stoppat eller valt. Kontrollera sedan (ändrar inget):  %s -B %s check\n'
            'Byt därefter, i din egen terminal:  %s -B %s activate'
            % (sys.executable, tool, sys.executable, tool))
    elif arguments.action == 'check':
        asyncio.run(do_check(host))
    elif arguments.action == 'activate':
        asyncio.run(do_activate(host))
    elif arguments.action == 'forward':
        asyncio.run(do_forward(host))
    else:
        asyncio.run(do_rebind(host))


if __name__ == '__main__':
    main()
