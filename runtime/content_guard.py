"""Model-free, host-owned publication content checks (OVL-20260930-1225ac I1).

Scan complete Git blobs, not patch lines. Never return matched values. Exceptions
are host policy, exact path plus exact SHA-256, and never supplied by a task.
This is a bounded pattern check, not proof that arbitrary private data is absent.
"""
import hashlib
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess


class ContentRefused(ValueError):
    pass


TARGETS = ('Nortropic/nortropic-runtime', 'Nortropic/nortropic-projektkontor',
           'Nortropic/nortropic-digitala', 'Nortropic/nortropic-kundstart')

MAX_BLOB = 64 * 1024 * 1024
KEY = b'PRIVATE' + b' KEY'
PATTERNS = {
    'private-key': re.compile(b'-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED |PGP )?' + KEY + b'(?: BLOCK)?-----|PuTTY-User-Key-File-[23]:'),
    'github-token': re.compile(rb'(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'anthropic-token': re.compile(rb'(?<![A-Za-z0-9_])sk-ant-[A-Za-z0-9_-]{20,}'),
    'openai-token': re.compile(rb'(?<![A-Za-z0-9_])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}'),
    'slack-token': re.compile(rb'(?<![A-Za-z0-9_])xox[baprs]-[A-Za-z0-9-]{20,}'),
    'aws-key': re.compile(rb'(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])'),
    'vercel-token': re.compile(rb'(?<![A-Za-z0-9_])vc[piark]_[A-Za-z0-9_-]{20,}'),
    'home-path': re.compile(rb'/(?:Users|home)/[^/\s"\x27<>]+(?:/|(?=[\s"\x27]))'),
}
STREAM = re.compile(rb'"(?:type|subtype)"\s*:\s*"(?:assistant|user|system|result|error|tool_result|tool_use|stream_event|response_item|session_meta|event_msg|task_complete|turn_failed|agent_message|command_execution|item\.(?:started|updated|completed)|thread\.started|turn\.(?:started|completed|failed))"')
# F-107/P1: actual invisible Unicode, not the printable escape notation used in
# source and fixtures. Invalid UTF-8 elsewhere must not hide a valid occurrence.
INVISIBLE = re.compile('[\u061c\u115f\u1160\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\u3164\ufe00-\ufe0f\ufeff\U000e0000-\U000e007f\U000e0100-\U000e01ef]')


def _acl(path,private=False):
    """Deny test-account ACL access and untrusted mutation, also on ancestors.

    Kept self-contained: the adopted scanner is loaded by absolute file path
    outside a Python package and must never import a candidate-selected module.
    """
    try:
        result=subprocess.run(['/bin/ls','-lde',str(path)],capture_output=True,
                              env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=10)
        if result.returncode:raise ContentRefused('Content policy ACL observation unavailable')
        for line in result.stdout.decode('utf-8','strict').splitlines()[1:]:
            match=re.fullmatch(r'\s*\d+: (user|group):([^ ]+) (?:inherited )?(allow|deny) ([a-z_,]+)',line)
            if not match:raise ContentRefused('Unknown content policy ACL representation')
            kind,principal,effect,rights=match.groups()
            if effect=='deny':continue
            test=pwd.getpwnam('_nortropicprov')
            groups=set(os.getgrouplist(test.pw_name,test.pw_gid))|{test.pw_gid}
            if kind=='user':
                uid=pwd.getpwnam(principal).pw_uid;applies=uid==test.pw_uid
                if uid in (0,os.getuid()) and not applies:continue
            else:applies=principal=='everyone' or grp.getgrnam(principal).gr_gid in groups
            readonly={'read','list','search','execute','readattr','readextattr','readsecurity',
                      'file_inherit','directory_inherit','only_inherit','limit_inherit'}
            if private or applies or not set(rights.split(','))<=readonly:
                raise ContentRefused('Content policy ACL permits test access or untrusted mutation')
    except (OSError,UnicodeError,KeyError,subprocess.TimeoutExpired):
        raise ContentRefused('Content policy ACL observation unavailable') from None


def _parents(path,allow_missing=False):
    for parent in path.parents:
        try:info=parent.lstat()
        except FileNotFoundError:
            if allow_missing:continue
            raise ContentRefused('Content policy ancestor is absent') from None
        except OSError:raise ContentRefused('Content policy ancestor is unreadable') from None
        sticky_root=info.st_uid==0 and bool(info.st_mode&stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid())
                or info.st_mode&0o022 and not sticky_root):
            raise ContentRefused('Unsafe content policy ancestor')
        _acl(parent)


