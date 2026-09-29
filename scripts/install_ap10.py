"""Create a pinned, user-owned release. No dependency install or implicit activation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import urllib.parse

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


OPERATION_NAME = re.compile('[a-z0-9][a-z0-9-]{0,79}')
# Office's own accepted period range (tools/driftoperation.py). Kept here so staging
# refuses what the handler would refuse; the qualification checks both against the
# handler bytes under test rather than trusting either copy alone.
PERIOD_FLOOR, PERIOD_CEILING = 3600, 2678400


def bind_operations(directory, files, manifest):
    """Bind named operations into the release: input bytes, interval and handler.

    Without this the operation mechanism cannot reach an ordinary release at all,
    only an injected test configuration. The manifest is one reviewed file naming
    each operation; nothing outside it, and no path outside the release, is bound.
    The interval is the wakeup, not the work's period, which lives in the input.
    """
    source = Path(manifest).absolute()
    if any(parent.is_symlink() for parent in (source, *source.parents)) or not source.is_file():
        raise ValueError('Operation manifest must be a regular reviewed file')
    selected = json.loads(source.read_text())
    if not isinstance(selected, dict) or not selected or len(selected) > 8:
        raise ValueError('Bounded named operation manifest required')
    if 'office/tools/driftoperation.py' not in files:
        raise ValueError('Operations require the reviewed Office handler in the release')
    operations = {}
    for name, entry in sorted(selected.items()):
        if not OPERATION_NAME.fullmatch(name) or not isinstance(entry, dict) or set(entry) != {'input', 'interval_seconds'}:
            raise ValueError('Operation entry must name exactly an input and an interval')
        interval = entry['interval_seconds']
        if type(interval) is not int or not 60 <= interval <= 86400:
            raise ValueError('Invalid bounded schedule interval for ' + name)
        given = Path(entry['input'])
        if not given.is_absolute() or any(parent.is_symlink() for parent in (given, *given.parents)):
            raise ValueError('Operation input must be an absolute regular path')
        raw = given.read_bytes()
        if not raw or len(raw) > 65536:
            raise ValueError('Bounded operation input required')
        value = json.loads(raw)
        # The release only ever binds Office's own accepted input schema; no command,
        # interpreter or path is selected here, and every path in it stays absolute.
        if not isinstance(value, dict) or value.get('schema') != 'office-drift/1':
            raise ValueError('Operation input is not an accepted Office operation')
        if not Path(value.get('state', '')).is_absolute():
            raise ValueError('Operation state must be an absolute private directory')
        # Staging must refuse what the handler would refuse at run time. Otherwise a
        # release could be staged, reviewed and activated carrying an operation that
        # can only ever fail, and the refusal would surface as a weekly incident.
        if not any(value.get(channel) for channel in ('intake', 'drift', 'monitor')):
            raise ValueError('Operation binds no intake, drift or monitor channel: ' + name)
        monitor = value.get('monitor') or {}
        if monitor and not isinstance(monitor, dict):
            raise ValueError('Monitor must be an object in ' + name)
        if monitor:
            # The handler accepts plain HTTP only for an isolated loopback probe. A
            # staged release is not one, so refuse it here rather than at the first
            # weekly wakeup - and never bind a probe flag into a release at all.
            if monitor.get('isolated_test') is not None:
                raise ValueError('isolated_test belongs to a probe, not a release: ' + name)
            address = urllib.parse.urlsplit(monitor.get('url') or '')
            if (address.scheme != 'https' or not address.hostname or address.username
                    or address.password or address.fragment):
                raise ValueError('Monitor requires an explicit HTTPS endpoint: ' + name)
            candidate = monitor.get('candidate')
            # str() would launder an integer past this check and leave the handler to
            # raise TypeError at the first wakeup instead.
            if not isinstance(candidate, str) or not re.fullmatch('[0-9a-f]{40}', candidate):
                raise ValueError('Monitor requires an exact candidate: ' + name)
        for channel in ('intake', 'drift'):
            given = value.get(channel)
            if not given:
                continue
            if not isinstance(given, dict):
                raise ValueError('Channel %s must be an object in %s' % (channel, name))
            if given.get('isolated_test') is not None:
                raise ValueError('isolated_test belongs to a probe, not a release: ' + name)
            # The handler needs every one of these to start a frozen tool at all. A
            # release that omits one can only fail, so it never reaches a wakeup.
            required = {'digitala_root', 'digitala_files', 'python_path', 'python_sha256'}
            required |= ({'plan', 'plan_sha256', 'receipts'} if channel == 'drift'
                         else {'base_url', 'key_file', 'customer', 'executor'})
            missing = sorted(key for key in required if not given.get(key))
            if missing:
                raise ValueError('Channel %s lacks %s in %s' % (channel, ', '.join(missing), name))
            # The handler refuses a binding that does not freeze the tool this channel
            # actually starts. Staging must refuse the same, or a release could carry a
            # channel that can only fail at its first wakeup.
            tool = 'verktyg/drift_kontroll.py' if channel == 'drift' else 'verktyg/kundstart.py'
            # NOT `files`: that name is the release's own file table, and shadowing it
            # here silently dropped the operation input's hash out of the release.
            frozen_files = given['digitala_files']
            if not isinstance(frozen_files, dict) or tool not in frozen_files:
                raise ValueError('Channel %s must freeze %s in %s' % (channel, tool, name))
            # Loop names kept distinct from `value` and `relative`, which hold the
            # operation input and the release-relative input path further down. Rebinding
            # either one here silently skipped the period check and dropped the input's
            # hash out of the release; both were caught by the round-trip test.
            for frozen, frozen_hash in sorted(frozen_files.items()):
                inside = Path(frozen)
                if (inside.is_absolute() or '..' in inside.parts
                        or not isinstance(frozen_hash, str)
                        or not re.fullmatch('[0-9a-f]{64}', frozen_hash)):
                    raise ValueError('Unsafe or unhashed frozen file %s in %s' % (frozen, name))
            for key in ('digitala_root', 'python_path') + (
                    ('plan', 'receipts') if channel == 'drift' else ('key_file', 'customer')):
                if not Path(str(given[key])).is_absolute():
                    raise ValueError('%s.%s must be an absolute path in %s' % (channel, key, name))
            # A value that is not 64 hex characters can never equal a SHA256, so the
            # handler would refuse it at the first wakeup. Refuse it while staging.
            for key in ('python_sha256',) + (('plan_sha256',) if channel == 'drift' else ()):
                if not re.fullmatch('[0-9a-f]{64}', str(given[key])):
                    raise ValueError('%s.%s is not a SHA256 in %s' % (channel, key, name))
        if 'period_seconds' in value:
            period = value['period_seconds']
            if type(period) is not int or not PERIOD_FLOOR <= period <= PERIOD_CEILING:
                raise ValueError('Operation period outside its accepted bounds: ' + name)
            if period < interval:
                raise ValueError('A wakeup slower than the period cannot keep it: ' + name)
        relative = 'operations/' + name + '.json'
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or relative in files:
            # A staged release is built once into a fresh directory. Rebinding a name
            # in place would silently replace reviewed bytes, so it is refused.
            raise ValueError('Operation input is already bound in this release: ' + name)
        target.write_bytes(raw); target.chmod(0o444)
        files[relative] = sha(target)
        operations[name] = {'input': relative, 'interval_seconds': interval}
    return operations


def stage(runtime_revision, office_revision, context=None, operations=None):
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
    # Bound before the config is built: the operation inputs must be inside `files`.
    bound = None if operations is None else bind_operations(directory, files, operations)
    config = dict(schema=1, host_root=str(ROOT), office_root=str(ROOT.parent/'nortropic-projektkontor'),
                  database=str(ROOT/'.runtime/runtime.sqlite'), runtime_revision=runtime_revision,
                  office_revision=office_revision, files=files, instruction_guards=instruction_guards())
    if bound is not None:
        config['scheduled_operations'] = bound
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
    if json.loads(config.read_text()).get('development', {}).get('id') == 'office-ap11':
        # The same existing host gh identity already used by Publisher.api.
        # Avoid an interactive Keychain Git helper in the unattended profile.
        # No token is copied; candidate/model environments filter these values.
        result['EnvironmentVariables'].update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='2',
            GIT_CONFIG_KEY_0='credential.helper', GIT_CONFIG_VALUE_0='',
            GIT_CONFIG_KEY_1='credential.helper', GIT_CONFIG_VALUE_1='!gh auth git-credential')
    # No launchd interval: Temporal is the only scheduler. No restart storm on failure.
    return plistlib.dumps(result)


if __name__ == '__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','select','write-plist'])
    p.add_argument('--runtime');p.add_argument('--office');p.add_argument('--config');p.add_argument('--context')
    p.add_argument('--operations');a=p.parse_args()
    if a.action=='stage':print(stage(a.runtime,a.office,a.context,a.operations))
    elif a.action=='select':print(select(a.config))
    else:
        dest=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist')
        if dest.exists():raise ValueError('Preserve existing installation; do not overwrite')
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(plist(a.config));dest.chmod(0o600);print(dest)
