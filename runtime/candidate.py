"""Freeze allowed source as an actual Git object before tests and review."""
import hashlib
import json
from pathlib import Path
import subprocess

from .profile import ROOT
from .snapshot import read_regular
from .task import task_directory
from .targets import repository, origin


def git(repository, *args, raw=False):
    result = subprocess.run(['git', '-C', str(repository), *args], capture_output=True, check=True, timeout=30)
    return result.stdout if raw else result.stdout.decode().rstrip('\n')


def prepare(task, attempt, source):
    source = Path(source)
    changed = git(source, 'diff', '--no-renames', '--name-only', '-z', task['base']).split('\0')
    untracked = git(source, 'ls-files', '--others', '-z').split('\0')
    observed = {p for p in changed + untracked if p and p != 'TASK.md' and not p.startswith('.scratch/')}
    if not observed or not observed.issubset(set(task['allowed_paths'])):
        raise ValueError('Candidate changed unaccepted source paths: ' + repr(sorted(observed)))
    blobs = {name: read_regular(source, name) for name in task['allowed_paths']}
    workspace = task_directory(task['id']) / ('commit-' + str(attempt))
    if workspace.exists(): raise ValueError('Preserve previous candidate; reconcile instead of overwriting')
    subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(repository(task['target'])), str(workspace)],
                   check=True, capture_output=True, timeout=30)
    git(workspace, 'checkout', '--detach', task['base'])
    git(workspace, 'remote', 'set-url', 'origin', origin(task['target']))
    for name, content in blobs.items():
        target = workspace / name
        # Base is a trusted exact Git object; refuse a symlink component regardless.
        parent = workspace
        for part in Path(name).parts[:-1]:
            parent = parent / part
            if parent.is_symlink(): raise ValueError('Base directory is a symlink')
            parent.mkdir(exist_ok=True)
        if target.is_symlink(): raise ValueError('Base source is a symlink')
        target.write_bytes(content)
    git(workspace, 'add', '--', *task['allowed_paths'])
    git(workspace, 'commit', '-qm', 'Runtime candidate: ' + task['id'])
    candidate = git(workspace, 'rev-parse', 'HEAD')
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in blobs.items()}
    for name, expected in hashes.items():
        if hashlib.sha256(git(workspace, 'show', candidate + ':' + name, raw=True)).hexdigest() != expected:
            raise ValueError('Git candidate bytes differ from frozen source')
    (workspace / '.scratch').mkdir(exist_ok=True)
    return {'candidate': candidate, 'workspace_name': workspace.name, 'candidate_files_sha256': hashes}
