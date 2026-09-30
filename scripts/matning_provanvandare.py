#!/Library/Developer/CommandLineTools/usr/bin/python3 -IB
"""The fixed credential-free measurement script, run as the key-less test user through ONE sudoers rule (D042).

Installed root-owned at /usr/local/libexec/nortropic/matning; config/nortropic-matning.sudoers lets the owner's
account run exactly this file, pinned by its sha256, as `_nortropicprov` and as no one else, with any arguments; this
file judges them. Sessions never run sudo (managed policy): the owner's agent runs it for a queued request
(scripts/measurement_queue.py), and the owner runs `gransprob` once by hand after installing.

    matning gransprob     the boundary probe alone: can this account read any of the owner's keys?
    matning mat ID        the probe, then the whole suite of the candidate the owner's inbox names, in a fresh clone

The interpreter is the Command Line Tools' root-owned Python (3.9), never one a session could change; so this file keeps
to what 3.9 has. What it writes goes under the test user's own home; the owner reads it there. It never writes
anything the owner owns and never prints what a probe could read: a readable key is reported by its path only.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

PROV = '_nortropicprov'
AGARE = 'elinhaggstrom'
AGARHEM = Path('/Users/elinhaggstrom')
RUNTIME = AGARHEM / 'nortropic-repos/Nortropic Runtime'
INKORG = Path('/Users/Shared/nortropic-matning/in')
PROVHEM = Path('/Users/_nortropicprov')
INSTALLERAD = Path('/usr/local/libexec/nortropic/matning')
BEGARAN = 'nortropic-matning-begaran/1'
SVIT = 'nortropic-measured-suite/1'
PROB = 'nortropic-gransprob/1'
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}')
HEX = re.compile(r'[0-9a-f]{40}')
REF = re.compile(r'refs/heads/[A-Za-z0-9._/-]{1,200}')
PATH = '/opt/homebrew/bin:/usr/bin:/bin'
VENV = RUNTIME / '.runtime/temporal-venv/bin/python'
# The worst case of one measurement, from the limits below: probe (about 300 s), clone (600 s) and five short git steps
# (60 s each), npm and browsers (900 s each), the suite (1800 s) - under 4800 s. The agent allows 5400 s (measurement_queue).
# Per repository: the suite directory the issuer's command names, the interpreter the owner's own measurement uses, the
# locale, the read-only host tools linked into the clone's .runtime, whether the clone is the host root, and an npm
# project to install (with the browsers its tests launch) in the test user's own caches.
PROFILER = {
    'runtime': {'katalog': 'scripts', 'python': VENV, 'locale': 'en_US.UTF-8',
                'lankar': ('bin', 'temporal-venv', 'web-tools'), 'vard': True, 'npm': None, 'tid': 1800},
    'kontoret': {'katalog': 'tools', 'python': Path('/opt/homebrew/bin/python3.12'), 'locale': 'C',
                 'lankar': (), 'vard': False, 'npm': None, 'tid': 1800},
    'digitala': {'katalog': 'verktyg', 'python': VENV, 'locale': 'C',
                 'lankar': (), 'vard': False, 'npm': 'verktyg/webblasare', 'tid': 1800,
                 # Digitala finds Runtime and the office as sister directories; a clone has none, so it is told (read only).
                 # Its schema tests run the ACTIVE Runtime release's own code, which only the owner can read: the
                 # session puts a view of that release's code and configuration in the request (runtime-vy).
                 'miljo': {'NR_HOST_ROOT': 'runtime-vy', 'NR_KONTOR_ROOT': str(AGARHEM / 'nortropic-repos/nortropic-projektkontor')}},
}
# The owner's keys, by his own list (App key, Claude and Codex logins, GitHub, SSH, keychain, ~/.nortropic-hemligheter).
KEYCHAIN = AGARHEM / 'Library/Keychains/login.keychain-db'
SVEP_NAMN = re.compile(r'(^auth\.json$|\.pem$|\.p12$|\.key$|^id_(rsa|ed25519|ecdsa|dsa)$|credentials|\.secret$|'
                       r'^hosts\.yml$|^\.netrc$|^\.git-credentials$|\.keychain(-db)?$|^token(s)?(\.json)?$)')
SVEP_HOPPA = {'.git', 'node_modules', 'Library', '.Trash'}


class Vagrar(Exception):
    pass


def nu():
    return datetime.now(timezone.utc).isoformat()


def sha_fil(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


class Plats:
    """Where things are. The installed script uses the constants; tests and the owner's rehearsal pass others."""

    def __init__(self, agarhem=AGARHEM, runtime=RUNTIME, inkorg=INKORG, provhem=PROVHEM, prov=PROV, agare=AGARE,
                 keychain=KEYCHAIN, skript=None):
        self.agarhem, self.runtime, self.inkorg, self.provhem = Path(agarhem), Path(runtime), Path(inkorg), Path(provhem)
        self.prov, self.agare, self.keychain = prov, agare, Path(keychain)
        self.skript = Path(skript or __file__)
        self.ut, self.arbete, self.cache = self.provhem / 'ut', self.provhem / 'arbete', self.provhem / 'cache'