def _private(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ContentRefused('Content policy contains a linked file')
    _parents(path)
    _acl(path,private=True)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            s = os.fstat(f.fileno())
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
                raise ContentRefused('Content policy must be an owner-private regular file')
            raw = f.read(1024 * 1024 + 1)
            current=path.lstat()
            if (current.st_dev,current.st_ino)!=(s.st_dev,s.st_ino):
                raise ContentRefused('Content policy changed during read')
    except OSError:
        raise ContentRefused('Configured content policy cannot be read') from None
    if len(raw) > 1024 * 1024:
        raise ContentRefused('Content policy exceeds size limit')
    if any((p / '.git').exists() for p in path.parents):
        raise ContentRefused('Content policy must be outside all repositories')
    return raw


def load_policy(path=None):
    """A fixed OS-account path, never HOME, environment or candidate configuration."""
    default = Path(pwd.getpwuid(os.getuid()).pw_dir) / 'Library/Application Support/Nortropic/content-guard.json'
    if path is None:
        try:default.lstat()
        except FileNotFoundError:
            _parents(default,allow_missing=True)
            return {'literals': [], 'exceptions': {}, 'literal_status': 'litterallista ej konfigurerad'}
        except OSError:raise ContentRefused('Content policy presence is unknown') from None
    try:
        d = json.loads(_private(default if path is None else path))
        if not isinstance(d, dict) or d.get('schema') != 1 or set(d) - {'schema', 'literal_file', 'exceptions', 'deletions'}:
            raise ValueError
        literals = []
        if 'literal_file' in d:
            if not isinstance(d['literal_file'], str) or not Path(d['literal_file']).is_absolute():
                raise ValueError
            lines = _private(d['literal_file']).decode('utf-8').splitlines()
            if not lines or any(not x.strip() or '\0' in x for x in lines):
                raise ValueError
            literals = [x.encode('utf-8') for x in lines]
        exceptions = {}
        rows = d.get('exceptions', [])
        if not isinstance(rows, list):
            raise ValueError
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'target', 'path', 'sha256', 'reason'}
                    or row['target'] not in TARGETS
                    or not isinstance(row['path'], str) or not row['path']
                    or row['path'].startswith('/') or any(x in ('', '.', '..') for x in row['path'].split('/'))
                    or not re.fullmatch('[0-9a-f]{64}', str(row['sha256']))
                    or not isinstance(row['reason'], str) or not row['reason'].strip()
                    or (row['target'], row['path']) in exceptions):
                raise ValueError
            exceptions[row['target'], row['path']] = {'sha256': row['sha256'], 'reason_sha256': hashlib.sha256(row['reason'].encode()).hexdigest()}
        deletions={}
        if not isinstance(d.get('deletions',[]),list):raise ValueError
        for row in d.get('deletions',[]):
            if (not isinstance(row,dict) or set(row)!={'target','path','base','sha256','reason'}
                or row['target'] not in ('Nortropic/nortropic-runtime','Nortropic/nortropic-projektkontor','Nortropic/nortropic-digitala','Nortropic/nortropic-kundstart')
                or not isinstance(row['path'],str) or row['path'].startswith('/')
                or any(x in ('','.','..') for x in row['path'].split('/'))
                or not re.fullmatch('[0-9a-f]{40}',str(row['base']))
                or not re.fullmatch('[0-9a-f]{64}',str(row['sha256']))
                or not isinstance(row['reason'],str) or not row['reason'].strip()):raise ValueError
            key=(row['target'],row['base'],row['path'])
            if key in deletions:raise ValueError
            deletions[key]={'sha256':row['sha256'],'reason_sha256':hashlib.sha256(row['reason'].encode()).hexdigest()}
    except ContentRefused:
        raise
    except (ValueError, UnicodeError, TypeError, KeyError):
        raise ContentRefused('Configured content policy is invalid or empty') from None
    return {'literals': literals, 'exceptions': exceptions, 'deletions':deletions,
            'literal_status': 'litterallista konfigurerad' if 'literal_file' in d else 'litterallista ej konfigurerad'}


def safe_path(path, literals=()):
    raw = path.encode('utf-8', errors='surrogateescape')
    if INVISIBLE.search(path) or any(x.search(raw) for x in PATTERNS.values()) or any(x in raw for x in literals):
        return '[redacted-path sha256=' + hashlib.sha256(raw).hexdigest() + ']'
    return path


