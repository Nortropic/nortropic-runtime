"""Submit one frozen accepted task and observe a bounded native workflow run.

No production daemon, hidden retry loop or paid API fallback. Existing state is
never overwritten. A waiting result is not approval; inspect before resumption.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

from google.protobuf.json_format import MessageToDict
from temporalio.common import WorkflowIDReusePolicy

from .candidate import git
from .integration import digest
from .profile import ROOT
from .service import LocalService
from .snapshot import read_regular
from .task import validate, task_directory, evidence_directory, load
from .workflow import DevelopmentTask
from .targets import repository, origin, TARGETS, OFFICE
from scripts.bounded import stop_group


def check_unfinished_writers():
    # Completed cleanup evidence belongs to the old process identity; do not kill
    # a later unrelated process merely because the OS recycled its PID.
    for pattern in ('evidence/accepted-task/attempt-*/launch.json', 'evidence/runs/*/*/launch.json'):
        for path in ROOT.glob(pattern):
            result_path = path.with_name('result.json')
            if result_path.exists() and json.loads(result_path.read_text()).get('process_group_removed') is True:
                continue
            launch = json.loads(path.read_text())
            for key in ('executor_pid', 'provider_pid'):
                if key not in launch: continue
                try: os.kill(launch[key], 0)
                except ProcessLookupError: pass
                else: raise RuntimeError('Unfinished recorded writer; inspect before starting: ' + str(path))
            if launch.get('provider_pid'):
                try: os.killpg(launch['provider_pid'], 0)
                except ProcessLookupError: pass
                else: raise RuntimeError('Unfinished provider group; inspect before starting: ' + str(path))


def read_input(task_file):
    task_file = Path(task_file).resolve()
    input_root = task_file.parent.parent
    if task_file.parent.name != 'tasks' or input_root not in [repository(t).resolve() for t in TARGETS]:
        raise ValueError('Select a committed accepted task in an authorized project tasks/')
    relative = str(task_file.relative_to(input_root))
    source_revision = git(ROOT, 'rev-parse', 'HEAD')
    input_revision = git(input_root, 'rev-parse', 'HEAD')
    for root in {ROOT, input_root}:
        if git(root, 'diff', '--name-only') or git(root, 'diff', '--cached', '--name-only'):
            raise ValueError('Commit reviewed host source and inputs before invoking models')
    task_bytes = read_regular(input_root, relative)
    if task_bytes != git(input_root, 'show', input_revision + ':' + relative, raw=True):
        raise ValueError('Accepted task differs from preserved Git object')
    task = validate(json.loads(task_bytes))
    if repository(task['target']).resolve() != input_root:
        raise ValueError('Accepted target differs from input repository')
    if git(input_root, 'remote', 'get-url', 'origin') != origin(task['target']):
        raise ValueError('Unauthorized input origin')
    if task['target'] == OFFICE and task['runtime_revision'] != source_revision:
        raise ValueError('Runtime revision differs from accepted office task')
    acceptance_path = task['acceptance']
    brief_path = task['brief']
    if not acceptance_path.startswith('acceptance/') or not brief_path.startswith('tasks/'):
        raise ValueError('Host verifier and brief must be selected from this project')
    acceptance = read_regular(input_root, acceptance_path)
    brief = read_regular(input_root, brief_path)
    for name, content in ((acceptance_path, acceptance), (brief_path, brief)):
        if content != git(input_root, 'show', input_revision + ':' + name, raw=True):
            raise ValueError('Accepted brief/verifier differs from preserved Git object')
    if hashlib.sha256(acceptance).hexdigest() != task['acceptance_sha256']:
        raise ValueError('Acceptance file changed after acceptance')
    return task, acceptance, brief, source_revision


def prepare(task_file):
    task, acceptance, brief, source_revision = read_input(task_file)
    task_bytes = json.dumps(task, indent=2).encode()
    state, output = task_directory(task['id']), evidence_directory(task['id'])
    if state.exists() or output.exists(): raise ValueError('Task already exists; inspect native state instead of overwriting or resubmitting')
    check_unfinished_writers()
    state.mkdir(parents=True); output.mkdir(parents=True)
    (state / 'accepted.json').write_bytes(task_bytes)
    (state / 'acceptance.py').write_bytes(acceptance)
    (state / 'brief.md').write_bytes(brief)
    workspace = state / 'candidate'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(repository(task['target'])),str(workspace)],
                   check=True,capture_output=True,timeout=30)
    git(workspace,'checkout','--detach',task['base'])
    git(workspace,'remote','remove','origin')
    (workspace/'tools').mkdir(exist_ok=True); (workspace/'.scratch').mkdir(exist_ok=True)
    # Exact-file Codex grants need existing regular files. No candidate can write
    # the host's active entry, task inputs or verifier.
    if task['target'] == OFFICE:
        for name in task['allowed_paths']:
            path = workspace / name
            parent = workspace
            for part in Path(name).parts[:-1]:
                parent = parent / part
                if parent.is_symlink(): raise ValueError('Unsafe allowed parent')
                parent.mkdir(exist_ok=True)
            if path.is_symlink(): raise ValueError('Unsafe allowed file')
            if not path.exists(): path.touch()
            read_regular(workspace, name)
    (workspace/'TASK.md').write_bytes(brief)
    manifest = {'task':task,'task_sha256':digest(task),'runtime_source':source_revision,
                'input_source':git(repository(task['target']), 'rev-parse', 'HEAD'),
                'brief_sha256':hashlib.sha256(brief).hexdigest(), 'acceptance_sha256':task['acceptance_sha256']}
    (output/'accepted.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return task, output


async def main(task_file, resume=False, diagnosis=None, reconcile=None, access_restored=False, review_repair=None, review_retry=None):
    if resume:
        selected = json.loads(Path(task_file).read_text())
        if access_restored:
            task, acceptance, brief, source_revision = read_input(task_file)
        else:
            task = load(selected['id'], digest(selected))
        check_unfinished_writers()
        output = evidence_directory(task['id']) / 'observations' / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
    else:
        if diagnosis or reconcile or access_restored or review_repair or review_retry: raise ValueError('Signals require --resume of an existing task')
        task, output = prepare(task_file)
    if task['target'] == OFFICE:
        if git(ROOT, 'rev-parse', 'HEAD') != task['runtime_revision'] or git(ROOT, 'diff', 'HEAD', '--name-only'):
            raise ValueError('Resume requires the unchanged accepted Runtime revision')
    worker = None
    # Existing report workflow is retained when establishing the central DB.
    old_database = ROOT/'.runtime/tasks/runtime-run-report-1/temporal.sqlite'
    seed = old_database if old_database.exists() else None
    service = LocalService(ROOT/'.runtime/runtime.sqlite',output/'service',seed_database=seed)
    async with service as client:
        with (output/'worker.log').open('wb') as log:
            worker = subprocess.Popen([sys.executable,'-m','runtime.worker'],cwd=ROOT,
                                      stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            (output/'worker.json').write_text(json.dumps({'pid':worker.pid})+'\n')
            try:
                # Verify the old waiting workflow before allowing a new task to run.
                if service.migrated:
                    old = await asyncio.wait_for(client.get_workflow_handle('runtime-run-report-1').query(DevelopmentTask.state),15)
                    expected=json.loads((ROOT/'evidence/accepted-task/engine-resume-2/state.json').read_text())
                    if old != expected: raise ValueError('Existing report workflow state changed unexpectedly')
                    (output/'preserved-report-state.json').write_text(json.dumps(old,indent=2)+'\n')
                required_attempt = required_publication = required_reviews = 0
                if resume:
                    handle = client.get_workflow_handle(task['id'])
                    prior = await asyncio.wait_for(handle.query(DevelopmentTask.state),15)
                    if access_restored:
                        from .continuation import prepare as prepare_continuation
                        receipt = prepare_continuation(task, acceptance, brief, source_revision, prior)
                        (output/'continuation.json').write_text(json.dumps(receipt,indent=2)+'\n')
                        required_attempt = prior['attempts'] + 1
                        await handle.signal(DevelopmentTask.resume_after_access, task)
                    if diagnosis:
                        if prior['phase'] != 'waiting_diagnosis': raise ValueError('Task is not waiting for implementation diagnosis')
                        required_attempt = prior['attempts'] + 1
                        await handle.signal(DevelopmentTask.retry_after_diagnosis,
                                            {'expected_attempt':prior['attempts'],'reason':diagnosis})
                    if reconcile:
                        if prior['phase'] != 'waiting_publication_reconciliation': raise ValueError('Task is not waiting for publication reconciliation')
                        required_publication = prior.get('publication_attempts',1) + 1
                        await handle.signal(DevelopmentTask.reconcile_publication,
                                            {'candidate':prior['results'][-1]['candidate'],'reason':reconcile})
                    if review_repair or review_retry:
                        action = 'repair' if review_repair else 'review_only'
                        if prior['phase'] != 'waiting_review' or prior.get('review_recovery') != action:
                            raise ValueError('Selected review continuation does not match diagnosed wait')
                        number = prior['review_number']
                        required_reviews = number + 1
                        if action == 'repair': required_attempt = prior['attempts'] + 1
                        await handle.signal(DevelopmentTask.continue_after_review,
                            {'task_sha256': digest(task), 'candidate': prior['results'][-1]['candidate'],
                             'review_number': number, 'expected_attempt': prior['attempts'],
                             'action': action, 'reason': review_repair or review_retry})
                    (output/'resume.json').write_text(json.dumps({'prior':prior,'diagnosis':diagnosis,'reconcile':reconcile,'access_restored':access_restored,'review_repair':review_repair,'review_retry':review_retry},indent=2)+'\n')
                else:
                    handle=await client.start_workflow(DevelopmentTask.run,task,id=task['id'],task_queue='development',
                                                       id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
                end=asyncio.get_running_loop().time()+task['attempt_seconds']*len(task['steps'])+420
                while asyncio.get_running_loop().time()<end:
                    status=await asyncio.wait_for(handle.query(DevelopmentTask.state),10)
                    snapshot = output/'state.json.tmp'
                    snapshot.write_text(json.dumps(status,indent=2)+'\n')
                    snapshot.replace(output/'state.json')
                    if ((status['phase']=='completed' or status['phase'].startswith('waiting_'))
                            and status['attempts'] >= required_attempt
                            and status.get('publication_attempts',0) >= required_publication
                            and (len(status.get('reviews', [])) >= required_reviews
                                 or status['phase'] == 'waiting_diagnosis')):break
                    if worker.poll() is not None:raise RuntimeError('Worker exited; inspect preserved state')
                    await asyncio.sleep(.5)
                else:raise TimeoutError('Bounded observation ended; inspect existing workflow before retry')
                history=await handle.fetch_history()
                (output/'history.json').write_text(json.dumps([MessageToDict(x) for x in history.events],indent=2)+'\n')
                print(json.dumps({'task':task['id'],'phase':status['phase'],'attempts':status['attempts'],
                                  'integration':status.get('integration'),'evidence':str(output.relative_to(ROOT))}))
                return 0 if status['phase']=='completed' else 1
            finally:
                removed=stop_group(worker)
                (output/'worker-cleanup.json').write_text(json.dumps({'process_group_removed':removed})+'\n')
                if not removed:raise RuntimeError('Worker group remains; inspect before restart')


async def bounded(task_file, **options):
    task=asyncio.create_task(main(task_file, **options));loop=asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM,task.cancel)
    try:return await asyncio.wait_for(task,4200)
    finally:loop.remove_signal_handler(signal.SIGTERM)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('accepted_task')
    parser.add_argument('--resume', action='store_true')
    signals = parser.add_mutually_exclusive_group()
    signals.add_argument('--diagnosis', help='Materially changed prerequisite after an implementation diagnosis')
    signals.add_argument('--reconcile', help='Reason to inspect/reconcile a failed or ambiguous publication')
    signals.add_argument('--access-restored', action='store_true', help='Resume a reviewed frozen continuation at its native access checkpoint')
    signals.add_argument('--review-repair', help='Diagnosed concrete rejection: repair same task, test and review again')
    signals.add_argument('--review-retry', help='Changed prerequisite for missing/invalid review; keep candidate unchanged')
    args=parser.parse_args()
    raise SystemExit(asyncio.run(bounded(args.accepted_task,resume=args.resume,diagnosis=args.diagnosis,reconcile=args.reconcile,access_restored=args.access_restored,review_repair=args.review_repair,review_retry=args.review_retry)))