def identitet(plats):
    """Who this runs as. Measures only as the test user, never as root or as a member of admin."""
    uid, euid = os.getuid(), os.geteuid()
    try:
        prov = pwd.getpwnam(plats.prov)
    except KeyError:
        raise Vagrar('the test user %s does not exist' % plats.prov)
    groups = sorted(set(os.getgroups()) | {os.getgid()})
    value = {'user': pwd.getpwuid(uid).pw_name, 'uid': uid, 'gid': os.getgid(), 'groups': groups}
    if uid != prov.pw_uid or euid != uid or uid == 0:
        raise Vagrar('this runs only as %s (uid %d), not as uid %d/%d' % (plats.prov, prov.pw_uid, uid, euid))
    if 80 in groups:
        raise Vagrar('the test user is a member of admin (gid 80); it must not be')
    return value


# ------------------------------------------------------------------------------------------------ the boundary probe
def forsok_las(path):
    try:
        with open(str(path), 'rb') as stream:
            stream.read(1)
        return 'LÄSBAR'
    except FileNotFoundError:
        return 'finns inte'
    except OSError as error:
        return 'nekad (%s)' % (error.strerror or type(error).__name__)


def forsok_lista(path):
    try:
        return 'LÄSBAR (%d poster)' % len(os.listdir(str(path)))
    except FileNotFoundError:
        return 'finns inte'
    except OSError as error:
        return 'nekad (%s)' % (error.strerror or type(error).__name__)


def forsok_kommando(argv, env):
    """A command that would print a secret: only whether it succeeded is kept, never its output."""
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=20)
    except FileNotFoundError:
        return 'finns inte'
    except (OSError, subprocess.SubprocessError) as error:
        return 'nekad (%s)' % type(error).__name__
    if done.returncode == 0 and done.stdout.strip():
        return 'LÄSBAR'
    tail = done.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] or ['']
    return 'nekad (kod %d: %s)' % (done.returncode, tail[0][:120])