def scan_blob(path, raw, policy, target=None):
    if target is not None and target not in TARGETS:
        raise ContentRefused("Unknown content target")
    if not isinstance(raw, bytes) or len(raw) > MAX_BLOB:
        raise ContentRefused('Content blob unavailable or exceeds size limit')
    found = set()
    decoded = raw.decode('utf-8', errors='replace')
    for match in INVISIBLE.finditer(decoded):
        found.add((decoded.count('\n', 0, match.start()) + 1, 'invisible-unicode'))
    for category, pattern in PATTERNS.items():
        for m in pattern.finditer(raw):
            found.add((raw.count(b'\n', 0, m.start()) + 1, category))
    for literal in policy['literals']:
        start = 0
        while (pos := raw.find(literal, start)) >= 0:
            found.add((raw.count(b'\n', 0, pos) + 1, 'private-literal'))
            start = pos + 1
    # Event structure is checked regardless of extension; conventional stream
    # names are also rejected even if an opaque/partial stream cannot be parsed.
    if Path(path).name in ('events.jsonl', 'stdout.log', 'stream.jsonl', 'session.jsonl'):
        found.add((1, 'raw-session'))
    for m in STREAM.finditer(raw):
        found.add((raw.count(b'\n', 0, m.start()) + 1, 'raw-session'))
    exempt = policy['exceptions'].get((target, path)) if target is not None else None
    accepted = bool(exempt and hashlib.sha256(raw).hexdigest() == exempt['sha256'])
    return {'path': safe_path(path, policy['literals']), 'sha256': hashlib.sha256(raw).hexdigest(),
            'exception': exempt if accepted else None,
            'findings': [] if accepted else [{'line': line, 'category': category} for line, category in sorted(found)]}


def _git(repo, *args):
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_LITERAL_PATHSPECS': '1'}
    p = subprocess.run(['git', '--no-replace-objects', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                        '-C', str(repo), *args], env=env, capture_output=True, timeout=30)
    if p.returncode:
        raise ContentRefused('Content guard cannot read Git object')
    return p.stdout


def scan_tree(repo, candidate, base=None, policy=None, target=None):
    if target is not None and target not in TARGETS:
        raise ContentRefused("Unknown content target")
    if not re.fullmatch('[0-9a-f]{40}', candidate) or (base is not None and not re.fullmatch('[0-9a-f]{40}', base)):
        raise ContentRefused('Content guard requires exact commit identities')
    policy = load_policy() if policy is None else policy
    selected = None if base is None else set(_git(repo, 'diff', '--no-renames', '--name-only', '--diff-filter=AMT', '-z', base, candidate).split(b'\0'))
    files = []
    for entry in _git(repo, 'ls-tree', '-rz', candidate).split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        if selected is not None and path not in selected:
            continue
        mode, kind, oid = meta.split()
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ContentRefused('Content guard refuses nonregular changed content')
        length = _git(repo, 'cat-file', '-s', oid.decode()).strip()
        if not length.isdigit() or int(length) > MAX_BLOB:
            raise ContentRefused('Content blob exceeds size limit')
        files.append(scan_blob(path.decode('utf-8', errors='surrogateescape'), _git(repo, 'cat-file', 'blob', oid.decode()), policy, target))
    return {'schema': 'nortropic-content-scan/1', 'candidate': candidate, 'base': base, 'target': target,
            'literal_status': policy['literal_status'], 'files': files,
            'passed': all(not x['findings'] for x in files)}


def require_content(repo, base, candidate, target):
    if target not in TARGETS:raise ContentRefused("Unknown content target")
    receipt = scan_tree(repo, candidate, base, target=target)
    if not receipt['passed']:
        rows = [dict(path=f['path'], **hit) for f in receipt['files'] for hit in f['findings']]
        raise ContentRefused('Content guard refused: ' + json.dumps(rows, ensure_ascii=True))
    return receipt


def require_deletion(repo,base,path,target,policy=None):
    """Only an exact privately reviewed cleanup deletion, never a task capability."""
    policy=load_policy() if policy is None else policy
    authorization=policy.get('deletions',{}).get((target,base,path))
    if not authorization:raise ContentRefused('Deletion lacks exact host cleanup authorization')
    entry=_git(repo,'ls-tree','-z',base,'--',path)
    if not entry or entry.split()[0] not in (b'100644',b'100755'):raise ContentRefused('Deletion base is not a regular file')
    size=_git(repo,'cat-file','-s',base+':'+path).strip()
    if not size.isdigit() or int(size)>MAX_BLOB:raise ContentRefused('Deletion source exceeds limit')
    if hashlib.sha256(_git(repo,'show',base+':'+path)).hexdigest()!=authorization['sha256']:
        raise ContentRefused('Deletion authorization names different source bytes')
    return {'path':safe_path(path,policy['literals']),'base':base,**authorization}
