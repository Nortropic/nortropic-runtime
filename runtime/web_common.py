"""Shared ground for the three web profiles (D034): run directories, receipts, the secret, tools and the grammar.

The profiles are host commands, not engine workflows: their evidence is the run directory itself, created exclusively,
never overwritten, and closed by a receipt that hashes every file in it. Nothing here writes into a repository.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets as token_source
import stat
import subprocess
import urllib.parse
from datetime import datetime, timezone

from .release import CODE_ROOT, ROOT

WEB = CODE_ROOT / 'runtime/web'
GRAMMAR_FILE = WEB / 'grammar.json'
TOOLS_LOCK = CODE_ROOT / 'config/web-tools.lock.json'
NODE = Path('/opt/homebrew/opt/node@22/bin/node')
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
CHROME_PLIST = Path('/Applications/Google Chrome.app/Contents/Info.plist')
IMPECCABLE_VERSION = '0.1.6'
IMPECCABLE_SHA256 = 'efa0860cce03382e4d384709529b9892eaaa20dd49c3e5fcf73e680abc6d7574'
PROFILES = ('matning', 'kritik', 'provare', 'vardprov')
LABEL = re.compile(r'\A[a-z0-9][a-z0-9-]{0,39}\Z')
SECRET_KINDS = {
    # The only protection exception in use (the existing Vercel automation exception). The header is attached to
    # requests for the target origin only; the second one asks the host to set its own cookie at priming.
    'vercel-automation-bypass': {'header': 'x-vercel-protection-bypass',
                                 'priming': {'x-vercel-set-bypass-cookie': 'true'}},
}
# Places the Codex sandbox can read or write whatever its table says (measured: /tmp is always writable, /etc
# readable), plus the per-user temporary tree. A secret file there would be within the model's reach.
SECRET_FORBIDDEN_PREFIXES = ('/tmp', '/private/tmp', '/etc', '/private/etc', '/var/folders', '/private/var/folders')
SECRET_MAX_BYTES = 4096
# Shorter values would escape the output search, whose encoded forms must be long enough not to match by chance.
SECRET_MIN_CHARS = 16


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def label(value):
    if not isinstance(value, str) or not LABEL.match(value):
        raise ValueError('A label is 1-40 characters of a-z, 0-9 and hyphen, starting with a letter or digit')
    return value


def new_run_directory(profile, name):
    """The run's own directory under the host's private area; never an existing one."""
    if profile not in PROFILES:
        raise ValueError('Unknown profile')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = ROOT / '.runtime/profiler' / profile
    base.mkdir(parents=True, exist_ok=True)
    run = base / ('%s-%s' % (stamp, label(name)))
    run.mkdir(exist_ok=False)
    return run


def code_files(*relative):
    """SHA256 of the code a profile actually runs, as the receipt's version."""
    return {rel: sha256_file(CODE_ROOT / rel) for rel in sorted(set(relative))}


def code_root_info():
    info = {'code_root': str(CODE_ROOT), 'host_root': str(ROOT), 'commit': None, 'clean': None,
            'active_release': False}
    try:
        info['commit'] = subprocess.run(['git', '-C', str(CODE_ROOT), 'rev-parse', 'HEAD'], capture_output=True,
                                        text=True, timeout=20, check=True).stdout.strip()
        info['clean'] = subprocess.run(['git', '-C', str(CODE_ROOT), 'status', '--porcelain'], capture_output=True,
                                       text=True, timeout=20, check=True).stdout == ''
    except (OSError, subprocess.SubprocessError):
        pass
    active = ROOT / '.runtime/ap10/active.json'
    try:
        release = Path(json.loads(active.read_text())['config']).resolve().parent
        info['active_release'] = release / 'runtime' == CODE_ROOT
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return info


def read_secret(path, forbidden_root=None):
    """The exception's value, from a private file only. Never logged, never returned to a caller that prints."""
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError('The exception file must be named by an absolute path')
    info = os.lstat(candidate)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError('The exception file must be a regular file, not a link')
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise ValueError('The exception file must be owned by this user with mode 0600')
    if info.st_size > SECRET_MAX_BYTES or info.st_size == 0:
        raise ValueError('The exception file is empty or too large')
    resolved = str(candidate.resolve())
    for prefix in SECRET_FORBIDDEN_PREFIXES:
        if resolved == prefix or resolved.startswith(prefix + '/'):
            raise ValueError('The exception file lies where a sandboxed model could read it')
    if forbidden_root is not None and (resolved + '/').startswith(str(Path(forbidden_root).resolve()) + '/'):
        raise ValueError('The exception file lies inside the run area of the profiles')
    raw = candidate.read_bytes().strip()
    if not raw or b'\n' in raw or b'\r' in raw or any(b < 0x21 or b > 0x7e for b in raw):
        raise ValueError('The exception file must hold one line of printable ASCII')
    if len(raw) < SECRET_MIN_CHARS:
        raise ValueError('The exception value is shorter than %d characters' % SECRET_MIN_CHARS)
    return raw.decode('ascii')


