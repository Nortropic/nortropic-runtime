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
import errno
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone

PROV = '_nortropicprov'
AGARE = 'NORTROPIC_OWNER'  # install-time sudoers placeholder, never a live account lookup
INKORG = Path('/Users') / 'Shared/nortropic-matning/in'
# D042's existing fixed work home. The service account's directory-service
# login home is /var/empty; it is deliberately not a general login account.
PROVHEM = Path('/Users') / PROV
INSTALLERAD = Path('/usr/local/libexec/nortropic/matning')
BEGARAN = 'nortropic-matning-begaran/1'
SVIT = 'nortropic-measured-suite/1'
PROB = 'nortropic-gransprob/1'
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}')
HEX = re.compile(r'[0-9a-f]{40}')
REF = re.compile(r'refs/heads/[A-Za-z0-9._/-]{1,200}')
PATH = '/opt/homebrew/bin:/usr/bin:/bin'
# Historical in-process diagnostic helper only. Candidate code can mutate this
# interpreter: its schema-1 output is never primary publication evidence.
# observe_suite is the historical schema-2 method; only the adopted owner
# observer plus OWNER_EVENT_RUNNER supplies schema-3 primary observations.
TIMED_RUNNER = r'''
import hashlib,json,os,re,sys,time,unittest
from pathlib import Path
stream=open(sys.argv[2], 'x', encoding='utf-8')
counter=0
def name(test):
    value=test.id()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}',value) or len(value)>512 or re.search(r'gh[pousr]_|sk[_-]|xox[baprs]-|AKIA',value):
        return 'masked-'+hashlib.sha256(value.encode()).hexdigest()
    return value
def write(row):
    stream.write(json.dumps(row,sort_keys=True)+'\n');stream.flush()
def filename(test):
    try:
        source=Path(sys.modules[type(test).__module__].__file__).resolve().relative_to(Path.cwd().resolve())
        value=source.as_posix()
        if re.fullmatch(r'[A-Za-z0-9_./-]+',value) and '..' not in source.parts:return value
    except (AttributeError,KeyError,TypeError,ValueError):pass
    return None
class Timed(unittest.TextTestResult):
    def startTest(self,test):
        global counter
        counter+=1;self.current=(counter,name(test),time.monotonic(),filename(test));self.status='success'
        write({'event':'start','order':counter,'name':self.current[1],'file':self.current[3]})
        super().startTest(test)
    def mark(self,test,status):
        global counter
        if getattr(self,'current',None):self.status=status
        else:
            counter+=1;write({'event':'stop','order':counter,'name':name(test),'file':filename(test),'seconds':None,'status':status})
    def addFailure(self,test,err):self.mark(test,'failure');super().addFailure(test,err)
    def addError(self,test,err):self.mark(test,'error');super().addError(test,err)
    def addSkip(self,test,reason):self.mark(test,'skipped');super().addSkip(test,reason)
    def addExpectedFailure(self,test,err):self.mark(test,'failure');super().addExpectedFailure(test,err)
    def addUnexpectedSuccess(self,test):self.mark(test,'error');super().addUnexpectedSuccess(test)
    def addSubTest(self,test,subtest,err):
        if err:self.mark(test,'failure')
        super().addSubTest(test,subtest,err)
    def stopTest(self,test):
        order,identifier,began,file=self.current
        write({'event':'stop','order':order,'name':identifier,'file':file,'seconds':round(time.monotonic()-began,6),'status':self.status})
        self.current=None;super().stopTest(test)
suite=unittest.defaultTestLoader.discover(sys.argv[1],pattern='test_*.py') if len(sys.argv)==3 else unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:])
result=unittest.TextTestRunner(verbosity=2,resultclass=Timed).run(suite)
stream.close()
sys.exit(0 if result.wasSuccessful() else 1)
'''
# Prepared schema-3 event runner; only the distinct owner process writes observations.
OWNER_EVENT_RUNNER = "# Fixed root-owned program text; candidate imports happen only in this child.\nimport hashlib,io,json,os,sys,unittest\nfrom pathlib import Path\nwire=sys.stdout\nsys.stdout=sys.stderr\nroot=Path(sys.argv[1]).resolve();directory=sys.argv[2];mode=sys.argv[3]\nsys.path.insert(0,str(root));sys.path.insert(0,str(root/directory))\nwith open(sys.argv[4],encoding='utf-8') as f:plan=json.load(f)\nnames=plan.get('names',[])\nsuite=(unittest.defaultTestLoader.loadTestsFromNames(names) if names else unittest.defaultTestLoader.discover(directory,pattern='test_*.py'))\ndef flat(node):\n    if isinstance(node,unittest.TestSuite):\n        for child in node:yield from flat(child)\n    else:yield node\nitems=list(flat(suite));rows=[]\nfor number,test in enumerate(items,1):\n    module=sys.modules[type(test).__module__]\n    file=Path(module.__file__).resolve().relative_to(root).as_posix()\n    rows.append({'id':number,'name':test.id(),'file':file})\ndef encoded(value):return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\\n').encode()\ndef send(value):wire.write(encoded(value).decode());wire.flush()\nmanifest_sha=hashlib.sha256(encoded(rows)).hexdigest()\nif mode=='inventory':\n    send({'schema':'nortropic-test-inventory/1','rows':rows,'manifest_sha256':manifest_sha})\n    raise SystemExit(0)\nif mode!='run' or rows!=plan['manifest']:\n    raise SystemExit('Manifest differs from the independently frozen inventory')\nids={id(test):number for number,test in enumerate(items,1)}\ndef event(kind,**fields):send({'schema':'nortropic-test-event/1','event':kind,**fields})\nclass Observed(unittest.TextTestResult):\n    active=None\n    next_id=1\n    def startTest(self,test):\n        number=ids[id(test)];self.active=number;self.next_id=number+1;self.status='success'\n        event('start',id=number);super().startTest(test)\n    def mark(self,test,status):\n        if self.active is None:event('fixture-error',before_id=self.next_id,status='skipped' if status=='skipped' else 'error')\n        else:self.status=status\n    def addFailure(self,test,error):self.mark(test,'failure');super().addFailure(test,error)\n    def addError(self,test,error):self.mark(test,'error');super().addError(test,error)\n    def addSkip(self,test,reason):self.mark(test,'skipped');super().addSkip(test,reason)\n    def addExpectedFailure(self,test,error):self.mark(test,'failure');super().addExpectedFailure(test,error)\n    def addUnexpectedSuccess(self,test):self.mark(test,'error');super().addUnexpectedSuccess(test)\n    def addSubTest(self,test,subtest,error):\n        if error:self.mark(test,'failure')\n        super().addSubTest(test,subtest,error)\n    def stopTest(self,test):\n        event('stop',id=ids[id(test)],status=self.status);self.active=None;super().stopTest(test)\nresult=unittest.TextTestRunner(stream=sys.stderr,verbosity=2,resultclass=Observed).run(suite)\nevent('terminal',count=result.testsRun,successful=result.wasSuccessful(),manifest_sha256=manifest_sha)\nraise SystemExit(0 if result.wasSuccessful() else 1)\n"

