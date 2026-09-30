"""Change the release's model choice through one reviewed, reusable controlled transition (D029, D040).

usage, as the owner of the Runtime directory, with the active release's own copy of this file:
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py show
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py stage [--claude MODEL] [--codex MODEL]
                                                                   [--runtime EXECUTOR/MODEL/EFFORT] [--watch EXECUTOR/MODEL/EFFORT]
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py check | activate | forward | rebind
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py auto
    <runtime venv python> -B <active release>/runtime/scripts/model_choice.py agent install | remove | show
`show` and `stage` print the exact paths; docs/runbook.md has the whole sequence.

D040 widens the choice to what the owner chooses in the workplace: the executor that drives every development role, its
model and its effort (`--runtime`), and the AP-10 watch's executor, model and effort (`--watch`). `auto` is the same
transition run by the workplace's recorded choice when Runtime is idle, from a LaunchAgent the owner starts once with
`agent install`; it waits while Runtime works, activates with the same way back, and records what it did.

D042 widens what the same agent does at each look: after the workplace's choice (D040), queued credential-free
measurements, run as the key-less test user through the one sudoers rule (scripts/measurement_queue.py), each kept away
from the AP-10 watch. The agent file itself does not change.

D022 made the model an explicit part of the frozen release configuration, changed only through a controlled release
transition, and every change so far needed its own derived transition script and its own review. This is that
transition written once, with the model as its parameter and `development.models` as the ONLY thing it can change.

stage     copies the ACTIVE release byte for byte into a new release directory and writes its configuration with only
          the choice replaced: `development.models`, `development.efforts`, `development.executors` and `watch`. The release's own code judges the choice, so a selection that release could
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
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import plistlib
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
# D040: the choice this transition may change, and nothing else.
CHOICE_KEYS = ('models', 'efforts', 'executors')          # under development; plus the top-level `watch`
REQUEST_SCHEMA = 'workplace-choice/1'
STATUS_SCHEMA = 'automatic-choice-status/1'
AGENT_LABEL = 'se.nortropic.ap10-runtime-choice'
AGENT_INTERVAL = 300                # seconds between the agent's looks; a switch waits at most this long after Runtime is idle
# Refusals that pass by themselves: auto waits and looks again. Every other refusal ends that request until it changes.
# The pinned Codex binary the startup chain launches, relative to the host; test_model_choice asserts it against
# worker_command() itself, so drift on either side fails a test instead of trusting a measurement of another binary.
CODEX_BINARY = '.runtime/bin/codex-0.155.1'
MEASUREMENT = 'evidence/partner/local/modellmatning.json'   # the workplace's own receipt, under the office root the release binds
FINAL = ('refused', 'restored', 'failed', 'interrupted')    # decided for this request; auto looks again only for a new one
WAITING = ('an AP10 watch run is in progress', 'the next AP10 run is less than 20 minutes away',
           'work is in progress in the engine', 'work started in the engine meanwhile', 'a web profile run is in progress',
           'the running service is not the recorded one')


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

from runtime import claude_profile, daemon, model_question, release           # noqa: E402
from runtime.development_model import ROLES, efforts, executors, models, watch  # noqa: E402
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
            'plist': Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist'),
            # D040: the workplace's recorded choice, what auto did with it, and the agent that runs auto
            'request': home / 'workplace-choice.json', 'status': home / 'automatic-choice-status.json',
            'lock': home / 'automatic-choice.lock', 'log': home / 'automatic-choice.log',
            'agent': Path.home() / 'Library/LaunchAgents' / (AGENT_LABEL + '.plist')}


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


def only_choice_differs(old, new):
    """The one invariant of this transition: the configurations are equal once the choice is set aside (D040).

    The choice is `development.models`, `development.efforts`, `development.executors` and the top-level `watch`.
    Everything else - files, revisions, scope, contract, amendments, guards, archives - is equal or it refuses.
    """
    a, b = copy.deepcopy(old), copy.deepcopy(new)
    for value in (a, b):
        if not isinstance(value.get('development'), dict):
            refuse('a configuration without a development selection has no model choice to change')
        for key in CHOICE_KEYS:
            value['development'].pop(key, None)
        value.pop('watch', None)
    if a != b:
        refuse('the staged configuration differs from the active one beyond the choice '
               '(development.models, development.efforts, development.executors, watch)')


def triple(text, what):
    """EXECUTOR/MODEL/EFFORT from the command line or the workplace's request; the release's own rules judge the values."""
    if isinstance(text, dict):
        parts = [text.get('executor'), text.get('model'), text.get('effort')]
        if set(text) != {'executor', 'model', 'effort'}:
            refuse(what + ' must name exactly executor, model and effort')
    else:
        parts = str(text).split('/')
    if len(parts) != 3 or not all(isinstance(part, str) and part for part in parts):
        refuse(what + ' must be EXECUTOR/MODEL/EFFORT, for example claude/claude-opus-5/high')
    return {'executor': parts[0], 'model': parts[1], 'effort': parts[2]}


def apply_choice(config, requested):
    """The configuration with the requested choice applied. Only the choice keys can change (only_choice_differs).

    requested: {'claude': MODEL|None, 'codex': MODEL|None, 'runtime': triple|None, 'watch': triple|None}. A runtime
    triple makes its executor drive EVERY development role, with that model and effort for that executor: the model
    the owner chooses decides which executor runs (D040). The other executor's model and effort are kept.
    """
    new = copy.deepcopy(config)
    development = new.get('development')
    if not isinstance(development, dict):
        refuse('the active release has no development selection to change')
    names = {executor: requested.get(executor) for executor in ('claude', 'codex') if requested.get(executor) is not None}
    if names:
        development['models'] = {**(development.get('models') or {}), **names}
    if requested.get('runtime') is not None:
        chosen = triple(requested['runtime'], '--runtime')
        development['executors'] = {role: chosen['executor'] for role in ROLES}
        development['models'] = {**(development.get('models') or {}), chosen['executor']: chosen['model']}
        development['efforts'] = {**(development.get('efforts') or {}), chosen['executor']: chosen['effort']}
    if requested.get('watch') is not None:
        new['watch'] = triple(requested['watch'], '--watch')
    return new


def choice_of(config):
    """What the release runs, by the release's own rules: executors per role, model and effort per executor, the watch."""
    return {'executors': executors(config), 'models': models(config), 'efforts': efforts(config), 'watch': watch(config)}


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
    status = paths(host)['status']
    print(json.dumps({'active_config_sha256': old['config_sha256'], 'release': old['directory'],
                      'selection': development.get('models'), 'models_run': models(config),
                      'efforts_run': efforts(config), 'executors': executors(config), 'watch': watch(config),
                      'tool': str(Path(old['directory']) / TOOL), 'questions': questions(config),
                      'automatic': json.loads(status.read_text()) if status.is_file() else None,
                      'measurements': read_optional(Path(host) / '.runtime/ap10/measurement-status.json'),
                      'agent_installed': paths(host)['agent'].is_file()}, indent=2, ensure_ascii=False))