def forsok_ansluta(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    try:
        client.connect(str(path))
        return 'LÄSBAR (anslutning öppnad)'
    except FileNotFoundError:
        return 'finns inte'
    except OSError as error:
        return 'nekad (%s)' % (error.strerror or type(error).__name__)
    finally:
        client.close()


def agentuttag():
    """Every launchd socket directory (the owner's SSH agent lives in one) and the sockets reachable in them."""
    found = []
    try:
        names = sorted(os.listdir('/private/tmp'))
    except OSError:
        return found
    for name in names:
        if name.startswith('com.apple.launchd.'):
            directory = Path('/private/tmp') / name
            found.append(('ssh-agentens katalog ' + str(directory), forsok_lista(directory)))
            found.append(('ssh-agentens uttag ' + str(directory / 'Listeners'), forsok_ansluta(directory / 'Listeners')))
    return found


def svep(plats, sekunder=90, poster=500000):
    """Every file under the owner's home this account can reach whose NAME looks like a key, and whether it opens."""
    start, seen, hits, cut = time.monotonic(), 0, [], None
    for root, dirs, files in os.walk(str(plats.agarhem), onerror=lambda error: None):
        dirs[:] = [d for d in dirs if d not in SVEP_HOPPA]
        seen += len(files) + len(dirs)
        for name in files:
            if SVEP_NAMN.search(name):
                path = Path(root) / name
                if not path.is_symlink() and forsok_las(path) == 'LÄSBAR':
                    hits.append(str(path))
        if time.monotonic() - start > sekunder or seen > poster:
            cut = 'svepet avbröts efter %d poster och %.0f s' % (seen, time.monotonic() - start)
            break
    return {'poster': seen, 'lasbara_med_nyckelnamn': hits[:300], 'antal': len(hits), 'avbrutet': cut}


def gransprob(plats, svep_sekunder=90):
    """Can this account read any of the owner's keys? Each case is tried for real; nothing read is kept."""
    hem = plats.agarhem
    env = {'PATH': PATH, 'HOME': str(plats.provhem), 'LANG': 'C', 'LC_ALL': 'C'}
    security = '/usr/bin/security'
    fall = [
        ('App-nyckeln', str(plats.runtime / '.runtime/ap11/check-issuer/app.pem'),
         forsok_las(plats.runtime / '.runtime/ap11/check-issuer/app.pem')),
        ('App-nyckeln', str(plats.runtime / '.runtime/ap11/check-issuer') + '/',
         forsok_lista(plats.runtime / '.runtime/ap11/check-issuer')),
        ('Claude-inloggningen', 'nyckelringen: Claude Code-credentials (sökordning)',
         forsok_kommando([security, 'find-generic-password', '-s', 'Claude Code-credentials', '-w'], env)),
        ('Claude-inloggningen', 'nyckelringen: Claude Code-credentials i ' + str(plats.keychain),
         forsok_kommando([security, 'find-generic-password', '-s', 'Claude Code-credentials', '-w', str(plats.keychain)], env)),
        ('Claude-inloggningen', str(hem / '.claude/.credentials.json'), forsok_las(hem / '.claude/.credentials.json')),
        ('Claude-inloggningen', str(hem / '.claude') + '/', forsok_lista(hem / '.claude')),
        ('Codex-inloggningen', str(hem / '.codex/auth.json'), forsok_las(hem / '.codex/auth.json')),
        ('GitHub', str(hem / '.config/gh/hosts.yml'), forsok_las(hem / '.config/gh/hosts.yml')),
        ('GitHub', str(hem / '.config') + '/', forsok_lista(hem / '.config')),
        ('GitHub', 'nyckelringen: gh:github.com i ' + str(plats.keychain),
         forsok_kommando([security, 'find-generic-password', '-s', 'gh:github.com', '-w', str(plats.keychain)], env)),
        ('GitHub', 'gh auth token', forsok_kommando(['/opt/homebrew/bin/gh', 'auth', 'token'], env)),
        ('SSH', str(hem / '.ssh') + '/', forsok_lista(hem / '.ssh')),
    ] + [('SSH', str(hem / '.ssh' / name), forsok_las(hem / '.ssh' / name))
         for name in ('id_ed25519', 'id_rsa', 'id_ecdsa', 'config', 'known_hosts')
    ] + [('SSH', what, result) for what, result in agentuttag()] + [
        ('Nyckelringen', str(hem / 'Library/Keychains') + '/', forsok_lista(hem / 'Library/Keychains')),
        ('Nyckelringen', str(plats.keychain), forsok_las(plats.keychain)),
        ('Nyckelringen', 'security show-keychain-info ' + str(plats.keychain),
         forsok_kommando([security, 'show-keychain-info', str(plats.keychain)], env)),
        ('~/.nortropic-hemligheter', str(hem / '.nortropic-hemligheter') + '/', forsok_lista(hem / '.nortropic-hemligheter')),
        ('~/.nortropic-hemligheter', str(hem / '.nortropic-hemligheter/kundstart') + '/',
         forsok_lista(hem / '.nortropic-hemligheter/kundstart')),
        # a file inside, read directly: a directory that can be passed through but not listed must not hide it
        ('~/.nortropic-hemligheter', str(hem / '.nortropic-hemligheter/kundstart/KUNDSTART_HEMLIGHET.secret'),
         forsok_las(hem / '.nortropic-hemligheter/kundstart/KUNDSTART_HEMLIGHET.secret')),
    ]
    lasbara = [{'grupp': g, 'vad': w} for g, w, r in fall if r.startswith('LÄSBAR')]
    ovrigt = [(str(hem / '.claude.json'), forsok_las(hem / '.claude.json')),
              (str(hem / '.codex') + '/', forsok_lista(hem / '.codex')),
              (str(plats.runtime / '.runtime/ap10/active.json'), forsok_las(plats.runtime / '.runtime/ap10/active.json'))]
    return {'schema': PROB, 'tid': nu(), 'identitet': identitet(plats), 'skript_sha256': sha_fil(plats.skript),
            'fall': [{'grupp': g, 'vad': w, 'resultat': r} for g, w, r in fall],
            'nycklar_lasbara': lasbara, 'kredentialfri': not lasbara,
            'utanfor_listan': [{'vad': w, 'resultat': r} for w, r in ovrigt],
            'svep': svep(plats, svep_sekunder)}


# ------------------------------------------------------------------------------------------------ the measurement
def las_begaran(plats, ident):
    """The owner's request: a regular bounded file in a directory the owner owns, of exactly the recorded shape."""
    if not ID.fullmatch(ident):
        raise Vagrar('the measurement id must match %s' % ID.pattern)
    agare = pwd.getpwnam(plats.agare).pw_uid
    katalog = plats.inkorg / ident
    for part in (plats.inkorg.parent, plats.inkorg, katalog):
        info = os.lstat(str(part))
        if not os.path.isdir(str(part)) or os.path.islink(str(part)) or info.st_uid != agare or info.st_mode & 0o022:
            raise Vagrar('%s is not a directory only the owner can write' % part)
    fil = katalog / 'begaran.json'
    info = os.lstat(str(fil))
    if os.path.islink(str(fil)) or not os.path.isfile(str(fil)) or info.st_uid != agare or info.st_size > 64 * 1024:
        raise Vagrar('the request is not a bounded regular file the owner wrote')
    value = json.loads(fil.read_text(encoding='utf-8'))
    keys = {'schema', 'id', 'repo', 'candidate', 'tree', 'ref', 'expected_test_count', 'requested_at'}
    if (not isinstance(value, dict) or set(value) != keys or value['schema'] != BEGARAN or value['id'] != ident
            or value['repo'] not in PROFILER or not isinstance(value['candidate'], str) or not HEX.fullmatch(value['candidate'])
            or not isinstance(value['tree'], str) or not HEX.fullmatch(value['tree'])
            or not isinstance(value['ref'], str) or not REF.fullmatch(value['ref']) or '..' in value['ref']
            or not (value['expected_test_count'] is None or (isinstance(value['expected_test_count'], int)
                                                             and not isinstance(value['expected_test_count'], bool)
                                                             and value['expected_test_count'] > 0))
            or not isinstance(value['requested_at'], str) or len(value['requested_at']) > 64):
        raise Vagrar('the request does not have the recorded shape')
    bundle = katalog / 'kandidat.bundle'
    info = os.lstat(str(bundle))
    if os.path.islink(str(bundle)) or not os.path.isfile(str(bundle)) or info.st_uid != agare or info.st_size > (2 << 30):
        raise Vagrar('the candidate bundle is not a bounded regular file the owner wrote')
    return value, bundle


def git(argv, cwd, env, tid=60):
    done = subprocess.run(['git'] + argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=tid)
    if done.returncode != 0:
        raise Vagrar('git %s failed: %s' % (argv[0], done.stderr.decode('utf-8', 'replace').strip()[-400:]))
    return done.stdout.decode().strip()


def temp_katalog(arbete):
    """This account's own temporary directory under /var/folders, as every macOS login has (some suites depend on
    where temporary files lie); a private one in the work area if the system gives none."""
    try:
        value = subprocess.run(['/usr/bin/getconf', 'DARWIN_USER_TEMP_DIR'], capture_output=True, text=True,
                               timeout=10).stdout.strip()
        info = os.lstat(value)
        if (value.startswith(('/var/folders/', '/private/var/folders/')) and os.path.isdir(value)
                and not os.path.islink(value) and info.st_uid == os.getuid() and not info.st_mode & 0o077):
            return value.rstrip('/') + '/'
    except (OSError, subprocess.SubprocessError):
        pass
    tmp = arbete / 'tmp'
    tmp.mkdir(mode=0o700)
    return str(tmp) + '/'


def miljo(plats, profil, arbete, repo, katalog=None):
    home = arbete / 'hem'
    for directory in (home, home / '.codex'):
        directory.mkdir(mode=0o700)
    # Runtime's command builders read the Codex home configuration (for its MCP servers); the test user's is empty, as
    # Runtime's own fixtures make it. The owner's file is never read or copied.
    (home / '.codex/config.toml').write_text('', encoding='utf-8')
    gitconfig = arbete / 'gitconfig'
    gitconfig.write_text('[user]\n\tname = Nortropic provanvändare\n\temail = prov@nortropic.invalid\n'
                         '[init]\n\tdefaultBranch = main\n', encoding='utf-8')
    env = {'PATH': PATH, 'HOME': str(home), 'USER': plats.prov, 'LOGNAME': plats.prov, 'TMPDIR': temp_katalog(arbete),
           'LANG': profil['locale'], 'LC_ALL': profil['locale'], 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
           'GIT_CONFIG_GLOBAL': str(gitconfig), 'GIT_CONFIG_NOSYSTEM': '1',
           'npm_config_cache': str(plats.cache / 'npm'), 'PLAYWRIGHT_BROWSERS_PATH': str(plats.cache / 'ms-playwright')}
    if profil['vard']:
        env['NR_HOST_ROOT'] = str(repo)
    for key, value in (profil.get('miljo') or {}).items():
        if value == 'runtime-vy':
            view = Path(katalog or '') / 'runtime-vy'
            if not katalog or not view.is_dir() or view.is_symlink():
                raise Vagrar('the request carries no view of the active Runtime release (runtime-vy); nothing else is used')
            value = str(view)
        env[key] = value
    return env


def forbered(plats, profil, repo, env, logg):
    """The read-only host tools the suite runs, linked into the clone; an npm project installed from its lock file.
    Every candidate is measured with an empty untracked .scratch, as in the owner's integration copies."""
    (repo / '.scratch').mkdir(mode=0o700)
    if profil['lankar']:
        (repo / '.runtime').mkdir(mode=0o700)
        for name in profil['lankar']:
            os.symlink(str(plats.runtime / '.runtime' / name), str(repo / '.runtime' / name))
    if profil['npm']:
        projekt = repo / profil['npm']
        for argv in (['/opt/homebrew/bin/npm', 'ci', '--no-audit', '--no-fund'],
                     ['/opt/homebrew/bin/node', 'node_modules/playwright/cli.js', 'install', 'chromium', 'webkit']):
            with open(str(logg), 'ab') as stream:
                stream.write(('$ ' + ' '.join(argv) + '\n').encode())
                stream.flush()
                done = subprocess.run(argv, cwd=str(projekt), env=env, stdin=subprocess.DEVNULL, stdout=stream,
                                      stderr=subprocess.STDOUT, timeout=900)
            if done.returncode != 0:
                raise Vagrar('%s failed with code %d; see %s' % (' '.join(argv[:3]), done.returncode, logg))


def kor_svit(argv, cwd, env, logg, tid):
    """The suite in its own process group; on the time limit the whole group is ended."""
    with open(str(logg), 'wb') as stream:
        process = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=tid), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(), True


