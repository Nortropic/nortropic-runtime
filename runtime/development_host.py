"""Narrow host handoff from frozen Office policy to existing accepted tasks.

Temporal schedules these operations. Models return data; only reviewed active
Office code can prepare a draft, and only the independent approval can freeze it.
The candidates never receive this host's Git, scope or publication authority.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from .candidate import git
from .development_model import active_scope, executors
from .development_scope import identifier, decode
from .inspection import inspect
from .integration import Publisher, digest
from .private_stage import write
from .release import ROOT
from .snapshot import read_regular
from .task import load, task_directory
from .targets import OFFICE, repository


def sha(content):
    return hashlib.sha256(content).hexdigest()


def policy(config):
    source = Path(config['directory']) / 'office/tools/development_policy.py'
    spec = importlib.util.spec_from_file_location('active_office_development_policy', source)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(source.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def apply_integrated_a(repo, revision, destination, goal, reports):
    """Execute only fresh Git-object bytes, never a mutable candidate checkout.

    This exact two-file import closure is part of A's accepted small interface.
    No pre-existing Python cache or unreviewed dependency enters the sandbox.
    The extracted input and its object binding are retained for readback.
    """
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    (destination / 'tools').mkdir()
    (destination / '.scratch').mkdir()
    manifest = {}
    for name in ('tools/development_result.py', 'tools/kontor_result.py'):
        entry = git(repo, 'ls-tree', revision, '--', name).split()
        if len(entry) != 4 or entry[0] not in ('100644', '100755') or entry[1] != 'blob' or entry[3] != name:
            raise ValueError('Only the bound regular A import closure may execute')
        content = git(repo, 'show', revision + ':' + name, raw=True)
        (destination/name).write_bytes(content)
        (destination/name).chmod(0o400)
        manifest[name] = sha(content)
    write(destination/'binding.json', {'revision': revision, 'files': manifest})
    def verify():
        files = sorted(str(p.relative_to(destination/'tools')) for p in (destination/'tools').rglob('*') if p.is_file())
        if files != ['development_result.py', 'kontor_result.py']:
            raise ValueError('Unexpected executable dependency/cache')
        for name, expected in manifest.items():
            if sha(read_regular(destination, name)) != expected:
                raise ValueError('Bound executable source changed')
    from .profile import sandbox_command, environment
    script = ('import sys,json,pathlib;sys.path.insert(0,str(pathlib.Path("tools").resolve()));'
              'import development_result;data=json.load(sys.stdin);'
              'print(json.dumps(development_result.reconcile(data["goal"],data["reports"]),allow_nan=False))')
    command = sandbox_command(destination, ['/opt/homebrew/bin/python3.12', '-I', '-B', '-c', script])
    verify()
    observed = subprocess.run(command, env=environment(), input=json.dumps({'goal': goal, 'reports': reports}).encode(),
                              capture_output=True, timeout=30)
    verify()
    if observed.returncode or len(observed.stdout) > 262144:
        raise ValueError('Integrated A could not reconcile actual bound task result')
    result = decode(observed.stdout)
    write(destination/'observation.json', {'goal': goal, 'reports': reports, 'result': result})
    return result


def goal_amendments(config, contract):
    """Separately reviewed amendments of the frozen goal, bound by the release configuration.

    The contract and its hash never change: the scope and its consumed calls are keyed
    to them. An amendment has effect only together with an external review record that
    approves exactly its bytes as an amendment of exactly the contract's goal. Both are
    delivered wherever goal.md and authority.md are, so no role judges the chain against
    the unamended text alone. Absent means none; anything malformed is refused.
    """
    selected = (config.get('development') or {}).get('amendments', [])
    if not isinstance(selected, list) or len(selected) > 4:
        raise ValueError('Invalid bound goal amendments')
    directory = Path(config['directory']) / 'development-context'; files = {}
    for number, item in enumerate(selected, 1):
        if (not isinstance(item, dict) or set(item) != {'file', 'sha256', 'review', 'review_sha256'}
                or any(not isinstance(item[name], str) or Path(item[name]).name != item[name] for name in ('file', 'review'))
                or not item['file'].endswith('.md') or not item['review'].endswith('.json')):
            raise ValueError('Invalid bound goal amendments')
        content = read_regular(directory, item['file']); raw = read_regular(directory, item['review'])
        if sha(content) != item['sha256'] or sha(raw) != item['review_sha256']:
            raise ValueError('Bound goal amendment changed')
        record = decode(raw)
        if (not isinstance(record, dict) or record.get('verdict') != 'approved' or record.get('sha256') != item['sha256']
                or record.get('amends_sha256') != contract['acceptance_sha256']
                or not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip()):
            raise ValueError('Goal amendment has no review record approving exactly these bytes for this goal')
        files['GOAL_AMENDMENT_%d.md' % number] = content
        files['GOAL_AMENDMENT_%d_REVIEW.json' % number] = raw
    return files


def amendment_notice(files):
    return [{'path': name, 'sha256': sha(content), 'amends': 'goal.md',
             'review_record': name[:-3] + '_REVIEW.json',
             'meaning': 'Separately reviewed amendment of the frozen goal; read it together with goal.md'}
            for name, content in sorted(files.items()) if name.endswith('.md')]


def base_context(scope, config, work, key, *, paused_interactive_recovery=False):
    """Read actual integration and source objects before deriving a next task."""
    state = scope.inspect()
    # The explicit pre-task interactive recovery must bind its read-only context
    # before resuming the waiting parent. It cannot run a model or start a task.
    recovery_read = (paused_interactive_recovery is True and state['control']=='paused'
                     and work=='reconciliation' and key in ('interactive-retry-1','interactive-retry-2','interactive-retry-3','interactive-retry-4','interactive-retry-5')
                     and not state['tasks'] and not state['integrated'])
    if state['control'] != 'active' and not recovery_read:
        raise ValueError('No new preparation while finite goal is paused or stopped')
    active = policy(config)
    if work not in active.WORK or work in state['integrated']:
        raise ValueError('No accepted remaining work')
    contract = decode(read_regular(scope.directory, 'contract.json'))
    if contract['work'] != active.WORK:
        raise ValueError('Frozen Office policy and activated write bounds differ')
    repo = repository(OFFICE)
    git(repo, 'fetch', 'origin', 'main')
    base = git(repo, 'rev-parse', 'origin/main')
    delivered = {}; reports = {}; source = None; actual_result = None
    for logical, event in state['integrated'].items():
        task = load(event['task'])
        report = inspect(task['id'])
        if report.get('verified_delivery') is not True:
            raise ValueError('Previous task has no consistent saved delivery observation')
        receipt = event['receipt']
        if report.get('integration') != receipt:
            raise ValueError('Scope journal and actual Runtime receipt differ')
        # Do not rely on the result renderer's own output for remote truth.
        workspace = task_directory(task['id']) / report['state']['results'][-1]['workspace_name']
        publisher = Publisher(workspace, OFFICE)
        number = int(receipt['url'].rsplit('/', 1)[1])
        subject = {'candidate': receipt['candidate'], 'base': task['base']}
        remote = publisher.reconcile(publisher.api('pulls/' + str(number)), subject, receipt['tree'])
        if remote != receipt:
            raise ValueError('Actual remote integration differs')
        delivered[logical] = receipt
        reports[logical] = report
        if logical == 'reconciliation':
            source = git(repo, 'show', receipt['merge_commit'] + ':tools/development_result.py')
            # Apply A to its actual saved, independently checked Runtime result.
            # Even integrated candidate code executes through the existing
            # sandbox, never as privileged dynamic host code.
            goal_input = {'id': 'office-ap11', 'requirements': [
                {'id': 'A', 'text': 'AP11 leveransavstämning',
                 'task': {'id': task['id'], 'sha256': digest(task),
                          'acceptance_sha256': task['acceptance_sha256'], 'merge_commit': receipt['merge_commit']}},
                {'id': 'B', 'text': 'AP11 överlämning genom befintlig AP08', 'task': None}],
                'next_action': {'text': 'Bereda återstående AP08-överlämning från faktisk A-integration', 'authority': 'accepted'}}
            actual_result = apply_integrated_a(repo, receipt['merge_commit'],
                scope.directory/'applications'/identifier(key), goal_input, [report])
            if (not isinstance(actual_result, dict) or actual_result.get('whole_goal_complete') is not False
                    or actual_result.get('requirements', [{}])[0].get('status') != 'delivery_supported'):
                raise ValueError('Actual A application did not preserve supported delivery/remaining goal')
    expected_base = delivered['reconciliation']['merge_commit'] if delivered else config['office_revision']
    if base != expected_base:
        raise ValueError('Office base changed outside the observed dependent chain; preserve and diagnose')
    context_dir = Path(config['directory']) / 'development-context'
    authority = read_regular(context_dir, 'authority.md')
    goal = read_regular(context_dir, 'goal.md')
    if sha(authority) != contract['authority_sha256'] or sha(goal) != contract['acceptance_sha256']:
        raise ValueError('Frozen goal or owner authority changed')
    observed_at = datetime.now(timezone.utc).isoformat()
    observation = json.dumps({'observed_at': observed_at, 'integrated': delivered,
                              'reports': reports, 'base': base,
                              'actual_reconciliation_result': actual_result}, sort_keys=True).encode()
    materials = {'authority': authority, 'goal': goal, 'observation': observation}
    sources = [{'id': name, 'title': name, 'path': name+'.md',
                'version': sha(content), 'sha256': sha(content), 'size': len(content)}
               for name, content in materials.items()]
    recipe = read_regular(Path(config['directory']) / 'office', active.RECIPES[work])
    context = {'task_id': identifier('ap11-' + key), 'observed_at': observed_at,
               'base': base, 'runtime_revision': config['runtime_revision'],
               'acceptance_sha256': sha(recipe), 'work': work,
               # Frozen explicit choice for the child task's author and separate reviewer.
               'executors': {role: executors(config)[role] for role in ('implementation', 'review')},
               'integrated': delivered, 'reports': reports,
               'actual_reconciliation_source': source, 'actual_reconciliation_result': actual_result, 'sources': sources,
               'source_check': {'checked_at': observed_at,
                                'manifest': {'version': 1, 'files': [{k: s[k] for k in ('path', 'sha256', 'size')} for s in sources]},
                                'result': {'ok': True, 'files': [{'path': s['path'], 'status': 'ok'} for s in sources]}}}
    # Read only a named small source set, never internal source collections or
    # raw histories. All bytes delivered to the driver/reviewer are retained.
    files = {s['path']: materials[s['id']] for s in sources}
    files['VERIFICATION_RECIPE.py'] = recipe
    for name in ('tools/kontor_result.py', 'tools/agarbild.py', 'tools/development_result.py'):
        if name == 'tools/development_result.py' and source is None:
            continue
        files[name] = git(repo, 'show', base + ':' + name, raw=True)
    files['AGENTS.md'] = read_regular(Path(config['directory']) / 'office', 'AGENTS.md')
    amended = goal_amendments(config, contract)
    if amended:
        files.update(amended); context['goal_amendments'] = amendment_notice(amended)
    return context, files


NAMED_ENTRIES = {
    'AGENTS.md': 'instruction file of this workspace (the same text is the model system prompt)',
    'VERIFICATION_RECIPE.py': 'the FROZEN host verification recipe of this work: align proposed tests with it; never change or execute it',
    'tools/kontor_result.py': 'existing Office result reader (delivery evidence interpretation) to reuse, not to re-create',
    'tools/agarbild.py': 'existing AP08 owner-view reader to reuse, not to re-create',
    'tools/development_result.py': 'the ACTUALLY integrated A result module (delivered only once A is integrated)',
    'OUTPUT_SCHEMA.json': 'schema of the structured answer',
    'DRAFT.json': 'the driver draft under review',
    'HOST_DIAGNOSIS_ANSWERS.json': 'what the host itself answered to earlier diagnoses of this child: host facts, not a decision for you',
    'HOST_ANSWERS.json': 'every answer the host itself gave to a diagnosis in this goal: operator interventions, not autonomous continuation',
    'goal.md': 'frozen goal: its meaning and authority come from sources, not from this inventory',
    'authority.md': 'owner authority: its meaning comes from sources, not from this inventory',
    'observation.md': 'actual observation of integration and reports: its meaning comes from sources',
}
INVENTORY_NOTE = ('Complete inventory of every file delivered into this workspace, with exact workspace-relative path, SHA256 and '
                  'size. A reader whose tools cannot list directories finds files ONLY here: read exactly these paths and never '
                  'guess names. Presence in this inventory confers no authority and no meaning: authority, the frozen goal, its '
                  'amendments and the observation are given by sources and goal_amendments; code files are evidence and tools, '
                  'never a decision or a mandate. A listed file that cannot be read, or a needed file that is absent from this '
                  'inventory, is missing evidence.')


HOST_WRITTEN = ('CONTEXT.json', 'OUTPUT_SCHEMA.json')


def delivered_files(files):
    """What a reader without directory listing needs to find every delivered file: the host binding, restated per file."""
    entries = []
    for name, content in sorted(files.items()):
        meaning = NAMED_ENTRIES.get(name)
        if meaning is None and name.startswith('GOAL_AMENDMENT_'):
            meaning = 'separately reviewed goal amendment or its review record: meaning given by goal_amendments'
        if meaning is None and name.startswith('review-'):
            meaning = ("the host's own record of an earlier review run of this child: the bound that applied, how long "
                       'it ran, how it ended and how much it wrote. An empty or short event stream is evidence about '
                       'the HOST run, never a finding about the candidate')
        if meaning is None and name.startswith('previous-') and name.endswith('-acceptance.json'):
            meaning = ("the host's verdict on the frozen acceptance recipe for an earlier implementation attempt of "
                       'this child, without the failure text')
        if meaning is None and name.startswith('previous-'):
            meaning = "the host's own record of an earlier implementation run of this child, as the host measured it"
        entries.append({'path': name, 'sha256': sha(content), 'size': len(content), **({'meaning': meaning} if meaning else {})})
    return {'note': INVENTORY_NOTE, 'files': entries,
            'named_entries': [e['path'] for e in entries if e['path'] in NAMED_ENTRIES and e['path'] not in ('goal.md', 'authority.md', 'observation.md')]}


def prepare_call(expected, nonce, role, work, context, files, extra=None):
    scope, config = active_scope(expected)
    identifier(nonce)
    active = policy(config)
    stage = scope.directory / 'calls' / nonce
    stage.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = stage / 'workspace'; workspace.mkdir(mode=0o700)
    (workspace / '.scratch').mkdir(mode=0o700)
    files = {**files, 'OUTPUT_SCHEMA.json': json.dumps(active.schema(role, work)).encode()}
    if extra:
        files.update(extra)
    if 'CONTEXT.json' in files:
        raise ValueError('CONTEXT.json is written by the host, never delivered as a source')
    # The inventory is computed AFTER every other file is final and BEFORE CONTEXT.json exists, so it names everything a
    # reader can open; CONTEXT.json itself is bound by input.json's workspace_sha256 like every other file.
    context = {**context, 'delivered_files': delivered_files(files)}
    files['CONTEXT.json'] = json.dumps(context, ensure_ascii=False, indent=2).encode()
    if sum(len(value) for value in files.values()) > CONTEXT_BYTES.get(role, CONTEXT_BYTES[None]):
        raise ValueError('Selected development context exceeds its bound')
    for name, content in files.items():
        if (Path(name).is_absolute() or any(part in ('', '.', '..') for part in name.split('/'))
                or not name.endswith(('.md', '.json', '.py'))):
            raise ValueError('Only explicit selected context text is allowed')
        target = workspace / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o400)
    data = {'prompt': active.instructions(role, work), 'schema': active.schema(role, work),
            'work': work, 'role': role, 'seconds': 480,
            'workspace_sha256': {name: sha(content) for name, content in files.items()}}
    write(stage / 'input.json', data)
    return {'contract_sha256': expected, 'nonce': nonce, 'input_sha256': sha(read_regular(stage, 'input.json'))}


def call_result(scope, nonce, role=None):
    stage = scope.directory / 'calls' / identifier(nonce)
    result = decode(read_regular(stage, 'result.json'))
    if result.get('completed') is not True or result.get('process_group_removed') is not True:
        raise ValueError('Model result unavailable; preserve the actual incomplete call')
    if not result.get('provider', {}).get('thread_id'):
        raise ValueError('Actual native model identity unavailable')
    state = scope.inspect()
    call = next((e for e in state['calls'] if e['nonce'] == nonce), None)
    if not call or nonce not in state['started'] or role is not None and call['role'] != role:
        raise ValueError('Result has no matching counted role/start')
    raw = read_regular(stage, 'input.json')
    consumed = decode(read_regular(stage, 'consumed.json'))
    inputs = decode(raw)
    if (consumed != {'nonce': nonce, 'input_sha256': sha(raw)}
            or inputs['role'] != call['role'] or inputs['work'] != call['work']):
        raise ValueError('Result input or role binding changed')
    for name, expected in inputs['workspace_sha256'].items():
        if sha(read_regular(stage/'workspace', name)) != expected:
            raise ValueError('Previously delivered model context changed; preserve and reassess')
    return result


def draft_from_call(expected, nonce):
    scope, config = active_scope(expected)
    result = call_result(scope, nonce, 'driver')
    stage = scope.directory / 'calls' / nonce
    context = decode(read_regular(stage / 'workspace', 'CONTEXT.json'))
    packet = policy(config).prepare(context, result['answer'])
    packet.update(driver_nonce=nonce, driver_run=result['provider']['thread_id'], context=context)
    destination = scope.directory / 'drafts' / nonce
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    write(destination / 'draft.json', packet)
    return {'draft': nonce, 'sha256': sha(read_regular(destination, 'draft.json')), 'work': packet['work']}


def review_call(expected, draft_ref, nonce):
    scope, config = active_scope(expected)
    draft_dir = scope.directory / 'drafts' / identifier(draft_ref['draft'])
    raw = read_regular(draft_dir, 'draft.json')
    if sha(raw) != draft_ref['sha256']:
        raise ValueError('Task draft changed before independent review')
    packet = decode(raw)
    original = scope.directory / 'calls' / packet['driver_nonce'] / 'workspace'
    # Same bound inputs, fresh provider session and read-only context. The
    # implementer never supplies or writes this review's output/identity.
    binding = decode(read_regular(original.parent, 'input.json'))['workspace_sha256']
    # The driver's binding names every file of its workspace, including the two the host writes itself for every
    # role (CONTEXT.json and OUTPUT_SCHEMA.json); the reviewer's workspace gets its own of each from prepare_call,
    # so only the delivered sources are re-delivered (found by review D: re-delivering CONTEXT.json was refused).
    files = {name: read_regular(original, name) for name in binding if name not in HOST_WRITTEN}
    return prepare_call(expected, nonce, 'preparation-review', packet['work'], packet['context'],
                        files, {'DRAFT.json': raw})


def freeze(expected, draft_ref, review_nonce):
    scope, config = active_scope(expected)
    raw = read_regular(scope.directory / 'drafts' / identifier(draft_ref['draft']), 'draft.json')
    if sha(raw) != draft_ref['sha256']:
        raise ValueError('Reviewed draft changed')
    packet = decode(raw)
    reviewed = call_result(scope, review_nonce, 'preparation-review')
    review_input = scope.directory / 'calls' / review_nonce / 'workspace'
    if read_regular(review_input, 'DRAFT.json') != raw:
        raise ValueError('Review does not bind these actual draft bytes')
    if (reviewed['provider']['thread_id'] == packet['driver_run']
            or not policy(config).review(reviewed['answer'])):
        raise ValueError('Independent scope/verification approval is missing')
    if scope.inspect()['control'] != 'active':
        raise ValueError('No new frozen task while goal is paused or stopped')
    # Recheck selected sources and current base; do not overwrite reference
    # hashes to make an obsolete draft look current.
    context = packet['context']; repo = repository(OFFICE)
    git(repo, 'fetch', 'origin', 'main')
    if git(repo, 'rev-parse', 'origin/main') != context['base']:
        raise ValueError('Reviewed task base changed before freezing')
    if git(repo, 'diff', 'HEAD', '--name-only'):
        raise ValueError('Another uncommitted Office writer; no task handoff')
    task = {**packet['task'], 'development': {'contract_sha256': expected, 'work': packet['work']}}
    active = policy(config)
    if (task['acceptance'] != active.RECIPES[packet['work']]
            or task['allowed_paths'] != active.WORK[packet['work']]):
        raise ValueError('Generated task cannot select executable host code or expand paths')
    from .task import validate
    validate(task)
    # The delivered selection is data to the policy; the frozen task must carry
    # exactly the release's explicit author and reviewer, whoever prepared it.
    chosen = executors(config)
    if ({step.get('provider') for step in task['steps']} != {chosen['implementation']}
            or task.get('review_provider', 'codex') != chosen['review']):
        raise ValueError('Task executors differ from the frozen explicit selection')
    recipe = read_regular(Path(config['directory']) / 'office', task['acceptance'])
    if sha(recipe) != task['acceptance_sha256'] or read_regular(repo, task['acceptance']) != recipe:
        raise ValueError('Only the frozen previously reviewed host recipe is executable')
    # Technical task inputs remain in the existing repo/private local history.
    # Publisher later exports only explicit candidate source/test paths.
    brief = ('# Separately reviewed AP11 task\n\n' + packet['brief'] +
             '\n\nApproval binds this draft and its frozen host recipe; AP06 draft labels are preserved as history.\n')
    relative = 'tasks/' + task['id'] + '.json'
    for name, value in [(task['brief'], brief.encode()), (relative, json.dumps(task, indent=2).encode())]:
        with (repo/name).open('xb') as stream:
            stream.write(value)
    git(repo, 'add', '--', relative, task['brief'])
    git(repo, 'commit', '-m', 'Freeze independently reviewed finite AP11 task ' + task['id'], '--', relative, task['brief'])
    from .run import prepare
    frozen, _ = prepare(repo / relative)
    scope.bind_task(packet['work'], frozen['id'], digest(frozen), frozen['allowed_paths'],
                    sha(read_regular(scope.directory / 'calls' / review_nonce, 'result.json')))
    write(scope.directory / 'drafts' / draft_ref['draft'] / 'frozen.json',
          {'task': frozen, 'input_revision': git(repo, 'rev-parse', 'HEAD'), 'review_nonce': review_nonce})
    return frozen


HOST_ANSWERS = 'host-diagnosis'
# The keys the host itself writes into a diagnosis context. The diagnosis binds to the task and the observed wait;
# these are the host's own delivered material and are excluded where the returned diagnosis is bound back to the wait.
DIAGNOSIS_HOST_KEYS = ('delivered_files', 'host_bounds', 'host_answers')


ANSWER_LIMIT = 8000   # the same bound the diagnosis reason already carries; see recovery_request
EVENT_STREAM_LIMIT = 262144   # what read_regular reads in one piece


def host_answers(scope, task_id=None):
    """Every answer the HOST itself gave to a diagnosis, oldest first. They carry no content for the model to copy:
    each one states a host fact and why it changed, and the model still decides what follows from it.

    An entry that cannot be read is REPORTED as unreadable instead of raising. Found by review E: reading raised for
    the whole scope if a single answer file was oversized or malformed, which took every future diagnosis with it --
    and the only command out of that wait reads the same directory, so the scope could not be recovered from within.
    An unreadable answer states no fact, so it never carries a host answer's authority either (see recovery_request).
    """
    directory = scope.directory / HOST_ANSWERS
    if not directory.is_dir() or directory.is_symlink():
        return []
    answers = []
    for path in sorted(p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and p.suffix == '.json'):
        try:
            entry = decode(read_regular(directory, path.name))
        except (ValueError, OSError):
            answers.append({'unreadable': path.name, 'note': 'A recorded host answer that can no longer be read: '
                                                             'treat it as absent evidence, never as a host fact'})
            continue
        if task_id is None or entry.get('task') == task_id:
            answers.append(entry)
    return answers


def host_answer_facts(scope, task_id):
    """The readable answers actually bound to this child. Only these are host facts."""
    return [a for a in host_answers(scope, task_id)
            if 'unreadable' not in a and isinstance(a.get('reason'), str) and a['reason'].strip()]


def check_host_answer(scope, reason):
    """Everything that can refuse an answer, checked WITHOUT writing anything.

    Found by review G: the continuation signal is sent first (so a recorded answer never outlives an undelivered
    signal), which means a refusal at the write would consume the operator's one continuation and record nothing,
    leaving the parent out of the phase the command requires. So the refusals run before the signal too.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Explicit host diagnosis answer required')
    # Bounded, so an answer the host records is always an answer the host can read back.
    if len(reason) > ANSWER_LIMIT:
        raise ValueError('Unbounded host diagnosis answer')
    directory = scope.directory / HOST_ANSWERS
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError('Host answer directory is not a directory')
    return directory


