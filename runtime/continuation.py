"""Host-only preparation of an explicit access/base continuation; never reset history."""
import fcntl
import hashlib
import json
import subprocess
from .candidate import git
from .integration import digest, Publisher
from .profile import ROOT
from .revision import require_revision
from .snapshot import read_regular
from .task import task_directory, evidence_directory, load


def prepare(task, acceptance, brief, source_revision, native_state):
    state=task_directory(task['id']);receipt_path=state/'continuation.json'
    if native_state['phase']!='waiting_access' or native_state['attempts']!=task['continuation']['expected_attempt']:
        raise ValueError('Native workflow is not at the accepted access checkpoint')
    original=json.loads(receipt_path.read_text())['original_task'] if receipt_path.exists() else load(task['id'])
    index=next(i for i,s in enumerate(original['steps']) if s.get('waiting_reason'))
    require_revision(original,task,index,native_state['attempts'])
    Publisher(ROOT).require_base(task['base'])
    with (state/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if receipt_path.exists():
            prior=json.loads(receipt_path.read_text())
            if prior['task_sha256']!=digest(task) or load(task['id'])!=task:
                raise ValueError('Partial/different continuation; inspect preserved files before any retry')
            for name,expected in prior['preserved_files_sha256'].items():
                if hashlib.sha256(read_regular(state/'candidate',name)).hexdigest()!=expected:
                    raise ValueError('Prepared candidate changed before access signal')
            return prior
        workspace=state/'candidate'
        files={name:read_regular(workspace,name) for name in task['allowed_paths']}
        hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        # A complete prior phase snapshot is the expected inherited work. Never
        # silently discard later edits when reconstructing against a current base.
        previous=evidence_directory(task['id'])/('attempt-'+str(native_state['attempts']))/'candidate'
        for name,data in files.items():
            if read_regular(previous,name)!=data:raise ValueError('Inherited source differs from last preserved phase')
        staged=state/'candidate-continuation';old=state/'candidate-before-continuation'
        if staged.exists() or old.exists() or (state/'accepted.json').exists():
            raise ValueError('Partial continuation exists; inspect and reconcile, never overwrite')
        subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(ROOT),str(staged)],check=True,capture_output=True,timeout=30)
        git(staged,'checkout','--detach',task['base']);git(staged,'remote','remove','origin')
        (staged/'tools').mkdir(exist_ok=True);(staged/'.scratch').mkdir(exist_ok=True)
        for name,data in files.items():
            target=staged/name
            if target.is_symlink() or target.parent.is_symlink():raise ValueError('Unsafe accepted base source')
            target.write_bytes(data)
        handoff=('\n\nRuntime continuity (host-owned): same task '+task['id']+
                 ', attempts already recorded: '+str(native_state['attempts'])+'.\n'
                 'Attempt1 was interrupted; attempt2 completed the Codex phase. The three allowed files\n'
                 'are byte-identical to its preserved snapshot. Read tools/README.md before continuing.\n'
                 'Runtime owns process checks, testing, review and publication. Do not start operator\n'
                 'commands or other writers. Claude has Read/Edit/Write only; external host tests run\n'
                 'after it exits. Final Codex then verifies both provider paths in these same files.\n'
                 'The host updated the old base to '+task['base']+' without resetting history.\n')
        (staged/'TASK.md').write_text(brief.decode()+handoff)
        receipt={'original_task':original,'task':task,'task_sha256':digest(task),'runtime_source':source_revision,
                 'native_checkpoint':native_state,'preserved_files_sha256':hashes,
                 'previous_candidate_base':git(workspace,'rev-parse','HEAD'),'new_base':task['base'],
                 'brief_sha256':hashlib.sha256(brief).hexdigest(),'acceptance_sha256':hashlib.sha256(acceptance).hexdigest()}
        output=evidence_directory(task['id'])/'continuation';output.mkdir(exist_ok=False)
        (output/'prepared.json').write_text(json.dumps(receipt,indent=2)+'\n')
        (output/'TASK.md').write_bytes((staged/'TASK.md').read_bytes())
        # Preserve original directory and every old attempt. An interrupted host
        # mutation stops for diagnosis; no automatic repair or model invocation.
        workspace.rename(old);staged.rename(workspace)
        (state/'acceptance.py').write_bytes(acceptance);(state/'brief.md').write_bytes(brief)
        (state/'accepted.json').write_text(json.dumps(task,indent=2)+'\n')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        return receipt