def read_optional(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def stage(host, requested, code_root=CODE_ROOT, now=None, request_id=None):
    old, raw = active_release(host); directory = Path(old['directory'])
    if Path(code_root) != directory / 'runtime':
        refuse('this is not the active release own copy of the tool; run ' + str(directory / TOOL))
    config = json.loads(raw)
    if config['files'].get(TOOL) != sha_bytes((Path(code_root) / 'scripts/model_choice.py').read_bytes()):
        refuse('the active release does not bind these tool bytes')
    development = config.get('development')
    if not isinstance(development, dict):
        refuse('the active release has no development selection to change')
    if not any(requested.get(key) is not None for key in ('claude', 'codex', 'runtime', 'watch')):
        refuse('name a choice: --claude MODEL, --codex MODEL, --runtime EXECUTOR/MODEL/EFFORT and/or --watch EXECUTOR/MODEL/EFFORT')
    new = apply_choice(config, requested)
    previous, selection = development.get('models'), new['development'].get('models')
    try:
        before, after = choice_of(config), choice_of(new)    # the release's own rules, applied by the release's own code
    except ValueError as error:
        refuse('this release refuses the selection: %s' % error)
    if new == config:
        refuse('the selection is already %s; nothing to change' % json.dumps(after))
    only_choice_differs(config, new)
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
              'previous_selection': previous, 'selection': selection,
              'models_before': before['models'], 'models_after': after['models'],
              'efforts_before': before['efforts'], 'efforts_after': after['efforts'],
              'executors_before': before['executors'], 'executors': after['executors'],
              'watch_before': before['watch'], 'watch_after': after['watch'], 'request_id': request_id,
              'runtime_revision': new['runtime_revision'], 'office_revision': new['office_revision']}
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