def record_host_answer(scope, reason, task_id, observed):
    """Written by the host's own continuation command, never by a model. Append only; nothing earlier is rewritten."""
    directory = check_host_answer(scope, reason)
    directory.mkdir(mode=0o700, exist_ok=True)
    entry = {'observed_at': datetime.now(timezone.utc).isoformat(), 'task': task_id, 'reason': reason,
             'parent_phase': observed.get('phase'), 'parent_sequence': observed.get('sequence'),
             'source': 'host operator continuation; no model ran and no call was counted'}
    # Numbered from the highest name present, not from how many are readable: a removed or unreadable file must not
    # make the next answer collide with an existing one.
    used = [p.name[7:10] for p in directory.iterdir() if p.is_file() and p.name.startswith('answer-')]
    number = 1 + max([int(t) for t in used if t.isdigit()] or [0])
    write(directory / (identifier('answer-%03d' % number) + '.json'), entry)
    return entry


def review_attempts(task_id):
    """The review attempt numbers this child actually has host evidence for, oldest first."""
    from .task import evidence_directory
    directory = evidence_directory(task_id)
    if not directory.is_dir() or directory.is_symlink():
        return []
    numbers = []
    for path in directory.iterdir():
        tail = path.name[7:]
        if path.name.startswith('review-') and tail.isdigit() and path.is_dir() and not path.is_symlink():
            numbers.append(int(tail))
    return sorted(numbers)


