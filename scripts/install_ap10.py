"""Create a pinned, user-owned release. No dependency install or implicit activation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess

from runtime.release import ROOT, sha, instruction_guards

LABEL = 'se.nortropic.ap10-runtime'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], timeout=30)


def copy_code(repo, revision, dest):
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Exact integrated revision required')
    git(repo, 'merge-base', '--is-ancestor', revision, 'origin/main')
    files = git(repo, 'ls-tree', '-r', '--name-only', revision).decode().splitlines()
    selected = [n for n in files if n in ('AGENTS.md', 'docs/runtime-v0.1.md') or n.startswith(('runtime/', 'scripts/', 'tools/', 'acceptance/', 'config/'))]
    hashes = {}
    for name in selected:
        mode = git(repo, 'ls-tree', revision, '--', name).decode().split()[0]
        if mode not in ('100644','100755'):
            raise ValueError('Only regular pinned code files supported')
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, 'show', revision + ':' + name)); target.chmod(0o444)
        hashes[name] = sha(target)
    return hashes


def stage(runtime_revision, office_revision, context=None):
    """Stage only; operator separately reviews config and selects/loads it."""
    home = ROOT / '.runtime/ap10'; home.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = home / 'releases' / (runtime_revision + '-' + office_revision)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = {}
    for name, repo, revision in [('runtime', ROOT, runtime_revision),
                                 ('office', ROOT.parent / 'nortropic-projektkontor', office_revision)]:
        files.update({name+'/'+p:h for p,h in copy_code(repo,revision,directory/name).items()})
    if context is not None:
        source=Path(context).absolute()
        office=ROOT.parent/'nortropic-projektkontor'
        if not source.is_relative_to(office/'evidence/ap10/local') or any(p.is_symlink() for p in (source,*source.parents)):
            raise ValueError('Private context must be regular selected AP10 Office evidence')
        selected=list(source.iterdir())
        if not selected or sum(p.stat().st_size for p in selected)>2*1024*1024:
            raise ValueError('Bounded private context required')
        for p in selected:
            if not p.is_file() or p.is_symlink() or p.suffix not in ('.md','.json'):
                raise ValueError('Only selected regular context text')
            target=directory/'context'/p.name;target.parent.mkdir(exist_ok=True,mode=0o700)
            target.write_bytes(p.read_bytes());target.chmod(0o400);files['context/'+p.name]=sha(target)
    config = dict(schema=1, host_root=str(ROOT), office_root=str(ROOT.parent/'nortropic-projektkontor'),
                  database=str(ROOT/'.runtime/runtime.sqlite'), runtime_revision=runtime_revision,
                  office_revision=office_revision, files=files, instruction_guards=instruction_guards())
    path = directory/'config.json';path.write_text(json.dumps(config,indent=2)+'\n');path.chmod(0o400)
    return path


def select(config):
    config = Path(config).resolve()
    value = json.loads(config.read_text())
    if config.parent.parent != ROOT/'.runtime/ap10/releases' or value['host_root'] != str(ROOT):
        raise ValueError('Not a staged named release')
    # An operator must unload/confirm old process cleanup before changing active code.
    from runtime.shared import process_identity
    receipt = ROOT/'.runtime/ap10/service.json'
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if any(process_identity(old[r]['pid']) == old[r]['identity'] for r in ('daemon','engine','worker')):
            raise ValueError('Previous service is still alive; no live code/config replacement')
    active=ROOT/'.runtime/ap10/active.json'
    active.write_text(json.dumps({'config':str(config),'sha256':sha(config)},indent=2)+'\n');active.chmod(0o600)
    from runtime.release import installed
    installed()
    return config


def plist(config):
    config = Path(config)
    result = {'Label':LABEL,'ProgramArguments':[str(ROOT/'.runtime/temporal-venv/bin/python'),'-B','-m','runtime.daemon'],
              'WorkingDirectory':str(config.parent/'runtime'),
              'EnvironmentVariables':{'NR_HOST_ROOT':str(ROOT),'NR_CONFIG_SHA256':sha(config),'PYTHONDONTWRITEBYTECODE':'1',
                                      'PATH':'/opt/homebrew/bin:/usr/bin:/bin'},
              'RunAtLoad':True,'KeepAlive':False,'ProcessType':'Background','Umask':63,
              'StandardOutPath':str(ROOT/'.runtime/ap10/launchd.stdout.log'),
              'StandardErrorPath':str(ROOT/'.runtime/ap10/launchd.stderr.log')}
    # No launchd interval: Temporal is the only scheduler. No restart storm on failure.
    return plistlib.dumps(result)


if __name__ == '__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','select','write-plist'])
    p.add_argument('--runtime');p.add_argument('--office');p.add_argument('--config');p.add_argument('--context');a=p.parse_args()
    if a.action=='stage':print(stage(a.runtime,a.office,a.context))
    elif a.action=='select':print(select(a.config))
    else:
        dest=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist')
        if dest.exists():raise ValueError('Preserve existing installation; do not overwrite')
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(plist(a.config));dest.chmod(0o600);print(dest)
