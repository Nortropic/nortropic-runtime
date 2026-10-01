"""Frozen host entry to the separately adopted issuer; no candidate imports.

The existing holder installs these reviewed bytes as check-issuer/launch.py and
seals launcher-adoption.json. Neither source checkout nor this program can adopt
itself. The issuer's existing authority, acceptance and server gates stay intact.
"""
import argparse
import hashlib
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

CODE = ('runtime/__init__.py', 'runtime/check_issuer.py', 'runtime/integration.py',
        'runtime/host_publication.py', 'runtime/decision_guard.py', 'runtime/content_guard.py', 'runtime/failure_ledger.py',
        'runtime/profile.py', 'runtime/release.py', 'runtime/targets.py',
        'runtime/construction_registration.py', 'runtime/development_binding.py',
        'runtime/development_scope.py', 'runtime/snapshot.py',
        'runtime/claude_profile.py', 'runtime/codex_pin.py',
        'scripts/probe_bridge.py', 'scripts/publish_construction.py',
        'scripts/publish_digitala.py', 'scripts/bounded.py', 'scripts/matning_provanvandare.py',
        'runtime/measurement_observer.py', 'scripts/measurement_queue.py')


def acl(path, *, private=False):
    """Standalone stdlib-only bootstrap: never import an unqualified helper."""
    result=subprocess.run(['/bin/ls','-lde',str(path)],capture_output=True,
                          env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=10)
    if result.returncode:raise ValueError('Host ACL observation unavailable')
    for line in result.stdout.decode('utf-8','strict').splitlines()[1:]:
        match=re.fullmatch(r'\s*\d+: (user|group):([^ ]+) (?:inherited )?(allow|deny) ([a-z_,]+)',line)
        if not match:raise ValueError('Unknown host ACL')
        kind,principal,effect,rights=match.groups()
        if effect=='deny':continue
        try:
            test=pwd.getpwnam('_nortropicprov')
            groups=set(os.getgrouplist(test.pw_name,test.pw_gid))|{test.pw_gid}
            if kind=='user':
                uid=pwd.getpwnam(principal).pw_uid;applies=uid==test.pw_uid
                if uid in (0,os.getuid()) and not applies:continue
            else:applies=principal=='everyone' or grp.getgrnam(principal).gr_gid in groups
        except (KeyError,OSError):raise ValueError('Unresolved host ACL principal') from None
        readonly={'read','list','search','execute','readattr','readextattr','readsecurity',
                  'file_inherit','directory_inherit','only_inherit','limit_inherit'}
        if private or applies or not set(rights.split(','))<=readonly:raise ValueError('Unsafe host ACL')


