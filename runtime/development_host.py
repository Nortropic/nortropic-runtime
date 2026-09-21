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
                     and work=='reconciliation' and key in ('interactive-retry-1','interactive-retry-2','interactive-retry-3')
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


def prepare_call(expected, nonce, role, work, context, files, extra=None):
    scope, config = active_scope(expected)
    identifier(nonce)
    active = policy(config)
    stage = scope.directory / 'calls' / nonce
    stage.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = stage / 'workspace'; workspace.mkdir(mode=0o700)
    (workspace / '.scratch').mkdir(mode=0o700)
    files = {**files, 'CONTEXT.json': json.dumps(context, ensure_ascii=False, indent=2).encode(),
             'OUTPUT_SCHEMA.json': json.dumps(active.schema(role)).encode()}
    if extra:
        files.update(extra)
    if sum(len(value) for value in files.values()) > 2*1024*1024:
        raise ValueError('Selected development context exceeds its bound')
    for name, content in files.items():
        if (Path(name).is_absolute() or any(part in ('', '.', '..') for part in name.split('/'))
                or not name.endswith(('.md', '.json', '.py'))):
            raise ValueError('Only explicit selected context text is allowed')
        target = workspace / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
        target.chmod(0o400)
    data = {'prompt': active.instructions(role), 'schema': active.schema(role),
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
    files = {name: read_regular(original, name) for name in binding}
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
    for result in state.get('results', [])[-2:]:
        number = result.get('attempt')
        if type(number) is not int or number < 1:
            continue
        for name in ('result.json', 'acceptance.json'):
            try:
                files['previous-'+str(number)+'-'+name] = read_regular(evidence_directory(task_id), 'attempt-'+str(number)+'/'+name)
            except FileNotFoundError:
                pass
    latest = state.get('results', [])[-1] if state.get('results') else {}
    workspace = task_directory(task_id) / latest.get('workspace_name', 'candidate')
    for name in task['allowed_paths']:
        files[name] = read_regular(workspace, name)
    return prepare_call(expected, nonce, 'diagnosis', bound['work'],
                        {'task': task, 'actual_child_wait': state}, files)


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
    if context != {'task': task, 'actual_child_wait': state}:
        raise ValueError('Diagnosis does not apply to the current observed wait')
    expected = state.get('review_recovery') if state['phase'] == 'waiting_review' else 'retry'
    if answer['action'] != expected:
        raise ValueError('Missing review/host fault must not become a candidate repair')
    # Free model text cannot establish that a quota/access/host prerequisite
    # changed. Those waits need actual host inspection and native recovery.
    # The only automatic model-derived continuation is a bounded candidate
    # repair supported by an actual independently bound code-review rejection.
    if expected != 'repair':
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
    if (latest.get('provider_completed') is not True
            or recovery_kind(task, subject, tests, state.get('review')) != 'repair'):
        return {'hold': True, 'reason': 'No independently bound candidate rejection supports repair'}
    finding_binding = digest({'subject': subject, 'review': state['review']})
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