VENV = 'runtime-python'
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
                 'miljo': {'NR_HOST_ROOT': 'runtime-vy', 'NR_KONTOR_ROOT': 'kontor-root'}},
}
# The owner's keys, by his own list (App key, Claude and Codex logins, GitHub, SSH, keychain, ~/.nortropic-hemligheter).
KEYCHAIN = None
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

    def __init__(self, agarhem=None, runtime=None, inkorg=INKORG, provhem=None, prov=PROV, agare=None,
                 keychain=None, skript=None):
        # The existing fixed inbox's OS owner binds the account. No HOME or
        # caller-chosen name selects a live measurement owner; explicit inputs
        # are only for isolated fixtures/rehearsals, never exposed by main().
        self.inkorg = Path(inkorg)
        if agare is not None and agarhem is None:
            agarhem = pwd.getpwnam(agare).pw_dir  # explicit isolated fixture binding
        if agare is None or agarhem is None:
            info = self.inkorg.lstat()
            if self.inkorg.is_symlink() or not self.inkorg.is_dir() or info.st_mode & 0o022:
                raise Vagrar('fixed owner inbox is unsafe')
            owner = pwd.getpwuid(info.st_uid)
            if owner.pw_uid == 0 or owner.pw_name == PROV:
                raise Vagrar('fixed inbox must belong to the actual owner')
            agare = owner.pw_name if agare is None else agare
            agarhem = owner.pw_dir if agarhem is None else agarhem
        self.agarhem = Path(agarhem)
        self.runtime = Path(runtime) if runtime is not None else self.agarhem/'nortropic-repos/Nortropic Runtime'
        try:
            self.provhem = Path(provhem) if provhem is not None else PROVHEM
        except KeyError:
            raise Vagrar('the test user %s does not exist' % prov)
        self.prov, self.agare = prov, agare
        self.keychain = Path(keychain) if keychain is not None else self.agarhem/'Library/Keychains/login.keychain-db'
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
def probfel(error):
    if isinstance(error,FileNotFoundError):return 'finns inte'
    if isinstance(error,PermissionError) and error.errno in (errno.EACCES,errno.EPERM):return 'nekad (OS-behorighet)'
    return 'okant (%s)' % type(error).__name__