def private(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe host path')
    for parent in path.parents:
        info=parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid())
                or info.st_mode&0o022 and not (info.st_uid==0 and info.st_mode&stat.S_ISVTX)):
            raise ValueError('Unsafe host ancestor')
        acl(parent)
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode) not in (0o400,0o600)):
        raise ValueError('Host file is not private')
    acl(path,private=True)
    identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        if identity(os.fstat(fd))!=identity(info):raise ValueError('Host identity changed before read')
        raw=stream.read()
        if identity(os.fstat(fd))!=identity(info) or identity(path.lstat())!=identity(info):
            raise ValueError('Host identity changed during read')
    return raw


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qualified_root(entry):
    entry = Path(entry).absolute()
    home = entry.parent
    host = home.parents[2]
    if entry != host / '.runtime/ap11/check-issuer/launch.py':
        raise ValueError('Only the installed host launcher can run')
    adoption = json.loads(private(home / 'launcher-adoption.json'))
    authority_raw = private(home / 'authority.json')
    if (adoption.get('schema') != 'nortropic-launcher-adoption/1'
            or adoption.get('launcher_sha256') != sha(private(entry))
            or adoption.get('issuer_authority_sha256') != sha(authority_raw)
            or adoption.get('verdict') != 'approved' or adoption.get('blocking_findings') != []
            or not adoption.get('reviewer_run') or not adoption.get('implementation_run')
            or adoption['reviewer_run'] == adoption['implementation_run']):
        raise ValueError('Launcher has not been separately adopted')
    authority = json.loads(authority_raw)
    root = Path(authority['adopted_code_root'])
    if (root.parent != home / 'adopted' or not re.fullmatch('[0-9a-f]{40}', root.name)
            or authority.get('schema') != 'nortropic-issuer-authority/1'
            or any(type(authority.get(k)) is not int or authority[k] <= 0
                   for k in ('app_id', 'installation_id'))
            or authority.get('code_sha256') != {p: sha(private(root / p)) for p in CODE}
            or (root / 'scripts/__init__.py').exists()
            or any(root.rglob('*.pyc'))):
        raise ValueError('Frozen issuer bytes differ')
    review_raw = private(home / 'adoption-review.json')
    review = json.loads(review_raw)
    if (sha(review_raw) != authority.get('adoption_review_sha256')
            or review.get('code_sha256') != authority['code_sha256']
            or review.get('verdict') != 'approved' or review.get('blocking_findings') != []
            or not review.get('reviewer_run') or not review.get('implementation_run')
            or review['reviewer_run'] == review['implementation_run']):
        raise ValueError('Issuer lacks its independent adoption')
    return host, root


def execute(arguments):
    # Parse a closed interface before opening any request or importing the issuer.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('digitala', 'issue'))
    parser.add_argument('--task', required=True)
    parser.add_argument('--candidate')
    parser.add_argument('--binding')
    args = parser.parse_args(arguments)
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', args.task):
        raise ValueError('Invalid task identifier')
    if args.operation == 'digitala':
        if args.candidate is not None or args.binding is not None:
            raise ValueError('Digitala accepts only a sealed task identifier')
    elif (not re.fullmatch('[0-9a-f]{40}', args.candidate or '')
          or not re.fullmatch('nortropic-check/1:[0-9a-f]{64}', args.binding or '')):
        raise ValueError('Issue requires an exact caller expectation')
    host, root = qualified_root(__file__)
    account = pwd.getpwuid(os.getuid())
    os.environ.clear()
    os.environ.update(PATH='/opt/homebrew/bin:/usr/bin:/bin', HOME=account.pw_dir,
                      USER=account.pw_name, LOGNAME=account.pw_name,
                      LANG='C', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1', NR_HOST_ROOT=str(host))
    os.chdir(host)
    sys.path.insert(0, str(root))
    # No runtime package was loaded in this isolated process before the complete fixed closure
    # were checked against private authority. The old adopted issuer rechecks too.
    from runtime.check_issuer import HostIssuer, DigitalaPublisher, read_object, binding
    issuer = HostIssuer(host)
    issuer.authority()
    if args.operation == 'digitala':
        return DigitalaPublisher(issuer).publish_sealed(args.task)
    record = read_object(issuer.home / 'requests' / args.task / 'request.json')
    task, subject, review = (record[key] for key in ('task', 'subject', 'review'))
    targets = {'Nortropic/nortropic-runtime': host,
               'Nortropic/nortropic-projektkontor': host.parent / 'nortropic-projektkontor'}
    if task.get('target') not in targets:
        raise ValueError('Issue serves only the ordinary Runtime/Office publisher')
    issuer.request(args.task, task, subject, review)
    if subject['candidate'] != args.candidate or binding(task, subject, review) != args.binding:
        raise ValueError('Caller differs from sealed task')
    return issuer.issue(targets[task['target']], task, subject, review)


def main(arguments=None):
    try:
        receipt = execute(sys.argv[1:] if arguments is None else arguments)
    except Exception:
        # Request data, local paths, transport bodies and credentials stay private.
        print(json.dumps({'published': False, 'reason': 'Host publication refused'}))
        return 2
    print(json.dumps(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