def secret_forms(secret):
    """Every form in which the value could plausibly be written: plain, URL-encoded, base64 of each."""
    raw = secret.encode()
    forms = {raw, urllib.parse.quote(secret, safe='').encode(), base64.b64encode(raw),
             base64.urlsafe_b64encode(raw), base64.b64encode(raw).rstrip(b'=')}
    return sorted(f for f in forms if len(f) >= 8)


def secret_hits(root, secret):
    """Files under root that contain the secret in any form, as (relative path, size)."""
    forms = secret_forms(secret)
    hits = []
    for current, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            data = path.read_bytes()
            if any(form in data for form in forms):
                hits.append((str(path.relative_to(root)), len(data)))
    return hits


def remove_contaminated(root, hits):
    removed = []
    for rel, size in hits:
        path = Path(root) / rel
        path.unlink()
        removed.append({'path': rel, 'bytes': size})
    return removed


def filtered_environment(extra=None):
    """A child environment with nothing that looks like a credential, a token or a key."""
    keep = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR')}
    keep.update(extra or {})
    return {k: v for k, v in keep.items()
            if not re.search(r'SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL|BYPASS', k, re.I) or k in (extra or {})}


def load_grammar():
    grammar = json.loads(GRAMMAR_FILE.read_text())
    if grammar.get('format') != 1 or grammar.get('command') != './handling':
        raise ValueError('Unexpected grammar file')
    grammar['_compiled'] = {k: re.compile(v) for k, v in grammar['patterns'].items()}
    return grammar


def page_url_allowed(url, allowed_origins, grammar=None):
    """The visitor's address rule: a page within the allowlist, no query or fragment, no API or asset path."""
    grammar = grammar or load_grammar()
    if not isinstance(url, str) or not grammar['_compiled']['url'].fullmatch(url):
        return False
    parts = urllib.parse.urlsplit(url)
    origin = '%s://%s' % (parts.scheme, parts.netloc)
    if origin not in allowed_origins or parts.query or parts.fragment:
        return False
    path = parts.path or '/'
    for prefix in grammar['page']['denied_prefixes']:
        if path == prefix or path.startswith(prefix + '/'):
            return False
    last = path.rsplit('/', 1)[-1]
    suffix = ('.' + last.rsplit('.', 1)[1]) if '.' in last else ''
    return suffix.lower() in grammar['page']['allowed_suffixes']


def validate_action(arguments, grammar=None):
    """One action as a list of words: (verb, normalized arguments) or ValueError with a reason a visitor can read."""
    grammar = grammar or load_grammar()
    compiled = grammar['_compiled']
    if not isinstance(arguments, list) or not arguments or not all(isinstance(a, str) for a in arguments):
        raise ValueError('ange en handling')
    if len(arguments) > grammar['max_arguments'] or len(' '.join(arguments)) > grammar['max_argument_chars']:
        raise ValueError('för långt kommando')
    joined = ' '.join(arguments)
    if compiled['forbidden'].search(joined):
        raise ValueError('argumenten innehåller otillåtna tecken')
    if any(a == '' or ' ' in a for a in arguments):
        raise ValueError('ogiltiga mellanrum')
    verb, rest = arguments[0], arguments[1:]
    if verb not in grammar['verbs']:
        raise ValueError('okänd handling; tillåtna: ' + ', '.join(grammar['verbs']))
    shape = grammar['verbs'][verb]
    if not shape:
        if rest:
            raise ValueError('ogiltiga argument för ' + verb)
        return verb, []
    if len(shape) == 2 and shape[1] == 'text':
        if len(rest) < 2 or not compiled['number'].fullmatch(rest[0]) or not compiled['text'].fullmatch(' '.join(rest[1:])):
            raise ValueError('ogiltiga argument för ' + verb)
        return verb, [rest[0], ' '.join(rest[1:])]
    if len(rest) != len(shape) or not all(compiled[kind].fullmatch(value) for kind, value in zip(shape, rest)):
        raise ValueError('ogiltiga argument för ' + verb)
    return verb, rest


def command_words(command, grammar=None):
    """The words of a visitor's Bash command, or None if it is not exactly the action command with single spaces."""
    grammar = grammar or load_grammar()
    if not isinstance(command, str) or grammar['_compiled']['forbidden'].search(command):
        return None
    prefix = grammar['command'] + ' '
    if not command.startswith(prefix) or command != command.strip() or '  ' in command:
        return None
    return command[len(prefix):].split(' ')