def forsok_las(path):
    try:
        # Follow credential links deliberately, but never block on a FIFO or
        # read an unqualified device. No content byte is retained or printed.
        fd=os.open(str(path),os.O_RDONLY|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):return 'okant (inte vanlig fil)'
            stream.read(1)
        return 'LÄSBAR'
    except OSError as error:
        return probfel(error)


def forsok_lista(path):
    try:
        return 'LÄSBAR (%d poster)' % len(os.listdir(str(path)))
    except OSError as error:
        return probfel(error)


def forsok_kommando(argv, env):
    """A command that would print a secret: only whether it succeeded is kept, never its output."""
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        # This concerns the examination tool, never the credential itself.
        # Missing/denied executable and transport failure are all unknown.
        return 'okant (kommandostart %s)' % type(error).__name__
    if done.returncode == 0:
        return 'LÄSBAR'
    # Nonzero alone is not proof of denial: I/O, transport and syntax errors
    # must not be mistaken for an absent key. Only known command outcomes are
    # accepted, without copying potentially sensitive stderr into the report.
    message=done.stderr.decode('utf-8','replace').strip()
    security={44:'The specified item could not be found in the keychain.',
              36:'User interaction is not allowed.',
              50:'The specified keychain could not be found.'}
    if (argv[:2]==['/usr/bin/security','find-generic-password'] or
            argv[:2]==['/usr/bin/security','show-keychain-info']):
        if done.returncode in security and message.endswith(security[done.returncode]):
            return 'nekad (verifierat nyckelringsutfall %d)' % done.returncode
    if argv==['/opt/homebrew/bin/gh','auth','token'] and done.returncode==1 and message=='no oauth token found for github.com':
        return 'finns inte (GitHub-token)'
    return 'okant (kommandokod %d)' % done.returncode


def forsok_ansluta(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    try:
        client.connect(str(path))
        return 'LÄSBAR (anslutning öppnad)'
    except OSError as error:
        if error.errno==errno.ECONNREFUSED:return 'nekad (ingen lyssnare)'
        return probfel(error)
    finally:
        client.close()


def agentuttag():
    """Every launchd socket directory (the owner's SSH agent lives in one) and the sockets reachable in them."""
    found = []
    try:
        names = sorted(os.listdir('/private/tmp'))
    except OSError as error:
        return [('ssh-agenternas sokrot /private/tmp',probfel(error))]
    for name in names:
        if name.startswith('com.apple.launchd.'):
            directory = Path('/private/tmp') / name
            found.append(('ssh-agentens katalog ' + str(directory), forsok_lista(directory)))
            found.append(('ssh-agentens uttag ' + str(directory / 'Listeners'), forsok_ansluta(directory / 'Listeners')))
    return found


def svep(plats, sekunder=90, poster=500000):
    """Every file under the owner's home this account can reach whose NAME looks like a key, and whether it opens."""
    start, seen, hits, cut = time.monotonic(), 0, [], None
    visited=set();pending=[plats.agarhem];unknown=[]
    def scan_error(error):
        result=probfel(error)
        if result.startswith('okant'):unknown.append(result)
    def over_budget():return time.monotonic()-start>sekunder or seen>poster
    while pending:
        if over_budget():
            cut='svepet avbrots efter %d poster' % seen;break
        root=pending.pop()
        try:
            info=os.stat(root);identity=(info.st_dev,info.st_ino)
            if identity in visited:continue
            visited.add(identity)
            # Explicit scandir/stat: os.walk suppresses individual entry.stat
            # errors, which must remain unknown instead of looking complete.
            with os.scandir(root) as entries:
                for entry in entries:
                    if over_budget():
                        cut='svepet avbrots efter %d poster' % seen;break
                    try:info=entry.stat(follow_symlinks=True)
                    except OSError as error:
                        scan_error(error);continue
                    if stat.S_ISDIR(info.st_mode) and entry.name in SVEP_HOPPA:continue
                    seen+=1
                    if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path))
                    elif SVEP_NAMN.search(entry.name):
                        result=forsok_las(Path(entry.path))
                        if result=='LÄSBAR':hits.append(entry.path)
                        elif result.startswith('okant'):unknown.append(result)
        except OSError as error:scan_error(error)
        if unknown:
            cut='okant undersokningsutfall: '+unknown[0];break
        if cut is not None:break
    return {'poster':seen,'lasbara_med_nyckelnamn':hits[:300],'antal':len(hits),'avbrutet':cut}


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
    unknown=[{'grupp':g,'vad':w,'resultat':r} for g,w,r in fall if r.startswith('okant')]
    unknown += [{'grupp':'utanfor_listan','vad':w,'resultat':r} for w,r in ovrigt if r.startswith('okant')]
    sweep=svep(plats,svep_sekunder)
    clean=not lasbara and not unknown and sweep['antal']==0 and sweep['avbrutet'] is None
    return {'schema': PROB, 'tid': nu(), 'identitet': identitet(plats), 'skript_sha256': sha_fil(plats.skript),
            'fall': [{'grupp': g, 'vad': w, 'resultat': r} for g, w, r in fall],
            'nycklar_lasbara': lasbara, 'undersokningsfel':unknown, 'kredentialfri': clean,
            'utanfor_listan': [{'vad': w, 'resultat': r} for w, r in ovrigt],
            'svep': sweep}


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
    if os.path.islink(str(fil)) or not os.path.isfile(str(fil)) or info.st_uid != agare or info.st_mode & 0o022 or info.st_size > 64 * 1024:
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
    if os.path.islink(str(bundle)) or not os.path.isfile(str(bundle)) or info.st_uid != agare or info.st_mode & 0o022 or info.st_size > (2 << 30):
        raise Vagrar('the candidate bundle is not a bounded regular file the owner wrote')
    return value, bundle


