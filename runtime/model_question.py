"""A concrete model-choice question to the owner when the selected model lacks capacity (D030).

Quota or access loss stays a persisted wait, and the host never switches model or executor by itself (D022). What this
adds is the question that wait lacked: which executor and which selected model were refused, in the provider's own
words, and the owner's two choices - wait, or change the model with the reviewed tool (D029) - with the exact commands
and the models this Runtime has qualified for that executor. One record per capacity event, never overwritten, under
the host's own records; the tool's `show` lists them.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .release import ROOT

# Qualified on the real non-interactive path, per executor, and where that is recorded. Information for the owner, not
# an allow-list: any plain model id stays selectable (D022), and a selectable model is not thereby a qualified one.
QUALIFIED = {'claude': {'claude-fable-5-1': 'D019', 'claude-opus-5': 'D022'},
             'codex': {'gpt-6-astra': 'D004, D028'}}
WORDS_BOUND = 600
TOOL = 'runtime/scripts/model_choice.py'


def home():
    return ROOT / '.runtime/ap10/model-questions'


def provider_words(provider, records):
    """What the provider said in the rows the capacity classifiers read, bounded; None when it said nothing there.

    Claude: its failed terminal's own text and HTTP status. Codex: its `error` rows' message and its `turn.failed` rows'
    error message (the exec event types of the pinned CLI). Agent text, usage counters and tool output are never read.
    """
    if provider == 'claude':
        rows = [e for e in records if e.get('type') == 'result' and e.get('is_error') is not False]
        parts = [str(e.get('result') or '') for e in rows] + ['HTTP %s' % e['api_error_status'] for e in rows if e.get('api_error_status')]
    else:
        parts = []
        for e in (e for e in records if e.get('type') in ('error', 'turn.failed')):
            error = e.get('error')
            parts.append(str(e.get('message') or (error.get('message') if isinstance(error, dict) else error) or ''))
    text = ' | '.join(p.strip() for p in parts if p and p.strip())
    return text[:WORDS_BOUND] or None


def question(executor, model, words, where, active, now):
    """The record itself, without writing it, so its words and choices can be checked on their own."""
    alternatives = {name: ref for name, ref in QUALIFIED.get(executor, {}).items() if name != model}
    python = ROOT / '.runtime/temporal-venv/bin/python'
    if active and TOOL in (active.get('files') or {}):
        tool = Path(active['directory']) / TOOL
        change = {'stage': '%s -B %s stage --%s <modell>' % (python, tool, executor),
                  'check': '%s -B %s check' % (python, tool), 'activate': '%s -B %s activate' % (python, tool)}
    else:
        change = 'Den aktiva releasen bär inte verktyget för modellbyte; ett byte kräver en kontrollerad kodövergång.'
    said = ' (leverantören: "%s")' % words if words else ''
    return {
        'asked_at': now.isoformat(), 'executor': executor, 'model': model, 'where': where, 'provider_said': words,
        'automatic_switch': False,
        'question': ('Vald modell %s för %s tar inte emot anrop%s. Runtime byter inte modell själv, och väntan består. '
                     'Vill du vänta, eller byta modell för %s?' % (model, executor, said, executor)),
        'choices': [
            {'choice': 'vänta', 'what': 'Gör ingenting nu. Väntan består; när kapaciteten är tillbaka fortsätter körningen på det '
                                        'sätt runbooken anger för den, utan ny budget och utan automatiskt nytt anrop.'},
            {'choice': 'byt modell', 'commands': change, 'qualified_alternatives': alternatives,
             'what': 'Ett byte gäller från aktiveringen för varje roll %s driver. Ett namn utanför listan är valbart men inte '
                     'kvalificerat.' % executor}],
        'not_a_choice': 'Köp av krediter, uppgraderingar, nya abonnemang eller andra betalvägar ingår inte, vad leverantören än föreslår.'}


def ask(executor, model, words, where, now=None):
    """Write one question and return its path relative to the host root. Changes nothing else."""
    from .release import installed
    now = now or datetime.now(timezone.utc)
    try:
        active = installed()
    except (OSError, ValueError, KeyError):
        active = None
    record = question(executor, model, words, where, active, now)
    directory = home(); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / ('%s-%s.json' % (now.strftime('%Y%m%dT%H%M%S%fZ'), executor))
    with path.open('x') as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False); stream.write('\n')
    return str(path.relative_to(ROOT))


def ask_safely(executor, model, records, where):
    """For a call that has already ended: a question that cannot be written is recorded as such, never raised."""
    try:
        return ask(executor, model, provider_words(executor, records), where)
    except Exception as error:
        return 'not written: %r' % error


def recent(limit=5):
    """The newest questions, newest first, as their records say them; unreadable ones are named, not skipped."""
    found = []
    for path in sorted(home().glob('2*Z-*.json'), reverse=True)[:limit]:
        try:
            found.append({'path': str(path.relative_to(ROOT)), **{k: v for k, v in json.loads(path.read_text()).items()
                                                                  if k in ('asked_at', 'executor', 'model', 'provider_said')}})
        except (OSError, ValueError):
            found.append({'path': str(path.relative_to(ROOT)), 'unreadable': True})
    return found
