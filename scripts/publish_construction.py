"""Protected publication of ONE separately reviewed construction candidate (v5).

usage:  <runtime venv python> -B publish_construction.py NAME EXPECTED_TEST_COUNT [--dry-run]

Every control is an explicit refusal (never `assert`), and optimized interpreter mode
is refused. Nothing is taken from an argument or a file name alone:
  * target repository, worktree location and suite command come from historical profiles
    or an immutable host-issued accepted-task registration; no candidate argument selects a target;
  * the candidate is the manifest's exact commit, re-checked against live Git objects;
  * the whole suite's credential-free measurement is sealed by the independent
    holder for exactly that commit/tree and re-read here; raw log/return code/count
    are bound. This credential-bearing wrapper executes no candidate host tests;
  * the review receipt must approve exactly this commit and exactly these blob hashes;
  * for runtime candidates, the host-check receipt must record a complete green run of the separate host
    checks on exactly this commit, these bytes and code imported from this candidate, against this host's
    own preserved scope at its current journal head; it is pinned in the preview and the invocation record;
  * the EXISTING Publisher is imported from the primary checkout, which must be
    byte-identical to integrated main; its gates, branch-protection readback, exact-head
    squash merge and remote reconciliation are used unchanged.
--dry-run validates the sealed suite and every local check, stopping before Publisher. A real run
refuses unless the newest dry run of the same name previewed identical hashes and count.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

# Direct script invocation must resolve this checkout before any runtime import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUNTIME_REPO = 'Nortropic/nortropic-runtime'
OFFICE_REPO = 'Nortropic/nortropic-projektkontor'
# Fixed per exact candidate name. 'where' selects the worktree home and interpreter; 'discover'
# is the repository's test directory, run as ONE whole suite (the office documents the same
# pattern per tool). Nothing here is taken from the command line.
PROFILES = {
    'ap11-claude-roles': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-claude-driver': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-office-executors': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap11-goal-amendment': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-history-bound': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-pause-wait': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-daemon-history': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-discoverability': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-office-discoverability': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap11-contract': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-office-contract': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap11-host-recovery': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-prompt-delivery': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-model-binding': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-final-evidence': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-assessment-path': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-hostcheck-binding': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-assessment-start': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-final-review-recipes': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-third-assessment': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-g6-examination': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-guardian-signal': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-final-review-room': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'ap11-plan-closed': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-result-test-case': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-closure-entry': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'modellval-codex-chain': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'modellval-model-choice': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'modellval-question': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-modellval-progress': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'modellval-plan-active': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-modellval-active': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'modellval-plan-switch': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-modellval-switch': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap10-registration': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-ap10-aquarium-registration': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap10-stage-signal': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-aquarium-byggbeslut': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'ap10-signal-active': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-ap10-signal-leverans': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aterfunnet-underlag': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'maintenance-aterfunnet-uppdrag': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-protokoll-ingang': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'maintenance-protokoll-ingang': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-aquarium-accept': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-arbetsform': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-projektion': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-indata-scenmall': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-gestaltning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-arbetsvarld': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-scenmall': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-scen-3': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-indata-scen': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-scenmall-fonster': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-fonster-2': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-indata-fonster': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-etapp3-plan': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-agarprov': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-agarprov-rattelse': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-runtime-granskningsbudget-beredning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-runtime-granskningsbudget-accept': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'runtime-granskningsbudget': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-runtime-granskningstid-kontor': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-agarprov-godkant': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-beredning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-komplettering': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-aquarium-leverans': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-runtime-steg2-plan': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-anvandningsprov-underlag': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'runtime-granskningsbudget-aktiv': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-kontor-stang': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-accept': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-korrigering': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-brief': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-leverans': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-grenar': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-riktad': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-riktad-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-jamforelse': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-jamforelse-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-precisering': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-precisering-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-genomforande': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-kunskapsstod': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-genomforande-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-riktning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-riktning-besked': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-tillaggsmandat-beslut': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-overblick-obsidian': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-etapp1-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-inventering-tillagg': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-inventering-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-etapp2-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-forvaltningar-lopande-utveckling': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-inventering-tillagg-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-forvaltningar-beslut': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-forvaltningar-beslut3': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'runtime-webbprofiler': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-runtime-profiler': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-etapp3-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-agarbeslut': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-etapp4-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-digitala-agarbedomning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'runtime-matprofil-parametrar': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-ombyggnad': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-ap06-forvaltning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-ombyggnad-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'runtime-overgang-18-aktiv': {'target': RUNTIME_REPO, 'where': 'runtime', 'discover': 'scripts'},
    'office-overgang-18-aktiv': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-agarsvar': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-helhet-registrering': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-helhet-beredning': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-helhet-etapp1': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-helhet-resultat': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-helhet-forslag': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
    'office-kundstart-registrering': {'target': OFFICE_REPO, 'where': 'office', 'discover': 'tools'},
}


def refuse(message):
    raise SystemExit('REFUSED: ' + message)


if sys.flags.optimize:
    refuse('optimized interpreter mode is not accepted')
arguments = [a for a in sys.argv[1:] if a != '--dry-run']
dry_run = '--dry-run' in sys.argv[1:]
if len(arguments) != 2 or sys.argv[1:].count('--dry-run') > 1 or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', arguments[0]) \
        or not re.fullmatch('[1-9][0-9]{0,4}', arguments[1]):
    refuse('usage: NAME EXPECTED_TEST_COUNT [--dry-run]')
name, expected = arguments[0], int(arguments[1])
# Historical exact names remain compatible. New work resolves only a sealed
# host-issued mandate registration, never candidate prose or a target argument.
if name in PROFILES:
    PROFILE = PROFILES[name]
else:
    try:
        from runtime.construction_registration import resolve_profile
        PROFILE = resolve_profile(name)
    except (OSError, ValueError, KeyError, ImportError) as error:
        refuse('unregistered or invalid accepted construction task: ' + type(error).__name__)
TARGET = PROFILE['target']

from runtime.release import ROOT as root
build = root / '.runtime/ap11/build'
# This tracked wrapper is invoked from an integrated checkout; candidate-local
# copies may only dry-run. Publication still imports the primary Publisher.
wrapper = Path(__file__).resolve()
if not dry_run and wrapper != root / 'scripts/publish_construction.py':
    refuse('publication wrapper must be the primary integrated copy')
os.chdir(root); sys.path.insert(0, str(root))
for variable in ('PYTHONOPTIMIZE', 'PYTHONPATH', 'PYTHONHOME'):
    os.environ.pop(variable, None)


def git(where, *args, raw=False):
    try:
        out = subprocess.run(['git', '-C', str(where), *args], check=True, capture_output=True, timeout=60).stdout
    except subprocess.CalledProcessError:
        refuse('required integrated Git object is unavailable; bootstrap is a separate reviewed holder transition')
    return out if raw else out.decode().rstrip('\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


# The existing Publisher, pinned to the bytes integrated on main.
import runtime.integration as integration  # noqa: E402
module = Path(integration.__file__).resolve()
if module != root / 'runtime/integration.py':
    refuse('Publisher was not imported from the primary checkout: ' + str(module))
publisher_sha = sha(module.read_bytes())
if publisher_sha != sha(git(root, 'show', 'refs/remotes/origin/main:runtime/integration.py', raw=True)):
    refuse('primary checkout Publisher differs from integrated main')
if not dry_run:
    for rel in ('scripts/publish_construction.py', 'runtime/construction_registration.py'):
        if sha((root / rel).read_bytes()) != sha(git(root, 'show', 'refs/remotes/origin/main:' + rel, raw=True)):
            refuse('publication holder differs from integrated main: ' + rel)

for required in ('-candidate.json', '-acceptance.txt', '-reviewer.json'):
    if not (build / (name + required)).is_file():
        refuse('missing ' + name + required + '; nothing is published without manifest, acceptance and review receipt')
candidate = json.loads((build / (name + '-candidate.json')).read_text())
if PROFILE.get('mandate_sha256') and (candidate.get('mandate_sha256') != PROFILE['mandate_sha256']
        or candidate.get('registration_sha256') != PROFILE['registration_sha256']):
    refuse('candidate is not bound to its registered accepted task')
accept = (build / (name + '-acceptance.txt')).read_text().strip()
reviewed = json.loads((build / (name + '-reviewer.json')).read_text())
path = Path(candidate['path']).resolve()
office = root.parent / 'nortropic-projektkontor'
home = (root / '.runtime/ap11/integrations' if PROFILE['where'] == 'runtime'
        else office / 'evidence/ap11/local')
if path.parent != home or not accept or (PROFILE['where'] == 'office' and not path.name.startswith('integration-')):
    refuse('candidate worktree or acceptance text is not where construction candidates live')
scratch = path / '.scratch'   # the office suite keeps its own temporary fixtures here
if PROFILE['where'] == 'office' and (not scratch.is_dir() or scratch.is_symlink() or any(scratch.iterdir())):
    refuse('office suite needs an existing EMPTY untracked .scratch directory')
head, base = candidate['candidate'], candidate['base']
for value in (head, base):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        refuse('exact 40-hex identities required')


def exact_candidate(moment):
    if git(path, 'rev-parse', 'HEAD') != head:
        refuse('worktree HEAD is not the recorded candidate ' + moment)
    if git(path, 'status', '--porcelain'):
        refuse('worktree is not clean ' + moment)


exact_candidate('before the suite')
if git(path, 'rev-list', '--parents', '-n', '1', head).split() != [head, base]:
    refuse('candidate is not exactly one commit on the recorded base')
changed = sorted(p for p in git(path, 'diff', '--no-renames', '--name-only', base, head).split('\n') if p)
if changed != sorted(candidate['files']) or not changed:
    refuse('manifest paths differ from the commit')
for rel, recorded in candidate['files'].items():
    if sha(git(path, 'show', head + ':' + rel, raw=True)) != recorded:
        refuse('manifest hash differs from the Git object: ' + rel)
if (reviewed.get('verdict') != 'approved' or reviewed.get('blocking_findings') != []
        or reviewed.get('candidate') != head or reviewed.get('source_sha256') != candidate['files']):
    refuse('review receipt does not approve exactly this commit and these bytes')
for field in ('reviewer_run', 'actual_reviewer', 'limitations'):
    if not isinstance(reviewed.get(field), str) or not reviewed[field].strip():
        refuse('review receipt lacks ' + field)
if reviewed['reviewer_run'] == candidate.get('implementation_run') or not candidate.get('implementation_run'):
    refuse('reviewer run must differ from the implementation run')

# Three receipt fields are published VERBATIM: reviewer_run in the Publisher's PR body, the
# other two in a public PR comment. Refuse, before anything is measured or published, text
# that could disclose private material or notify/link. A second net, NOT proof of absence:
# each receipt is read and attested by its own reviewer, and the dry run prints the exact note.
MARK = 'Host note on this construction integration.'
if not re.fullmatch('[a-z0-9][a-z0-9-]{0,119}', reviewed['reviewer_run']):
    refuse('review receipt field reviewer_run is not a plain label')
for field in ('limitations', 'actual_reviewer'):
    text = reviewed[field]
    if (len(text) > 3000 or re.search(r'(/Users/|/private/|/var/|/tmp/|/opt/|~/|[A-Za-z]:\\|\.runtime/|evidence/)', text) or '@' in text
            or re.search(r'https?://|www\.', text, re.I) or re.search(r'#\d|GH-\d', text, re.I)
            or any(ord(ch) < 32 or ord(ch) > 126 for ch in text)):
        refuse('review receipt field %s is not safe to publish verbatim (path, @, link, reference, non-printable or non-ASCII character, or too long)' % field)


def note_body(test_count):
    return (MARK + ' Review limitation, exactly as recorded in the review receipt for this candidate: '
            + reviewed['limitations'] + ' Reviewer as recorded there: ' + reviewed['actual_reviewer']
            + ' A credential-free whole-suite measurement (%s tests) is sealed for this exact candidate. '
              'The issuer executes its frozen acceptance before publication. This integration activates nothing.' % test_count)

# Read the holder's exact measured suite. A candidate-selected log or count proves nothing.
environment = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR')}
environment['PYTHONDONTWRITEBYTECODE'] = '1'
interpreter = (str(root / '.runtime/temporal-venv/bin/python') if PROFILE['where'] == 'runtime'
               else '/opt/homebrew/bin/python3.12')
from runtime.check_issuer import sealed_construction_suite
suite = sealed_construction_suite(path, head, PROFILE['discover'], name, expected)
log = suite.stdout.decode(errors='replace')
exact_candidate('after the suite')
if PROFILE['where'] == 'office' and (not scratch.is_dir() or scratch.is_symlink() or any(scratch.iterdir())):
    refuse('office suite removed .scratch or left files in it')
ran = re.findall(r'^Ran (\d+) tests? in ', log, re.M)
lines = [line for line in log.splitlines() if line.strip()]
if suite.returncode != 0 or len(ran) != 1 or not lines or lines[-1] != 'OK':
    refuse('suite on the exact candidate is not green (return code %s, summary %r)' % (suite.returncode, lines[-1:] ))
if int(ran[0]) != expected:
    refuse('suite ran %s tests, expected %s' % (ran[0], expected))
# The suite above is ONE discovery run over the profile's directory, and checks that need the preserved
# application are deliberately outside its pattern - a skip inside it would be indistinguishable from a check
# that quietly stopped running. Independent review found the consequence: nothing gated on those checks, so a
# green publication said nothing about whether they had ever run. For runtime candidates their receipt is now
# a gate, bound to this exact commit and to the bytes it names.
HOST_RECEIPT_SHA = None
if PROFILE['where'] == 'runtime':
    host_receipt = build / (name + '-hostcheck.json')
    if not host_receipt.is_file():
        refuse('no host-check receipt for this candidate; run scripts/run_host_checks.py against the '
               'checkout holding the preserved application and write it to ' + str(host_receipt))
    raw_receipt = host_receipt.read_bytes()   # hashed and parsed from the SAME bytes
    HOST_RECEIPT_SHA = sha(raw_receipt)
    host = json.loads(raw_receipt)
    if host.get('module') != 'scripts.hostcheck_preserved_state':
        refuse('host-check receipt is not about the host-check module: ' + repr(host.get('module')))
    if host.get('candidate') != head:
        refuse('host-check receipt is for %r, not the candidate %r' % (host.get('candidate'), head))
    if host.get('clean_tree') is not True:
        refuse('host-check receipt was taken with an unclean tree')
    if (host.get('successful') is not True or host.get('skipped') or host.get('failures')
            or host.get('errors') or not isinstance(host.get('run'), int) or host['run'] < 1):
        refuse('host-check receipt does not record a complete green run: ' + json.dumps(
            {k: host.get(k) for k in ('run', 'failures', 'errors', 'skipped', 'successful')}))
    # EXACTLY the bound files, not whatever keys the receipt chose to supply: an empty or trimmed map
    # would otherwise satisfy the loop by having nothing to disagree with.
    bound = {'scripts/hostcheck_preserved_state.py', 'scripts/test_final_evidence.py'}
    recorded = host.get('source_sha256')
    if not isinstance(recorded, dict) or set(recorded) != bound:
        refuse('host-check receipt must name exactly %s; it names %r' % (sorted(bound), sorted(recorded or {})))
    for rel, expected_sha in recorded.items():
        blob = subprocess.run(['git', '-C', str(path), 'show', head + ':' + rel],
                              capture_output=True, check=True).stdout
        if sha(blob) != expected_sha:
            refuse('host-check receipt names %s at a different content than this candidate carries' % rel)
    # The bytes say what should have run; the import map says what the interpreter actually loaded. The
    # module and its base-class file must come from exactly this candidate, and nothing it loaded from
    # runtime/ or scripts/ may come from anywhere else.
    imported = host.get('imported')
    if (not isinstance(imported, dict)
            or any(not isinstance(f, str) or Path(f) != Path(f).resolve() or not Path(f).is_relative_to(path)
                   for f in imported.values())
            or any(imported.get(rel[:-3].replace('/', '.')) != str(path / rel) for rel in bound)):
        refuse('host-check receipt does not show the checks importing this candidate code: ' + repr(imported))
    # The preserved scope is THIS host's own: the one under the publisher's root, which the checks themselves
    # verify against the accepted active binding. It is not whichever directory the receipt says it ran
    # against - a run against a copy names the copy, and reading the copy's own head would only confirm the copy.
    own_scope = root / '.runtime/ap11/application'
    if host.get('scope') != str(own_scope):
        refuse('host-check receipt ran against %r, not this host scope %s' % (host.get('scope'), own_scope))
    if not isinstance(host.get('host_root'), str) or Path(host['host_root']).resolve() != root:
        refuse('host-check receipt names the host root %r, not this host %s' % (host.get('host_root'), root))
    own_head = own_scope / 'head.json'
    if not own_head.is_file() or host.get('journal_head') != json.loads(own_head.read_text()):
        refuse('host-check receipt records a journal head that is not this scope current head')

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
log_path = build / ('%s-publication-suite-%s%s.log' % (name, stamp, '-dryrun' if dry_run else ''))
with log_path.open('x') as stream:
    stream.write(log)

task = {'id': name, 'target': TARGET, 'base': base, 'allowed_paths': changed,
        'steps': [{'provider': 'claude', 'prompt': accept}], 'acceptance_sha256': sha(accept.encode())}
subject = {'task_id': name, 'task_sha256': integration.digest(task), 'base': base, 'candidate': head,
           'completed_steps': [0], 'acceptance_sha256': task['acceptance_sha256'],
           'implementation_runs': [candidate['implementation_run']]}
bound = {k: subject[k] for k in ('task_id', 'task_sha256', 'candidate', 'acceptance_sha256')}
bound.update(scope='whole_task', terminal_status='completed')
tests = {**bound, 'passed': True, 'test_count': int(ran[0]), 'returncode': suite.returncode,
         'log_sha256': sha(log.encode()), 'log': log_path.name,
              'measured_by': 'credential-free whole suite; exact sealed host measurement read by publication wrapper'}
review = {**bound, 'verdict': 'approved', 'blocking_findings': [], 'reviewer_run': reviewed['reviewer_run'],
          'actual_reviewer': reviewed['actual_reviewer'], 'source_sha256': reviewed['source_sha256'],
          'limitations': reviewed['limitations']}
integration.require_gate(task, subject, tests, review)
invocation = {'observed_at': datetime.now(timezone.utc).isoformat(), 'argv': sys.argv, 'dry_run': dry_run,
              'interpreter': sys.executable, 'optimize': sys.flags.optimize, 'target': TARGET, 'base': base,
              'candidate': head, 'tree': git(path, 'rev-parse', head + '^{tree}'),
              'wrapper_sha256': sha(Path(__file__).read_bytes()), 'publisher_sha256': publisher_sha,
              'manifest_sha256': sha((build / (name + '-candidate.json')).read_bytes()),
              'reviewer_receipt_sha256': sha((build / (name + '-reviewer.json')).read_bytes()),
              'acceptance_sha256': task['acceptance_sha256'],
              'hostcheck_receipt_sha256': HOST_RECEIPT_SHA,
              'public_note_sha256': sha(note_body(tests['test_count']).encode()), 'suite': {k: tests[k] for k in ('test_count', 'returncode', 'log_sha256', 'log')}}
PREVIEWED = ('wrapper_sha256', 'publisher_sha256', 'manifest_sha256', 'reviewer_receipt_sha256', 'acceptance_sha256',
             'public_note_sha256', 'candidate', 'base', 'tree', 'target', 'hostcheck_receipt_sha256')
if not dry_run:
    # Publish only what the NEWEST dry run previewed: same wrapper, receipt, manifest, candidate,
    # measured count and therefore exactly the same public note.
    previews = sorted(build.glob(name + '-publication-invocation-*-dryrun.json'))
    if not previews or previews[-1].is_symlink():
        refuse('no dry-run preview exists for this name; run --dry-run first')
    preview = json.loads(previews[-1].read_text())
    if (any(preview.get(key) != invocation[key] for key in PREVIEWED)
            or (preview.get('suite') or {}).get('test_count') != tests['test_count']):
        refuse('the newest dry-run preview differs from this run; preview again before publishing')
    invocation['preview'] = previews[-1].name
with (build / ('%s-publication-invocation-%s%s.json' % (name, stamp, '-dryrun' if dry_run else ''))).open('x') as stream:
    json.dump(invocation, stream, indent=2); stream.write('\n')
if dry_run:
    print('EXACT PUBLIC NOTE THAT WOULD BE POSTED ON THE PR:\n' + note_body(tests['test_count']) + '\n')
    print(json.dumps({'dry_run': True, 'would_publish': head, 'public_note_sha256': invocation['public_note_sha256'], 'on_base': base, 'to': TARGET, **invocation['suite'],
                      'gate': 'require_gate passed locally; Publisher NOT called; no remote access'}, indent=2))
    raise SystemExit(0)

for label, value in (('task', task), ('subject', subject), ('tests', tests), ('review', review)):
    (build / (name + '-' + label + '.json')).write_text(json.dumps(value, indent=2) + '\n')
os.environ.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='credential.helper',
                  GIT_CONFIG_VALUE_0='', GIT_CONFIG_KEY_1='credential.helper',
                  GIT_CONFIG_VALUE_1='!gh auth git-credential')
publisher = integration.Publisher(path, TARGET)
receipt = publisher.publish(task, subject, tests, review)
(build / (name + '-integration.json')).write_text(json.dumps(receipt, indent=2) + '\n')
# The Publisher's fixed public text says "independent review". State the ACTUAL limitation publicly,
# taken from this candidate's own review receipt (never a fixed claim about who reviewed).
note = {'posted': False}
try:
    number = str(receipt['url']).rsplit('/', 1)[1]
    existing = publisher.api('issues/' + number + '/comments?per_page=100')
    if any(isinstance(c, dict) and str(c.get('body', '')).startswith(MARK) for c in existing):
        note = {'posted': False, 'already_present': True}   # a re-run that only reconciles must not duplicate it
    else:
        publisher.api('issues/' + number + '/comments', 'POST', {'body': note_body(tests['test_count'])})
        note = {'posted': True}
except Exception as error:  # the integration receipt stands; a missing note is reported, not hidden
    note = {'posted': False, 'error': type(error).__name__, 'detail': str(error)[:300]}
(build / (name + '-limitation-note.json')).write_text(json.dumps(note, indent=2) + '\n')
print(json.dumps({'integration': receipt, 'limitation_note': note}, indent=2))