def web_profile_runs():
    """Running web profile commands (D034-D037: runtime.web_measure, web_critique, web_visitor), as process ids.

    They run as host commands outside the engine, so the engine's work list does not show them, and a switch under one
    would leave its receipt naming a release that is no longer the active one. A process list that cannot be read
    counts as a run in progress: the switch waits rather than guesses.
    """
    try:
        listing = subprocess.run(['/bin/ps', '-axww', '-o', 'pid=,command='], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ['the process list could not be read']
    if listing.returncode != 0:
        return ['the process list could not be read']
    return ['pid ' + line.split()[0] for line in listing.stdout.splitlines()
            if re.search(r'-m\s+runtime\.web_(measure|critique|visitor)\b', line)]


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
    new = json.loads(new_path.read_text()); only_choice_differs(json.loads(raw), new)
    verify_files(new_path.parent, new['files'], 'staged file differs: ')
    try:
        resolved = choice_of(new)
    except ValueError as error:
        refuse('this release refuses the staged selection: %s' % error)
    if (resolved['models'] != staged['models_after'] or resolved['efforts'] != staged['efforts_after']
            or resolved['executors'] != staged['executors'] or resolved['watch'] != staged['watch_after']
            or new['development'].get('models') != staged['selection']):
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
    running = web_profile_runs()
    if running:
        refuse('a web profile run is in progress (%s); activate later' % ', '.join(running))
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
            'models_run': {'from': staged['models_before'], 'to': staged['models_after']},
            'efforts_run': {'from': staged['efforts_before'], 'to': staged['efforts_after']},
            'executors': {'from': staged['executors_before'], 'to': staged['executors']},
            'watch': {'from': staged['watch_before'], 'to': staged['watch_after']},
            'idle_development_workflows': p['idle'], 'next_ap10_run': p['next_ap10'],
            'new_daemon_start_requirements_now': p['startup'],
            'way_back': 'restore and restart the previous release (its own offline start check passed on its own bytes)'}


async def do_check(host):
    record_directory, staged = latest_staged(host); p = await preconditions(host, record_directory, staged)
    print(json.dumps({'check': 'every precondition holds; nothing was selected or stopped', 'staged': str(record_directory),
                      **summary_of(staged, p)}, indent=2, default=str))