# Host-MEASURED scalars only. Found by review I on measured bytes: `permission_denials` carries the interrupted
# model's own tool input, including absolute host paths, and `usage` carries account-shaped fields; both are reduced
# to a host-derived value below rather than delivered. A field belongs here only if the host itself measured it AND
# its value comes from the host's own vocabulary. `interrupted` qualifies only because it is classified below: found
# by review L, attempt.py sets it to str(error) on a host error, which carries an absolute path.
# 'model' and 'reported_model' are named model ids, not host text: which model was started and which one the
# provider said it was. A release that changes only the selection keeps the same runtime_revision, so without
# these a diagnosis could not tell two otherwise identical runs apart.
# How much selected context a role may be delivered. Every role keeps the 2 MiB it has always had. The
# whole-goal review is the one role whose subject IS the whole goal: it is delivered the complete native
# history of the parent and both children, the scope journal, both remote integrations, the host's own account
# and the named artefacts the acceptance points at. Measured on this goal, that material is about 2.1 MB, so
# the old bound would force a choice between refusing the delivery and shortening the evidence - and a
# whole-goal review that cannot see the whole goal is the defect this release exists to correct.
#
# This is a deliberate widening of ONE role's context bound, not a general one. It buys room for evidence, not
# for looser rules: every other guard stands, the per-file reader bound is unchanged, nothing is truncated, and
# anything still undelivered remains an explicit gap rather than a silence.
#
# Raised again on 2026-09-24 under the owner's words that what is required is done (D027): each further assessment
# adds its own history, decision, review and run record, and measured before the sixth assessment the 3 MiB bound
# already delivered the first part of the application's history as a named gap to the one review that examines the
# whole. The 4 MiB figure is the operator session's choice.
CONTEXT_BYTES = {None: 2*1024*1024, 'final-review': 4*1024*1024}

