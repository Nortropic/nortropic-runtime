"""Independent review protocol; host binds subject identities, never model echoes."""
import json
from pathlib import Path
from .integration import GateClosed, require_gate


def recovery_kind(task, subject, tests, review):
    """A missing/invalid review is not evidence that implementation is defective."""
    if (not isinstance(review, dict) or review.get('verdict') != 'rejected'
            or not isinstance(review.get('blocking_findings'), list)
            or not review['blocking_findings']
            or not all(isinstance(x, str) and x.strip() for x in review['blocking_findings'])
            or not isinstance(review.get('summary'), str) or not review['summary'].strip()):
        return 'review_only'
    try:
        # Check all subject, test and independence requirements without pretending
        # the rejection approved publication. This copy is never published.
        require_gate(task, subject, tests, {**review, 'verdict': 'approved', 'blocking_findings': []})
    except (GateClosed, TypeError, KeyError):
        return 'review_only'
    return 'repair'

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'verdict': {'type': 'string', 'enum': ['approved', 'rejected', 'inconclusive']},
        'blocking_findings': {'type': 'array', 'items': {'type': 'string'}},
        'summary': {'type': 'string'},
    },
    'required': ['verdict', 'blocking_findings', 'summary'],
}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate review JSON key: ' + key)
        result[key] = value
    return result


def claude_response(events):
    """The verdict is only the single native terminal's structured output.

    Assistant prose, a partial stream or an interrupted run never carries one.
    Measured with the pinned CLI: the terminal repeats the object as JSON text;
    a differing repeat is a conflict, not a choice between two verdicts.
    """
    terminals = [e for e in events if isinstance(e, dict) and e.get('type') == 'result']
    if (len(terminals) != 1 or terminals[0].get('is_error') is not False
            or terminals[0].get('subtype') != 'success' or terminals[0].get('terminal_reason') != 'completed'):
        raise ValueError('Missing review response')
    result = terminals[0].get('structured_output')
    if not isinstance(result, dict): raise ValueError('Missing review response')
    # Any other shape than the measured exact repeat is unqualified and fails closed.
    text = terminals[0].get('result')
    if not isinstance(text, str) or json.loads(text, object_pairs_hook=strict_object) != result:
        raise ValueError('Conflicting structured review response')
    return result


def verdict(events_path, provider='codex'):
    if provider == 'claude':
        # Duplicate keys at any depth could hide a second verdict behind last-wins decoding.
        result = claude_response([json.loads(line, object_pairs_hook=strict_object)
                                  for line in Path(events_path).read_text().splitlines()])
        return validated(result)
    if provider != 'codex': raise ValueError('Unsupported review provider')
    messages = []
    for line in Path(events_path).read_text().splitlines():
        event = json.loads(line)
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            messages.append(item.get('text'))
    if not messages or not isinstance(messages[-1], str): raise ValueError('Missing review response')
    return validated(json.loads(messages[-1], object_pairs_hook=strict_object))


def validated(result):
    if (not isinstance(result, dict) or set(result) != set(SCHEMA['required'])
            or result['verdict'] not in ('approved', 'rejected', 'inconclusive')
            or not isinstance(result['blocking_findings'], list)
            or not all(isinstance(x, str) and x.strip() for x in result['blocking_findings'])
            or not isinstance(result['summary'], str) or not result['summary'].strip()):
        raise ValueError('Invalid or unjudgeable review response')
    if result['verdict'] == 'approved' and result['blocking_findings']:
        raise ValueError('Conflicting approval with blocking findings')
    return result