def git(argv, cwd, env, tid=60):
    done = subprocess.run(['git', '--no-replace-objects'] + argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
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
            return tempfile.mkdtemp(prefix='nortropic-matning-',dir=value).rstrip('/') + '/'
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
        if value == 'kontor-root':
            value = str(plats.agarhem/'nortropic-repos/nortropic-projektkontor')
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


# Discovery runs untrusted imports only in a child. The supervisor itself never
# imports a candidate module or receives a writable result-file descriptor.
DISCOVER_CASES = r'''
import io,json,sys,unittest
from pathlib import Path
root=Path.cwd().resolve(); sys.path.insert(0,str(root/sys.argv[1]))
original=sys.stdout;sys.stdout=io.StringIO()
suite=(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]) if len(sys.argv)>2
       else unittest.defaultTestLoader.discover(sys.argv[1],pattern='test_*.py'))
def flatten(node):
    if isinstance(node,unittest.TestSuite):
        for part in node:
            yield from flatten(part)
    else:
        file=Path(sys.modules[type(node).__module__].__file__).resolve().relative_to(root).as_posix()
        yield {'name':node.id(),'file':file}
rows=list(flatten(suite));sys.stdout=original;print(json.dumps(rows))
'''
ONE_CASE = r'''
import sys,unittest
sys.path.insert(0,sys.argv[1]);sys.argv=['unittest',sys.argv[2],'-v']
unittest.main(module=None)
'''


def observation_profile(repo, env, output, owner_home, extra_protected=()):
    """Read-only source and result/ledger denial, with bounded fixture write roots.

    Candidate code can affect its own assertions/exit status. It cannot edit the
    observer's clock, result files, or source through this child boundary. These
    are process wall times (including import/setup), not in-process body timings.
    The same UID outside this sandbox is not an adversarial-owner boundary.
    """
    repo, output = Path(repo).resolve(), Path(output).resolve()
    writable = [repo/'.scratch', Path(env['HOME']).resolve(), Path(env['TMPDIR']).resolve()]
    for key in ('npm_config_cache','PLAYWRIGHT_BROWSERS_PATH'):
        if env.get(key):writable.append(Path(env[key]).resolve())
    protected=[output,Path(owner_home)/'Library/Application Support/Nortropic/test-ledger',
               *[Path(p).resolve() for p in extra_protected]]
    for root in writable:
        if root == repo or root in repo.parents or any(root == p or root in p.parents for p in protected):
            raise Vagrar('observation write root overlaps protected source/results')
        root.mkdir(parents=True,exist_ok=True)
    writable_rules=' '.join('(subpath '+json.dumps(str(p))+')' for p in writable)
    denied=[Path(owner_home)/p for p in ('.nortropic-hemligheter','Library/Keychains','.config/gh','.ssh',
            '.codex','.claude','.claude.json','.aws','.docker','.vercel','.git-credentials','.netrc',
            'nortropic-repos/Nortropic Runtime/.runtime/ap11/check-issuer')]+protected
    return ('(version 1)\n(allow default)\n'
            '(deny file-write* (require-not (require-any '+writable_rules+' (literal "/dev/null"))))\n'
            '(deny file-read* '+' '.join('(subpath '+json.dumps(str(p))+')' for p in denied)+')\n'
            '(deny signal (require-not (require-any (target self) (target children))))\n'
            '(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd") '
            '(global-name "com.apple.security.agent") (global-name "com.apple.secd"))\n'
            '(deny network-outbound)\n(allow network-outbound (remote ip "localhost:*"))\n'
            '(deny network-inbound)\n(allow network-inbound (local ip "localhost:*"))\n')


def observe_child(argv, repo, env, profile, seconds):
    """Only the parent timestamps, owns result files, and records process status."""
    import selectors
    began=time.monotonic();deadline=began+seconds
    output=bytearray();limited=False;timed_out=False;poll=None
    child=subprocess.Popen(['/usr/bin/sandbox-exec','-p',profile]+argv,cwd=str(repo),env=env,
                           stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           start_new_session=True,close_fds=True)
    try:
        poll=selectors.DefaultSelector();poll.register(child.stdout,selectors.EVENT_READ)
        while poll.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:timed_out=True;break
            for key,_ in poll.select(min(.2,remaining)):
                data=os.read(key.fileobj.fileno(),65536)
                if not data:poll.unregister(key.fileobj);continue
                if len(output)+len(data)>8*1024*1024:limited=True;break
                output.extend(data)
            if limited:break
        if not timed_out and not limited:
            try:child.wait(timeout=max(.05,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:timed_out=True
    finally:
        try:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            finally:child.wait(timeout=10)
        finally:
            from contextlib import ExitStack
            with ExitStack() as handles:
                handles.callback(child.stdout.close)
                if poll is not None:handles.callback(poll.close)
    return {'returncode':child.returncode,'seconds':round(time.monotonic()-began,6),
            'timed_out':timed_out,'output_limit_exceeded':limited,'output':bytes(output)}


def observe_suite(python, directory, repo, env, output, seconds, expected_count=None, names=(),
                  owner_home=None, extra_protected=()):
    """One ordered batch; each discovered case has an externally measured process.

    Discovery remains candidate-controlled test inventory; the independently
    accepted count and code review protect its meaning. No claimed resistance to
    a deliberately fake test assertion. Per-case process isolation is explicit;
    it does not claim shared interpreter state across cases.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    owner_home=Path(owner_home) if owner_home is not None else Path(pwd.getpwuid(os.getuid()).pw_dir)
    profile=observation_profile(repo,env,output,owner_home,extra_protected)
    (output/'boundary.sb').write_text(profile)
    began=time.monotonic();cases=[];complete=True
    discovery=observe_child([str(python),'-B','-c',DISCOVER_CASES,directory,*names],repo,env,profile,min(120,seconds))
    with (output/'discovery.log').open('xb') as f:f.write(discovery['output'])
    try:
        inventory=json.loads(discovery['output'])
        if (discovery['returncode'] or discovery['timed_out'] or discovery['output_limit_exceeded']
            or not isinstance(inventory,list) or not inventory or len(inventory)>100000
            or expected_count is not None and len(inventory)!=expected_count):raise ValueError
        seen=set()
        for row in inventory:
            if (not isinstance(row,dict) or set(row)!={'name','file'}
                or not isinstance(row['name'],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}',row['name'])
                or row['name'] in seen or len(row['name'])>512
                or not isinstance(row['file'],str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',row['file'])
                or row['file'].startswith('/') or '..' in Path(row['file']).parts):raise ValueError
            seen.add(row['name'])
    except (ValueError,KeyError,TypeError):inventory=[];complete=False
    with (output/'cases.jsonl').open('x') as events, (output/'suite.log').open('x') as log:
        for order,item in enumerate(inventory,1):
            remaining=seconds-(time.monotonic()-began)
            if remaining<=0:complete=False;break
            events.write(json.dumps({'event':'start','order':order,**item})+'\n');events.flush()
            result=observe_child([str(python),'-B','-c',ONE_CASE,str(Path(repo)/directory),item['name']],
                                 repo,env,profile,remaining)
            with (output/('case-%05d.log'%order)).open('xb') as f:f.write(result['output'])
            count,last=tolka(result['output'].decode('utf-8','replace'))
            status=('timeout' if result['timed_out'] else 'unknown' if result['output_limit_exceeded']
                    else 'success' if result['returncode']==0 and count==1 and last=='OK'
                    else 'skipped' if result['returncode']==0 and 'skipped=' in last else 'failure')
            row={'order':order,**item,'seconds':result['seconds'],'status':status}
            cases.append(row);events.write(json.dumps({'event':'stop',**row})+'\n');events.flush()
            log.write(item['name']+' ... '+('ok' if status=='success' else status)+'\n');log.flush()
        complete=complete and len(cases)==len(inventory)
        passed=complete and bool(cases) and all(r['status']=='success' for r in cases)
        wall=round(time.monotonic()-began,6)
        log.write('\nRan %d tests in %.6fs\n\n%s\n'%(len(cases),wall,'OK' if passed else 'FAILED (external observations incomplete or failed)'))
    return {'cases':cases,'returncode':0 if passed else 1,'timed_out':any(c['status']=='timeout' for c in cases),
            'wall_seconds':wall,'complete':complete,'test_count':len(cases),'last_line':'OK' if passed else 'FAILED',
            'case_timing_schema':2,'observation_kind':'external-process/1','protected_primary_files':True,
            'shared_interpreter_state':False}


def case_observations(path):
    """An interrupted start remains unknown; no time is invented for it."""
    rows = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        order = event['order']
        if type(order) is not int or order <= 0 or event['event'] not in ('start', 'stop'):
            raise Vagrar('invalid case timing event')
        if event['event'] == 'start':
            if order in rows:
                raise Vagrar('duplicate case start')
            rows[order] = {'order': order, 'name': event['name'], 'file': event.get('file'), 'seconds': None, 'status': 'unknown'}
        else:
            if order in rows and (rows[order]['name'] != event['name'] or rows[order]['status'] != 'unknown'):
                raise Vagrar('case stop differs from start')
            rows[order] = {k: event[k] for k in ('order', 'name', 'seconds', 'status')}
            rows[order]['file'] = event.get('file')
    if sorted(rows) != list(range(1, len(rows) + 1)):
        raise Vagrar('case order is incomplete')
    return list(rows.values())


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
    env = {}
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
        interpreter=plats.runtime/'.runtime/temporal-venv/bin/python' if profil['python']==VENV else profil['python']
        actual = ['fixed-external-observer', str(interpreter), profil['katalog']]
        observation=observe_suite(interpreter,profil['katalog'],repo,env,ut,profil['tid'],
                                  expected_count=begaran['expected_test_count'],owner_home=plats.agarhem)
        code,timed_out=observation['returncode'],observation['timed_out'];wall=observation['wall_seconds']
        log=(ut/'suite.log').read_bytes();count,last=tolka(log.decode('utf-8','replace'))
        status = git(['status', '--porcelain=v1', '--ignored', '--untracked-files=all'], repo, base)
        suite = {'schema': SVIT, 'candidate': head, 'tree': tree, 'command': command, 'actual_command': actual,
                 'cases': observation['cases'], 'observation_kind': observation['observation_kind'],
                 'protected_primary_files': observation['protected_primary_files'],
                 'shared_interpreter_state': observation['shared_interpreter_state'],
                 'case_observation_sha256': sha_fil(ut / 'cases.jsonl'), 'case_timing_schema': 2,
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
        if env.get('TMPDIR'):
            shutil.rmtree(env['TMPDIR'], ignore_errors=True)
        shutil.rmtree(str(arbete), ignore_errors=True)
    skriv(ut / 'klar.json', klar)
    return klar


def owner_document(plats, ident, name):
    """Fixed owner request filenames only; never caller-selected paths or code."""
    if name not in ('observation.json','stop.json') or not ID.fullmatch(ident):
        raise Vagrar('invalid owner protocol document')
    path=plats.inkorg/ident/name;owner=pwd.getpwnam(plats.agare).pw_uid
    info=path.lstat()
    if path.is_symlink() or not path.is_file() or info.st_uid!=owner or info.st_mode&0o022 or info.st_size>4*1024*1024:
        raise Vagrar('owner protocol document is not protected')
    acl=subprocess.run(['/bin/ls','-lde',str(path)],capture_output=True,env={'PATH':PATH,'LANG':'C','LC_ALL':'C'},timeout=10)
    if acl.returncode or any(' allow ' in line for line in acl.stdout.decode('utf-8','strict').splitlines()[1:]):
        raise Vagrar('owner protocol document has an unqualified ACL')
    data=json.loads(path.read_text())
    if not isinstance(data,dict):raise Vagrar('invalid owner protocol document')
    return data


def observed_source(plats, ident, need_manifest=False):
    request,_=las_begaran(plats,ident);plan=owner_document(plats,ident,'observation.json')
    fields={'schema','id','run','candidate','tree','files','names','manifest','program_sha256','observer_sha256','queue_sha256'}
    if (set(plan)!=fields or plan['schema']!='nortropic-observed-request/1' or plan['id']!=ident
        or not re.fullmatch('[0-9a-f]{32}',str(plan['run']))
        or plan['candidate']!=request['candidate'] or plan['tree']!=request['tree']
        or plan['program_sha256']!=sha_fil(plats.skript)
        or not all(re.fullmatch('[0-9a-f]{64}',str(plan[k])) for k in ('observer_sha256','queue_sha256'))
        or not isinstance(plan['files'],dict) or not plan['files'] or len(plan['files'])>10000
        or not isinstance(plan['names'],list) or len(plan['names'])>100
        or any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}',n) for n in plan['names'])):
        raise Vagrar('owner observation binding differs')
    source=plats.inkorg/ident/'source';owner=pwd.getpwnam(plats.agare).pw_uid
    total=0
    for name,digest in plan['files'].items():
        if (not isinstance(name,str) or name.startswith('/') or any(x in ('','.','..') for x in name.split('/'))
            or not re.fullmatch('[0-9a-f]{64}',str(digest))):raise Vagrar('invalid snapshot member')
        path=source/name
        for directory in (source,*list(path.parents)[:len(Path(name).parts)-1]):
            info=directory.lstat()
            if directory.is_symlink() or not directory.is_dir() or info.st_uid!=owner or info.st_mode&0o022:
                raise Vagrar('snapshot parent is not protected')
        info=path.lstat();total+=info.st_size
        if path.is_symlink() or not path.is_file() or info.st_uid!=owner or info.st_mode&0o022 or total>512*1024*1024:
            raise Vagrar('snapshot file is not protected or bounded')
        if sha_fil(path)!=digest:raise Vagrar('snapshot bytes differ')
    if need_manifest:
        rows=plan['manifest']
        if not isinstance(rows,list) or not rows or len(rows)>100000:raise Vagrar('test manifest missing')
        for index,row in enumerate(rows,1):
            if (not isinstance(row,dict) or set(row)!={'id','name','file'} or type(row['id']) is not int or row['id']!=index
                or not isinstance(row['name'],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,20}',row['name'])
                or row['file'] not in plan['files']):raise Vagrar('test manifest differs')
    return request,plan,source


def observed_launch(plats, ident, mode):
    """Fixed helper as test UID. Parent/owner owns every primary observation."""
    request,plan,source=observed_source(plats,ident,need_manifest=mode=='run')
    profile=PROFILER[request['repo']];work=plats.arbete/ident
    if mode=='prepare':
        for directory in (plats.arbete,plats.cache):directory.mkdir(mode=0o700,exist_ok=True)
        work.mkdir(mode=0o700);(work/'scratch').mkdir(mode=0o700)
        probe=gransprob(plats)
        print(json.dumps({'schema':'nortropic-owner-probe/1','id':ident,'run':plan['run'],'probe':probe}),flush=True)
        if not probe['kredentialfri']:return 3
        env=miljo(plats,profile,work,source,plats.inkorg/ident)
        # Short private paths outside repositories preserve Unix-socket fixtures.
        shutil.rmtree(env['TMPDIR']);env['TMPDIR']=tempfile.mkdtemp(prefix='nrm-',dir='/private/tmp')+'/'
        with (work/'gitconfig').open('a') as config:config.write('[safe]\n\tdirectory = '+str(source)+'\n')
        if profile['npm']:
            project=work/'npm';project.mkdir()
            for name in ('package.json','package-lock.json'):shutil.copyfile(source/profile['npm']/name,project/name)
            for argv in (['/opt/homebrew/bin/npm','ci','--no-audit','--no-fund'],
                         ['/opt/homebrew/bin/node','node_modules/playwright/cli.js','install','chromium','webkit']):
                result=subprocess.run(argv,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=sys.stderr,stderr=sys.stderr,timeout=900)
                if result.returncode:raise Vagrar('dependency preparation failed')
        skriv(work/'environment.json',env);(work/'environment.json').chmod(0o600)
    else:
        path=work/'environment.json';info=path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise Vagrar('test work environment is not private')
        env=json.loads(path.read_text())
        if not isinstance(env,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in env.items()):
            raise Vagrar('invalid work environment')
    interpreter=plats.runtime/'.runtime/temporal-venv/bin/python' if profile['python']==VENV else profile['python']
    command=[str(interpreter),'-B','-c',OWNER_EVENT_RUNNER,str(source),profile['katalog'],
             'inventory' if mode=='prepare' else 'run',str(plats.inkorg/ident/'observation.json')]
    child=subprocess.Popen(command,cwd=source,env=env,stdin=subprocess.DEVNULL,stdout=sys.stdout,stderr=sys.stderr,
                           close_fds=True,start_new_session=True)
    try:
        return child.wait(timeout=120 if mode=='prepare' else profile['tid'])
    finally:
        # These signals are sent by the SAME test UID, not by the owner. Parent
        # still verifies actual process absence independently before acceptance.
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:child.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait(timeout=10)


def observed_stop(plats, ident):
    """No PID arguments: only exact owner-written identities for this attempt."""
    request,_=las_begaran(plats,ident);plan=owner_document(plats,ident,'observation.json')
    stop=owner_document(plats,ident,'stop.json')
    if (set(stop)!={'schema','id','run','candidate','processes'} or stop['schema']!='nortropic-measurement-stop/1'
        or stop['id']!=ident or stop['run']!=plan.get('run') or stop['candidate']!=request['candidate']
        or not isinstance(stop['processes'],list) or len(stop['processes'])>1000):raise Vagrar('invalid stop binding')
    def alive(row):
        if (not isinstance(row,dict) or set(row)!={'pid','ppid','pgid','uid','started'}
            or any(type(row[k]) is not int or row[k]<0 for k in ('pid','ppid','pgid','uid'))
            or row['pid'] in (0,1,os.getpid()) or row['uid']!=os.getuid() or not isinstance(row['started'],str)):
            raise Vagrar('invalid stop process identity')
        r=subprocess.run(['/bin/ps','-p',str(row['pid']),'-o','pid=,ppid=,pgid=,uid=,lstart='],capture_output=True,
                         env={'PATH':PATH,'LANG':'C','LC_ALL':'C'},timeout=10)
        if r.returncode==1 and not r.stdout:return False
        if r.returncode:raise Vagrar('stop process identity unavailable')
        parts=r.stdout.decode().strip().split(None,4)
        return len(parts)==5 and parts[0]==str(row['pid']) and parts[2]==str(row['pgid']) and parts[3]==str(row['uid']) and parts[4]==row['started']
    for sig in (signal.SIGTERM,signal.SIGKILL):
        for row in stop['processes']:
            if alive(row):
                try:os.kill(row['pid'],sig)
                except ProcessLookupError:pass
        time.sleep(.2)
    return 1 if any(alive(row) for row in stop['processes']) else 0


def main(argv):
    os.umask(0o022)
    try:
        plats = Plats()
        os.chdir(str(plats.provhem))
        if argv[1:] == ['gransprob']:
            identitet(plats)
            value = gransprob(plats)
            plats.ut.mkdir(mode=0o755, exist_ok=True)
            skriv(plats.ut / ('gransprob-%s.json' % datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')), value)
            print(json.dumps(value, indent=2, ensure_ascii=False))
            return 0 if value['kredentialfri'] else 3
        if len(argv) == 3 and argv[1] in ('prepare','run','stop'):
            identitet(plats)
            info=plats.skript.lstat()
            if plats.skript.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
                raise Vagrar('observed operations require the installed root-owned fixed program')
            return observed_stop(plats,argv[2]) if argv[1]=='stop' else observed_launch(plats,argv[2],argv[1])
        if len(argv) == 3 and argv[1] == 'mat':
            identitet(plats)
            value = mat(plats, argv[2])
            print(json.dumps(value, indent=2, ensure_ascii=False))
            return 0 if value.get('returncode') == 0 and value.get('credential_free_execution') else 1
        raise Vagrar('usage: matning gransprob | matning prepare|run|stop ID; mat ID is legacy diagnostics')
    except (Vagrar, OSError, ValueError, KeyError) as error:
        print('VÄGRAR: %s' % error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