async def do_activate(host, chosen=None):
    """The owner's activation of the newest staged record, or auto's of exactly the record it verified (chosen)."""
    record_directory, staged = chosen or latest_staged(host); p = await preconditions(host, record_directory, staged)
    target = paths(host)['plist']; summary = summary_of(staged, p)
    say('Modellbyte: %s -> %s. Ansträngning: %s -> %s. Bevakningen: %s -> %s. Rollerna enligt releasen: %s. %s'
        % (json.dumps(staged['models_before']), json.dumps(staged['models_after']),
           json.dumps(staged['efforts_before']), json.dumps(staged['efforts_after']),
           json.dumps(staged['watch_before']), json.dumps(staged['watch_after']), json.dumps(staged['executors']),
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
             'efforts_run': staged['efforts_after'], 'watch': staged['watch_after'], 'request_id': staged.get('request_id'),
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
    say('KLART. Den nya versionen kör (bekräftat nu) med modellvalet %s, ansträngningen %s och bevakningen %s, och AP10:s schema '
        'pekar på den. Inget mer behöver göras av dig.' % (json.dumps(staged['models_after']), json.dumps(staged['efforts_after']),
                                                           json.dumps(staged['watch_after'])))


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


def read_request(host):
    """The workplace's recorded choice (D040), or None when there is none. Untrusted input: a regular bounded file of
    exactly the recorded shape; the triples are judged by the release's own rules like any other choice."""
    path = paths(host)['request']
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        refuse('the workplace choice is not a regular file of bounded size')
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        refuse('the workplace choice is unreadable')
    if (not isinstance(value, dict) or value.get('schema') != REQUEST_SCHEMA
            or set(value) != {'schema', 'id', 'requested_at', 'runtime', 'watch'}
            or not isinstance(value['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value['id'])
            or not isinstance(value['requested_at'], str) or len(value['requested_at']) > 64):
        refuse('the workplace choice does not have the recorded shape')
    return {'id': value['id'], 'requested_at': value['requested_at'],
            'runtime': triple(value['runtime'], 'the runtime choice'), 'watch': triple(value['watch'], 'the watch choice')}


def measured(host, config, request):
    """Only what worked in the workplace's measurement of THIS host's pinned programs is activated automatically.

    The owner's rule is to offer only models and levels that demonstrably work on the subscription. The workplace offers
    only those; this checks it again where it matters, against the office's own receipt (modellmatning/2) under the
    office root the release binds, whose binaries must be exactly the ones the release launches.
    """
    receipt = Path(config['office_root']) / MEASUREMENT
    try:
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('not a regular bounded file')
        value = json.loads(receipt.read_text())
        if not isinstance(value, dict) or value.get('schema') != 'modellmatning/2':
            raise ValueError('not a modellmatning/2 receipt')
        binaries, results = value['binarer'], value['resultat']
        if not isinstance(binaries, dict) or not isinstance(results, list):
            raise ValueError('no binaries or results')
    except (OSError, ValueError, KeyError, TypeError) as error:
        refuse('the workplace measurement could not be read (%s); nothing is activated without it' % error)
    pinned = {'claude': str(Path(host) / '.runtime/bin' / ('claude-' + claude_profile.VERSION)),
              'codex': str(Path(host) / CODEX_BINARY)}
    for part in ('runtime', 'watch'):
        chosen = request[part]; program = chosen['executor'] + '_runtime'
        if chosen['executor'] not in pinned or (binaries.get(program) or {}).get('sokvag') != pinned[chosen['executor']]:
            refuse('the measurement of the %s choice was not made with this host pinned %s program' % (part, chosen['executor']))
        if not any(isinstance(row, dict) and row.get('program') == program and row.get('modell') == chosen['model']
                   and row.get('niva') == chosen['effort'] and row.get('ok') is True for row in results):
            refuse('the %s choice %s at %s did not work in the measurement of this host pinned %s program'
                   % (part, chosen['model'], chosen['effort'], chosen['executor']))


def read_status(host):
    try:
        value = json.loads(paths(host)['status'].read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_status(host, **fields):
    value = {'schema': STATUS_SCHEMA, 'checked_at': datetime.now(timezone.utc).isoformat(), **fields}
    replace(paths(host)['status'], (json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n').encode())
    return value


def reuse_or_stage(host, desired, request):
    """The newest staged record when it is exactly this request on the active release with this tool; else stage anew."""
    try:
        directory, staged = latest_staged(host)
    except SystemExit:
        directory, staged = None, None
    old = active_release(host)[0]
    content = (json.dumps(desired, indent=2) + '\n').encode()
    if (staged and staged.get('request_id') == request['id'] and staged.get('old_config_sha256') == old['config_sha256']
            and staged.get('sha256') == sha_bytes(content) and staged.get('tool_sha256') == sha_bytes(Path(__file__).read_bytes())):
        return directory, staged
    record, directory = stage(host, {'runtime': request['runtime'], 'watch': request['watch']}, code_root=CODE_ROOT,
                              request_id=request['id'])
    return directory, record


def outcome(host, record_directory, staged, text, unexpected=False):
    """What a refused or failed activation left behind: waiting, refused before the stop, restored, failed or active.
    An unexpected error before any stop (unexpected=True) is a wait: nothing was stopped or selected, and the next look
    measures everything again."""
    activations = sorted(record_directory.glob('activation-2*Z')) if record_directory else []
    last = activations[-1] if activations else None
    if last is not None and (last / 'rollback.json').is_file():
        try:
            restored = json.loads((last / 'rollback.json').read_text()).get('restored_service') is not None
        except (OSError, ValueError):
            restored = False
        return 'restored' if restored else 'failed'
    try:
        if json.loads(paths(host)['active'].read_text()).get('sha256') == staged['sha256']:
            return 'activated'                          # the new release runs; the reason names what the readback found
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if last is not None and (last / 'state.json').is_file():
        try:
            if json.loads((last / 'state.json').read_text()).get('stop_completed'):
                return 'failed'
        except (OSError, ValueError):
            return 'failed'
    return 'waiting' if unexpected or any(fragment in text for fragment in WAITING) else 'refused'


async def automatic(host):
    """The workplace's recorded choice, activated when Runtime is idle (D040). The owner's agent runs this every few
    minutes: nothing to do, the choice already in effect, waiting while Runtime works, or the same activation as the
    owner's, with the same way back. What happened is written to the status file the workplace reads."""
    handle = paths(host)['lock'].open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close(); return None                  # an earlier look is still running
    with handle:
        old, raw = active_release(host); config = json.loads(raw)
        base = {'active_config_sha256': old['config_sha256']}
        try:
            request = read_request(host)
        except SystemExit as refusal:
            return write_status(host, state='refused', request_id=None, reason=str(refusal), **base)
        if request is None:
            return write_status(host, state='none', request_id=None, reason=None, **base)
        base.update(request_id=request['id'], requested_at=request['requested_at'],
                    runtime=request['runtime'], watch=request['watch'])
        previous = read_status(host)
        if (previous and previous.get('request_id') == request['id'] and previous.get('state') in FINAL
                and previous.get('active_config_sha256') == old['config_sha256']):
            return previous                          # decided for this request; a new request is needed to try again
        carried = {k: previous[k] for k in ('activated_at', 'record') if previous and previous.get('request_id') == request['id']
                   and previous.get(k) is not None}
        # A look that finds its own earlier 'activating' was cut off before it could report (the lock is free, so it is not
        # running). Unless the switch completed, nothing more is tried automatically: the owner looks, and forward exists.
        cut_off = previous is not None and previous.get('request_id') == request['id'] and previous.get('state') == 'activating'
        record_directory = staged = None
        try:
            desired = apply_choice(config, {'runtime': request['runtime'], 'watch': request['watch']})
            try:
                wanted, running = choice_of(desired), choice_of(config)
            except ValueError as error:
                refuse('this release refuses the selection: %s' % error)
            if wanted == running:
                if cut_off:
                    carried.setdefault('activated_at', previous.get('checked_at'))
                return write_status(host, state='in_effect', reason=None, **base, **carried)
            if cut_off:
                return write_status(host, state='interrupted', record=previous.get('record'), **base,
                                    reason='an automatic activation of this request was cut off before it reported; nothing '
                                           'more is tried automatically. Read the record; if the service is down, the tool '
                                           'continues with forward')
            measured(host, config, request)
            record_directory, staged = reuse_or_stage(host, desired, request)
            await preconditions(host, record_directory, staged)
        except SystemExit as refusal:
            text = str(refusal)
            return write_status(host, state='waiting' if any(f in text for f in WAITING) else 'refused', reason=text,
                                record=str(record_directory) if record_directory else None, **base)
        except Exception as error:            # the engine could not be asked, for example; nothing was stopped: look again
            return write_status(host, state='waiting', reason='unexpected before any stop: %r' % (error,),
                                record=str(record_directory) if record_directory else None, **base)
        write_status(host, state='activating', reason=None, record=str(record_directory), **base)
        try:
            await do_activate(host, (record_directory, staged))     # exactly the record verified above, never a newer one
        except Exception as error:
            # before the stop do_activate raises on its own (after it, it reports through refuse); either way the record
            # directory says what happened
            text = 'unexpected: %r' % (error,)
            state = outcome(host, record_directory, staged, text, unexpected=True)
            now = active_release(host)[0]['config_sha256']
            return write_status(host, state=state, reason=text, record=str(record_directory), **{**base, 'active_config_sha256': now})
        except SystemExit as refusal:
            state = outcome(host, record_directory, staged, str(refusal))
            now = active_release(host)[0]['config_sha256']
            return write_status(host, state=state, reason=str(refusal), record=str(record_directory),
                                **{**base, 'active_config_sha256': now},
                                **({'activated_at': datetime.now(timezone.utc).isoformat()} if state == 'activated' else {}))
        return write_status(host, state='activated', reason=None, record=str(record_directory),
                            activated_at=datetime.now(timezone.utc).isoformat(),
                            **{**base, 'active_config_sha256': active_release(host)[0]['config_sha256']})


async def ap10_quiet(margin):
    """Heavy work - a measurement, a rehearsal - waits while the AP-10 watch runs or its next run is closer than the
    20-minute lead plus margin: the watch's analysis heartbeat has about two seconds to spare (measured 2026-09-30 07:01Z,
    when a publication and suites ran beside it). Refuses with the reason; returns the next run."""
    try:
        client = await temporal()
        described = await raw_schedule(client)
    except Exception as error:
        refuse('the AP10 schedule could not be read (%r); heavy work waits' % (error,))
    if described['info'].get('running_workflows'):
        refuse('an AP10 watch run is in progress; heavy work waits')
    upcoming = (described['info'].get('future_action_times') or [None])[0]
    if not upcoming or (datetime.fromisoformat(upcoming.replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds() < LEAD_SECONDS + margin:
        refuse('the next AP10 run is less than 20 minutes away (with room for heavy work: %d s); heavy work waits' % margin)
    return upcoming


def tick(host):
    """One look of the owner's agent: the workplace's choice (D040), then queued credential-free measurements (D042).
    A failure in one part is written to its own status and never stops the next part; nothing here stops or starts the
    service except an activation under its preconditions."""
    for part in ('choice', 'measurements'):
        try:
            if part == 'choice':
                asyncio.run(automatic(host))
            else:
                from scripts import measurement_queue
                measurement_queue.run_pending(host, quiet=lambda margin: asyncio.run(ap10_quiet(margin)))
        except SystemExit as refusal:
            print('%s %s: %s' % (datetime.now(timezone.utc).isoformat(), part, refusal), flush=True)
        except Exception as error:
            print('%s %s: unexpected %r' % (datetime.now(timezone.utc).isoformat(), part, error), flush=True)


def agent_plist(host):
    """The owner's LaunchAgent for auto. Its program resolves the ACTIVE release's own copy of this tool at every run,
    from the active pointer, so it always runs the bytes the active release binds; the tool refuses any other copy."""
    python = str(Path(host) / '.runtime/temporal-venv/bin/python')
    script = ('A="$(dirname "$("$0" -B -c \'import json,sys; print(json.load(open(sys.argv[1]))["config"])\' '
              '"$1/.runtime/ap10/active.json")")" && exec "$0" -B "$A/runtime/scripts/model_choice.py" auto')
    return {'Label': AGENT_LABEL, 'ProgramArguments': ['/bin/sh', '-c', script, python, str(host)],
            'EnvironmentVariables': {'LC_ALL': 'C', 'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'},
            'StartInterval': AGENT_INTERVAL, 'RunAtLoad': True, 'ProcessType': 'Background', 'Umask': 63,
            'StandardOutPath': str(paths(host)['log']), 'StandardErrorPath': str(paths(host)['log'])}


def agent(host, what):
    """install: the owner's one-time step - write the agent file and start it; remove: stop it and delete the file;
    show: print it and whether it is installed. Sessions cannot run launchctl; this is run in the owner's own terminal."""
    target = paths(host)['agent']; data = plistlib.dumps(agent_plist(host)); domain = 'gui/' + str(os.getuid())
    if what == 'show':
        print(data.decode()); print(json.dumps({'file': str(target), 'installed': target.is_file() and target.read_bytes() == data}))
        return
    if what == 'install':
        if target.exists() or target.is_symlink():
            if target.is_symlink() or target.read_bytes() != data:
                refuse('%s exists with other content; run agent remove first' % target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(0o644)
        loaded = subprocess.run(['launchctl', 'print', domain + '/' + AGENT_LABEL], capture_output=True, text=True, timeout=30)
        if loaded.returncode != 0:
            result = subprocess.run(['launchctl', 'bootstrap', domain, str(target)], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                refuse('launchctl bootstrap failed: ' + result.stderr.strip())
        say('Den automatiska aktiveringen är igång. Den tittar var %d:e sekund efter arbetsplatsens val för Runtime och '
            'bevakningen och byter bara när Runtime är ledigt, med samma väg tillbaka som vid ett handbyte. Stoppa den med: '
            '%s -B %s agent remove' % (AGENT_INTERVAL, sys.executable, Path(__file__).resolve()))
        return
    subprocess.run(['launchctl', 'bootout', domain + '/' + AGENT_LABEL], capture_output=True, text=True, timeout=30)
    if target.is_file() and not target.is_symlink():
        target.unlink()
    say('Den automatiska aktiveringen är stoppad och borttagen. Arbetsplatsens val ligger kvar men aktiveras inte förrän '
        'agenten installeras igen; ett byte kan alltid göras för hand med stage, check och activate.')


def exclusive(host):
    """The same lock auto holds, for the owner's own activate and forward: the two never interleave."""
    handle = paths(host)['lock'].open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        refuse('an automatic or manual activation holds the lock now; nothing was stopped or selected. Try again in a few minutes')
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=['show', 'stage', 'check', 'activate', 'forward', 'rebind', 'auto', 'agent'])
    parser.add_argument('what', nargs='?', choices=['install', 'remove', 'show'])
    parser.add_argument('--claude'); parser.add_argument('--codex'); parser.add_argument('--runtime'); parser.add_argument('--watch')
    arguments = parser.parse_args(argv)
    if arguments.action != 'stage' and (arguments.claude or arguments.codex or arguments.runtime or arguments.watch):
        refuse('a choice is named only when staging')
    if (arguments.action == 'agent') != (arguments.what is not None):
        refuse('agent takes install, remove or show, and no other action takes one')
    os.umask(0o077); host = host_root()
    if os.getuid() != host.stat().st_uid:
        refuse('run this as the owner of the Runtime directory, never with sudo')
    require_active_copy(host)
    if arguments.action == 'show':
        show(host)
    elif arguments.action == 'stage':
        with exclusive(host):                  # never between auto's check of its record and its activation
            record, record_directory = stage(host, {'claude': arguments.claude, 'codex': arguments.codex,
                                                    'runtime': arguments.runtime, 'watch': arguments.watch})
        tool = Path(record['old_config']).parent / TOOL
        print(json.dumps(record, indent=2))
        say('Förberett, ingenting är stoppat eller valt. Kontrollera sedan (ändrar inget):  %s -B %s check\n'
            'Byt därefter, i din egen terminal:  %s -B %s activate'
            % (sys.executable, tool, sys.executable, tool))
    elif arguments.action == 'check':
        asyncio.run(do_check(host))
    elif arguments.action == 'activate':
        with exclusive(host):
            asyncio.run(do_activate(host))
    elif arguments.action == 'forward':
        with exclusive(host):
            asyncio.run(do_forward(host))
    elif arguments.action == 'auto':
        tick(host)
    elif arguments.action == 'agent':
        agent(host, arguments.what)
    else:
        asyncio.run(do_rebind(host))


if __name__ == '__main__':
    main()