def chrome_identity():
    try:
        plist = plistlib.loads(CHROME_PLIST.read_bytes())
        version = plist.get('CFBundleShortVersionString')
    except (OSError, plistlib.InvalidFileException):
        version = None
    return {'path': str(CHROME), 'version': version, 'present': CHROME.is_file()}


def node_identity():
    if not NODE.is_file():
        return {'path': str(NODE), 'present': False}
    version = subprocess.run([str(NODE), '--version'], capture_output=True, text=True, timeout=20).stdout.strip()
    return {'path': str(NODE), 'present': True, 'version': version, 'sha256': sha256_file(NODE.resolve())}


def tools_directory():
    return ROOT / '.runtime/web-tools/node_modules'


def impeccable_binary():
    binary = ROOT / '.runtime/bin' / ('impeccable-' + IMPECCABLE_VERSION)
    if binary.is_symlink() or not binary.is_file() or sha256_file(binary) != IMPECCABLE_SHA256:
        raise ValueError('The pinned Impeccable engine is missing or changed')
    return binary


def verify_tools():
    """The host's pinned tool copy, checked tree by tree against the lock the candidate carries."""
    lock = json.loads(TOOLS_LOCK.read_text())
    directory = tools_directory()
    if not directory.is_dir():
        raise ValueError('The pinned web tools are not installed; run scripts/install_web_tools.py')
    for key, expected in sorted(lock['packages'].items()):
        package = directory.parent / key
        files = {}
        for current, dirs, names in os.walk(package):
            dirs[:] = sorted(d for d in dirs if d != 'node_modules')
            for name in sorted(names):
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Unexpected file in the pinned web tools: ' + key)
                files[str(path.relative_to(package))] = sha256_file(path)
        tree = sha256_bytes(''.join('%s\0%s\n' % (r, d) for r, d in sorted(files.items())).encode())
        if tree != expected['tree_sha256'] or len(files) != expected['files']:
            raise ValueError('The pinned web tools differ from the lock: ' + key)
    return {'lock_sha256': sha256_file(TOOLS_LOCK), 'tree_sha256': lock['tree_sha256'],
            'packages': len(lock['packages'])}


def tool_identity(with_impeccable=False):
    identity = {'chrome': chrome_identity(), 'node': node_identity(), 'web_tools': verify_tools()}
    if with_impeccable:
        identity['impeccable'] = {'version': IMPECCABLE_VERSION, 'sha256': sha256_file(impeccable_binary())}
    return identity


def output_map(run_directory, exclude=('KVITTO.json', 'KVITTO.sha256')):
    outputs = {}
    for current, dirs, names in os.walk(run_directory):
        dirs.sort()
        for name in sorted(names):
            path = Path(current) / name
            rel = str(path.relative_to(run_directory))
            if rel in exclude or path.is_symlink() or not path.is_file():
                continue
            outputs[rel] = {'sha256': sha256_file(path), 'bytes': path.stat().st_size}
    return outputs


def write_receipt(run_directory, receipt):
    """The receipt is the last write: every other file in the run is hashed into it."""
    receipt = dict(receipt)
    receipt['outputs'] = output_map(run_directory)
    receipt['closed_at'] = now()
    data = (json.dumps(receipt, indent=1, ensure_ascii=False, sort_keys=True) + '\n').encode()
    with open(Path(run_directory) / 'KVITTO.json', 'xb') as stream:
        stream.write(data)
    with open(Path(run_directory) / 'KVITTO.sha256', 'x') as stream:
        stream.write(sha256_bytes(data) + '  KVITTO.json\n')
    return receipt


def copy_regular(source, destination, limit):
    """Copy one regular file without following a link anywhere on its path.

    Returns (source sha256 as read, copy sha256 as re-read, bytes); the two are equal or the copy is refused.
    """
    source = Path(source)
    if not source.is_absolute():
        raise ValueError('Sources are named by absolute paths')
    if str(source.resolve()) != os.path.normpath(str(source)):
        raise ValueError('A source path may not pass through a link: ' + str(source))
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('Not a regular file: ' + str(source))
        if before.st_size > limit:
            raise ValueError('File exceeds the per-file limit: ' + str(source))
        digest, total = hashlib.sha256(), 0
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, 'xb') as out:
            while True:
                chunk = os.read(descriptor, 1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError('File grew past the per-file limit: ' + str(source))
                digest.update(chunk)
                out.write(chunk)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or total != before.st_size:
            raise ValueError('Source changed while copying: ' + str(source))
    finally:
        os.close(descriptor)
    copied = sha256_file(destination)
    if copied != digest.hexdigest():
        raise ValueError('Copy differs from the source bytes: ' + str(source))
    return digest.hexdigest(), copied, total


def run_token():
    return token_source.token_hex(8)