def tolka(text):
    counts = re.findall(r'^Ran (\d+) tests? in ', text, re.M)
    lines = [line for line in text.splitlines() if line.strip()]
    return (int(counts[0]) if len(counts) == 1 else None), (lines[-1].strip() if lines else '')


def skriv(path, value):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def mat(plats, ident, svep_sekunder=90):
    """The probe, then the whole suite of exactly the requested candidate. Everything lands in ut/ID; never twice."""
    begaran, bundle = las_begaran(plats, ident)
    profil = PROFILER[begaran['repo']]
    ut, arbete = plats.ut / ident, plats.arbete / ident
    for directory in (plats.ut, plats.arbete, plats.cache):
        directory.mkdir(mode=0o755 if directory == plats.ut else 0o700, exist_ok=True)
    ut.mkdir(mode=0o755)                          # exists already: this id was measured; never again
    arbete.mkdir(mode=0o700)
    started = nu()
    prob = gransprob(plats, svep_sekunder)
    skriv(ut / 'gransprob.json', prob)
    klar = {'id': ident, 'repo': begaran['repo'], 'candidate': begaran['candidate'], 'started_at': started,
            'script_sha256': prob['skript_sha256'], 'credential_free_execution': prob['kredentialfri']}
    if not prob['kredentialfri']:
        klar.update(finished_at=nu(), refused='the test user can read a key; the suite was not run')
        skriv(ut / 'klar.json', klar)
        return klar
    repo = arbete / 'repo'
    logg = ut / 'forberedelse.log'
    try:
        base = {'PATH': PATH, 'HOME': str(arbete), 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
                'GIT_CONFIG_GLOBAL': '/dev/null'}
        git(['clone', '--quiet', '--no-checkout', str(bundle), str(repo)], arbete, base, tid=600)
        git(['checkout', '--quiet', '--detach', begaran['candidate']], repo, base)
        head, tree = git(['rev-parse', 'HEAD'], repo, base), git(['rev-parse', 'HEAD^{tree}'], repo, base)
        heads = git(['bundle', 'list-heads', str(bundle), begaran['ref']], arbete, base).split()
        if head != begaran['candidate'] or tree != begaran['tree'] or heads[:1] != [begaran['candidate']]:
            raise Vagrar('the bundle does not carry exactly the requested candidate, tree and ref')
        env = miljo(plats, profil, arbete, repo, bundle.parent)
        forbered(plats, profil, repo, env, logg)
        command = ['python', '-B', '-m', 'unittest', 'discover', '-s', profil['katalog'], '-p', 'test_*.py', '-v']
        actual = [str(profil['python'])] + command[1:]
        t0 = time.monotonic()
        code, timed_out = kor_svit(actual, repo, env, ut / 'suite.log', profil['tid'])
        wall = round(time.monotonic() - t0, 3)
        log = (ut / 'suite.log').read_bytes()
        count, last = tolka(log.decode('utf-8', 'replace'))
        status = git(['status', '--porcelain=v1', '--ignored', '--untracked-files=all'], repo, base)
        suite = {'schema': SVIT, 'candidate': head, 'tree': tree, 'command': command, 'actual_command': actual,
                 'log_sha256': hashlib.sha256(log).hexdigest(), 'returncode': code, 'timed_out': timed_out,
                 'test_count': count, 'expected_test_count': begaran['expected_test_count'], 'wall_seconds': wall,
                 'last_line': last, 'credential_free_execution': True,
                 'credential_boundary': {'kind': 'separate local user without keys (D042)',
                                         'identity': prob['identitet'], 'script': str(plats.skript),
                                         'script_sha256': prob['skript_sha256'],
                                         'probe_sha256': sha_fil(ut / 'gransprob.json'),
                                         'keys_readable': prob['nycklar_lasbara']},
                 'environment': {k: env[k] for k in sorted(env)}, 'repo': begaran['repo'], 'request_id': ident,
                 'started_at': started, 'finished_at': nu(), 'worktree_after': status.splitlines()[:200],
                 'scratch_preserved_empty': not any((repo / '.scratch').iterdir())}
        skriv(ut / 'suite.json', suite)
        klar.update(finished_at=suite['finished_at'], returncode=code, test_count=count, last_line=last,
                    suite_sha256=sha_fil(ut / 'suite.json'))
    except (Vagrar, OSError, subprocess.SubprocessError, ValueError) as error:
        klar.update(finished_at=nu(), refused=str(error))
    finally:
        shutil.rmtree(str(arbete), ignore_errors=True)
    skriv(ut / 'klar.json', klar)
    return klar


def main(argv):
    os.umask(0o022)
    plats = Plats()
    try:
        os.chdir(str(plats.provhem))
        if argv[1:] == ['gransprob']:
            identitet(plats)
            value = gransprob(plats)
            plats.ut.mkdir(mode=0o755, exist_ok=True)
            skriv(plats.ut / ('gransprob-%s.json' % datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')), value)
            print(json.dumps(value, indent=2, ensure_ascii=False))
            return 0 if value['kredentialfri'] else 3
        if len(argv) == 3 and argv[1] == 'mat':
            identitet(plats)
            value = mat(plats, argv[2])
            print(json.dumps(value, indent=2, ensure_ascii=False))
            return 0 if value.get('returncode') == 0 and value.get('credential_free_execution') else 1
        raise Vagrar('usage: matning gransprob | matning mat ID')
    except (Vagrar, OSError, ValueError, KeyError) as error:
        print('VÄGRAR: %s' % error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