RUN_FIELDS = ('attempt', 'elapsed_seconds', 'exit_code', 'provider_completed', 'model_started', 'process_group_removed',
              'model', 'reported_model')
REVIEW_RUN_FIELDS = RUN_FIELDS            # the name the earlier releases used for this set
# Every value attempt.py assigns to `interrupted` from its own words. Anything else is a host error string.
HOST_INTERRUPTIONS = ('deadline', 'signal', 'active instruction/configuration binding changed')


def run_record(task_id, area, number):
    """The host's own record of one model run of this child, as a bounded JSON object.

    The raw files are deliberately NOT delivered. The event stream's name is not one the delivery point accepts;
    launch.json carries the host's own account state, absolute host paths, the provider argv and process ids; and
    result.json carries the provider's own usage, denied tool calls, thread id, reported cost, the run's evidence
    path and its scope reservation. What a diagnosis needs in order to tell a host failure from a model one is the
    bound that applied, how long the process ran, how it ended and whether it wrote anything at all; those are
    measured here from the host's own files, field by named field. An empty stream is reported as empty, because the
    emptiness is the evidence. A run the host cannot read is reported as unreadable rather than omitted, so a
    diagnosis can tell that from "no run at all"; a run that never happened yields no record.
    """
    from .task import evidence_directory
    directory = evidence_directory(task_id) / (area + '-' + str(number))
    label = 'review' if area == 'review' else 'implementation'
    record = {area + '_number': number,
              'note': "The host's own record of this " + label + " run. An empty or short event stream is evidence "
                      'about the HOST run, never a finding about the candidate.'}
    if not directory.is_dir() or directory.is_symlink():
        return None                                    # no such run; saying anything about it would be an invention
    try:
        result = decode(read_regular(directory, 'result.json'))
    except (OSError, ValueError):
        result = None
    if not isinstance(result, dict):
        return {**record, 'unavailable': 'the host could not read its own record of this run'}
    record.update({name: result[name] for name in RUN_FIELDS if name in result})
    # Classified, never passed through: the host's own words go out as they are, anything else says only that the
    # host failed to start or hold the run.
    interrupted = result.get('interrupted')
    if interrupted is not None:
        record['interrupted'] = interrupted if interrupted in HOST_INTERRUPTIONS else 'host error while running it'
    # Whether the run was denied a tool, and whether it reported any usage at all, are useful to a diagnosis; the
    # denials themselves and the usage object are not the host's own text, so only these values are delivered.
    denials = result.get('permission_denials')
    record['permission_denials'] = len(denials) if isinstance(denials, list) else ('none reported' if denials is None else 'unreadable')
    record['usage_reported'] = isinstance(result.get('usage'), dict)
    try:
        launch = decode(read_regular(directory, 'launch.json'))
        if isinstance(launch, dict) and type(launch.get('seconds_limit')) is int:
            record['bound_seconds'] = launch['seconds_limit']
    except (OSError, ValueError):
        pass
    # The size is measured from the file itself, so an oversized stream is never described as something else; the
    # lines are counted only when the host can actually read it (found by review I: every read_regular ValueError
    # was reported to the model as an oversize claim, and real streams already approach the read bound). A failed
    # read never discards the size the host already measured (review L).
    stream = directory / 'events.jsonl'
    try:
        if stream.is_symlink() or not stream.is_file():
            record['events_bytes'] = 'no regular event stream'
        else:
            record['events_bytes'] = stream.stat().st_size
            if record['events_bytes'] <= EVENT_STREAM_LIMIT:
                record['events_lines'] = len([line for line in read_regular(directory, 'events.jsonl').splitlines() if line.strip()])
    except (OSError, ValueError):
        record.setdefault('events_bytes', 'no readable event stream')
    return record


def review_run_record(task_id, number):
    return run_record(task_id, 'review', number)


# The host's own verdict on the frozen recipe. Everything here is written by the host or by the frozen, separately
# reviewed verifier - except the failure text. Found by review L and proven by execution: activities.py records a
# failed freeze as {'passed': False, 'reason': str(error)}, and a CalledProcessError stringifies the whole git argv,
# so that text names absolute host paths. The verdict is what a diagnosis needs; the text is not.
ACCEPTANCE_FIELDS = ('passed', 'scope', 'checks', 'candidate_files_sha256')
# What a frozen verifier's own REJECTION may carry into a model workspace. Measured by review L on the live recipe:
# its failure branch returns up to 6000 bytes of raw subprocess stderr, and that stderr names absolute host paths.
# The recipe's own verdict fields are its words; the output it collected from a subprocess is not.
VERIFIER_FIELDS = ('passed', 'scope', 'checks', 'failed', 'reason', 'verifier_incomplete')
VERIFIER_LIMIT = 4000


def acceptance_record(task_id, number):
    """The host's acceptance verdict for one implementation attempt, without the failure text.

    A failure still reaches the diagnosis as a failure, and as the KIND of failure that matters here: the host's own
    tooling failed rather than the candidate. What it does not reach it as is a Git or OS error string naming this
    host's paths.
    """
    from .task import evidence_directory
    try:
        verdict = decode(read_regular(evidence_directory(task_id) / ('attempt-' + str(number)), 'acceptance.json'))
    except (OSError, ValueError):
        return None
    if not isinstance(verdict, dict):
        return None
    record = {name: verdict[name] for name in ACCEPTANCE_FIELDS if name in verdict}
    if verdict.get('passed') is True:
        return record
    # The cause is read from the marker activities.py writes where the failure happens, never inferred from the
    # record's shape. Review L measured a shape test going wrong in both directions against the LIVE recipe: its
    # rejection branch returns exactly {'passed', 'reason'}, which a shape test reads as the host's own failure.
    inner = verdict.get('details')
    if verdict.get('host_error') is True:
        record['withheld'] = ('The host recorded why this acceptance run failed, but that text is an OS or Git error '
                              "naming host paths, so it is not delivered. The host's own tooling raised while freezing "
                              'or verifying the candidate. This is not the frozen verifier\'s verdict on the candidate; '
                              'it may itself have been caused by what the candidate did, such as writing outside the '
                              'paths the task allows.')
    elif verdict.get('verifier_rejected') is True:
        named = {k: v for k, v in inner.items() if k in VERIFIER_FIELDS} if isinstance(inner, dict) else {}
        if len(json.dumps(named, ensure_ascii=False)) > VERIFIER_LIMIT:
            named = {'passed': False, 'oversized': 'the verifier verdict is larger than the host delivers'}
        record['verifier_verdict'] = named
        record['note'] = (('The frozen verifier did not complete on this candidate: it may never have started, so '
                           'this is not its verdict.') if isinstance(inner, dict) and inner.get('verifier_incomplete') is True
                          else ('The frozen verifier ran and did not pass the candidate. These are its own verdict '
                                'fields: a finding about the candidate, not a host failure.')) + (
                          ' Anything else it collected, including subprocess output, is not delivered.')
    else:
        # Written before the host marked its own cause. Asserting either cause would be an invention, and the text
        # cannot be delivered because in one of the two cases it is an OS or Git error naming host paths.
        record['cause_unrecorded'] = ('This acceptance run predates the host marking its own cause, so the host '
                                      'cannot say whether its own tooling failed or the frozen verifier rejected the '
                                      'candidate, and it delivers neither text.')
    return record


def host_bounds(task):
    """The bounds of the ACTIVE release that apply to this task. A bound that cannot be derived is reported as such:
    a diagnosis must never fail because the host could not describe itself."""
    from .development_binding import activity_seconds, model_seconds
    note = ('The bounds of the ACTIVE release. Evidence produced under an earlier release may have had other bounds; an '
            'interruption at a bound is a host failure, never a candidate defect, and a bound that has changed since the '
            'evidence was produced is a materially changed prerequisite.')
    undetermined = {'note': note, 'undetermined': 'This task does not carry the bounded profile the host derives its bounds from'}
    try:
        if type(task.get('attempt_seconds')) is not int:
            return undetermined
        return {'note': note, 'implementation_model_seconds': task['attempt_seconds'],
                'review_model_seconds': model_seconds(task, 'review'),
                'review_activity_seconds': activity_seconds(task, 'review')}
    except (KeyError, TypeError, ValueError):
        return undetermined


def diagnosis_call(expected, task_id, state, nonce):
    scope, config = active_scope(expected)
    bound = scope.inspect()['tasks'].get(task_id)
    if not bound:
        raise ValueError('Cannot diagnose unrelated work')
    task = load(task_id, bound['task_sha256'])
    if state.get('phase') not in ('waiting_diagnosis', 'waiting_review'):
        raise ValueError('Only the existing diagnosed implementation/review waits are supported')
    files = {'TASK.md': read_regular(task_directory(task_id), 'brief.md'),
             'VERIFICATION_RECIPE.py': read_regular(task_directory(task_id), 'acceptance.py'),
             'goal.md': read_regular(Path(config['directory'])/'development-context', 'goal.md'),
             'authority.md': read_regular(Path(config['directory'])/'development-context', 'authority.md'),
             'AGENTS.md': read_regular(Path(config['directory'])/'office', 'AGENTS.md')}
    files.update(goal_amendments(config, decode(read_regular(scope.directory, 'contract.json'))))
    from .task import evidence_directory
    # The implementation attempts, through the SAME host record. Found by review L: previous-N-result.json was a raw
    # copy of the provider's own result, carrying every field the review record had just been narrowed to exclude -
    # its usage, denied tool calls, thread id, reported cost, evidence path and scope reservation. Nothing binds
    # these files, so unlike the child's own wait state they can be narrowed, and they are. The acceptance record is
    # the host's own verdict on the frozen recipe and is delivered as it is.
    for result in state.get('results', [])[-2:]:
        number = result.get('attempt')
        if type(number) is not int or number < 1:
            continue
        record = run_record(task_id, 'attempt', number)
        if record:
            files['previous-'+str(number)+'-run.json'] = json.dumps(record, ensure_ascii=False, indent=2).encode()
        verdict = acceptance_record(task_id, number)
        if verdict:
            files['previous-'+str(number)+'-acceptance.json'] = json.dumps(verdict, ensure_ascii=False, indent=2).encode()
    # The review's OWN run record. Without it a diagnosis cannot tell a host kill from a provider stall and can only
    # hold: measured 2026-09-22, the cut-off review left an EMPTY event stream and a 182.2 s result under a 180 s
    # bound, and the diagnosis said in its own words that it could not justify a re-run without it.
    for number in review_attempts(task_id)[-2:]:
        record = review_run_record(task_id, number)
        if record:
            files['review-'+str(number)+'-run.json'] = json.dumps(record, ensure_ascii=False, indent=2).encode()
    # The readers the frozen goal names. Every other role that judges this candidate receives them; the diagnosis
    # did not, and said so. Same named set, same source, at the task's own base.
    for name in ('tools/kontor_result.py', 'tools/agarbild.py'):
        try:
            files[name] = git(repository(OFFICE), 'show', task['base'] + ':' + name, raw=True)
        except (KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    latest = state.get('results', [])[-1] if state.get('results') else {}
    workspace = task_directory(task_id) / latest.get('workspace_name', 'candidate')
    for name in task['allowed_paths']:
        files[name] = read_regular(workspace, name)
    # The bounds that actually applied to the evidence above, and the host's own earlier answers: without them a host
    # failure can only ever be read as "nothing changed" (measured 2026-09-22, when a review cut off at its bound left
    # the diagnosis with no materially changed prerequisite it could see).
    answers = host_answers(scope, task_id)
    # Anything added here that the diagnosis does not bind to belongs in DIAGNOSIS_HOST_KEYS, or recovery_request
    # refuses every non-hold diagnosis that follows.
    context = {'task': task, 'actual_child_wait': state, 'host_bounds': host_bounds(task), 'host_answers': answers}
    if answers:
        files['HOST_DIAGNOSIS_ANSWERS.json'] = json.dumps(answers, ensure_ascii=False, indent=2).encode()
    return prepare_call(expected, nonce, 'diagnosis', bound['work'], context, files)


def recovery_request(scope, task_id, state, nonce):
    result = call_result(scope, nonce, 'diagnosis')
    answer = result['answer']
    if (type(answer) is not dict or set(answer) != {'action', 'reason', 'changed_prerequisite'}
            or any(type(answer[k]) is not str or not answer[k].strip() for k in answer)):
        raise ValueError('Concrete diagnosis and changed prerequisite required')
    if answer['action'] == 'hold':
        return {'hold': True, 'reason': answer}
    task = load(task_id, scope.inspect()['tasks'][task_id]['task_sha256'])
    context = decode(read_regular(scope.directory/'calls'/nonce/'workspace', 'CONTEXT.json'))
    # What the HOST itself adds to a diagnosis workspace is not part of what the diagnosis binds to: the diagnosis
    # binds to the task and the observed wait, exactly as before. Found by review C when the delivered-file
    # inventory was added, and it would have happened again when the bounds and the host's answers were added:
    # a bare comparison refuses every non-hold diagnosis. DIAGNOSIS_HOST_KEYS is the one place both sides agree.
    if {k: v for k, v in context.items() if k not in DIAGNOSIS_HOST_KEYS} != {'task': task, 'actual_child_wait': state}:
        raise ValueError('Diagnosis does not apply to the current observed wait')
    expected = state.get('review_recovery') if state['phase'] == 'waiting_review' else 'retry'
    if answer['action'] != expected:
        raise ValueError('Missing review/host fault must not become a candidate repair')
    # Free model text cannot establish that a quota/access/host prerequisite
    # changed. Those waits need actual host inspection and native recovery.
    # The only automatic model-derived continuation is a bounded candidate
    # repair supported by an actual independently bound code-review rejection.
    # Free model text cannot establish that a host prerequisite changed. The host's OWN recorded answer can: it is
    # written only by the host operator's continuation command, never by a model, and it states a measured host fact.
    # Where such an answer exists for this child, an interrupted review may be re-run. The model still decides the
    # action, it must still be the one the host measures, and the repeat guard below binds the answer itself, so the
    # same host fact cannot justify a second identical continuation.
    answered = host_answer_facts(scope, task_id)
    if expected != 'repair' and not (expected == 'review_only' and answered):
        return {'hold': True, 'reason': 'No host-verified prerequisite change; model text is not recovery authority',
                'diagnosis': answer}
    from .review import recovery_kind
    latest = state['results'][-1]
    subject = {'task_id': task['id'], 'task_sha256': digest(task), 'base': task['base'],
               'candidate': latest['candidate'], 'completed_steps': list(range(len(task['steps']))),
               'acceptance_sha256': task['acceptance_sha256'],
               'implementation_runs': [x['thread_id'] for x in state['results'] if x.get('thread_id')]}
    tests = {k: subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
    tests.update(scope='whole_task', terminal_status='completed', passed=latest.get('phase_acceptance_passed') is True)
    measured = recovery_kind(task, subject, tests, state.get('review'))
    if expected == 'repair' and (latest.get('provider_completed') is not True or measured != 'repair'):
        return {'hold': True, 'reason': 'No independently bound candidate rejection supports repair'}
    if expected != 'repair' and measured != expected:
        return {'hold': True, 'reason': 'The host no longer measures this wait the way the diagnosis does',
                'diagnosis': answer}
    # For repair the binding is the rejection that supports it, unchanged. For a host-answered continuation it is the
    # ANSWER, never the review record: found by review G, a re-run writes a new attempt number, evidence path and
    # reservation nonce into state['review'], so binding on that let one host answer authorize an unbounded chain of
    # automatic re-runs. Bound this way, a second continuation needs a second host fact.
    finding_binding = (digest({'subject': subject, 'review': state['review']}) if expected == 'repair'
                       else digest({'subject': subject, 'host_answer': answered[-1]}))
    reason = 'Diagnosis: '+answer['reason']+'\nChanged prerequisite: '+answer['changed_prerequisite']
    if len(reason) > 8000:
        raise ValueError('Unbounded diagnosis')
    # Exact repeated diagnosis for the same logical attempt conditions provides
    # no changed prerequisite. No automatic blind model/process retry follows.
    for path in (scope.directory/'calls').glob('*/recovery.json'):
        prior = decode(read_regular(path.parent, path.name))
        if prior['task_id'] == task_id and prior.get('finding_binding') == finding_binding:
            raise ValueError('Repeated unchanged diagnosis; preserve and inspect')
    continuation = {'expected_attempt': state['attempts'], 'reason': reason}
    if state['phase'] == 'waiting_review':
        continuation.update(task_sha256=digest(task), candidate=state['results'][-1]['candidate'],
                            review_number=state['review_number'], action=expected)
    record = {'task_id': task_id, 'reason': reason, 'action': expected, 'request': continuation,
              'finding_binding': finding_binding}
    write(scope.directory/'calls'/nonce/'recovery.json', record)
    return record
