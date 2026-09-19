"""Report provider execution from JSONL; this does not report task acceptance."""

import argparse
import json
import sys


CODEX_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")


def _reject_constant(value):
    """Python's NaN/Infinity extensions are not JSON."""
    raise ValueError(f"Invalid JSON constant: {value}")


def _events(lines):
    """Yield parsed JSON objects, or None for a malformed/non-object line."""
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line, parse_constant=_reject_constant)
        except ValueError:
            yield None
            continue
        yield event if isinstance(event, dict) else None


def _status(invalid, terminals, failed):
    """Invalid outranks failure, which outranks completion."""
    if invalid or terminals > 1:
        return "invalid"
    if failed:
        return "failed"
    if terminals:
        return "completed"
    return "incomplete"


def _summarize_codex(lines):
    """Summarize one Codex turn.

    Both turn.completed and turn.failed count as terminal events; error and
    failed items mark failure without counting as an additional terminal event.
    """
    usage = None
    terminals = 0
    failed = False
    invalid = False
    for event in _events(lines):
        if event is None:
            invalid = True
            continue
        kind = event.get("type")
        if kind in ("turn.completed", "turn.failed"):
            terminals += 1
        if kind == "turn.completed":
            reported = event.get("usage")
            # Never synthesize zeroes for missing usage or missing counters.
            if terminals == 1 and isinstance(reported, dict):
                usage = {key: reported.get(key) for key in CODEX_USAGE_KEYS}
        elif kind in ("turn.failed", "error"):
            failed = True
        elif kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("status") == "failed":
                failed = True

    return {"provider": "codex", "status": _status(invalid, terminals, failed),
            "usage": usage}


def _summarize_claude(lines):
    """Summarize one Claude stream-json run.

    Only a `result` event is terminal. It completes the run only when
    `is_error` is the JSON boolean false and `subtype` is "success". A true
    `is_error` or any non-success subtype is a failure even if the other field
    looks successful. A `success` subtype without an explicit boolean false
    `is_error`, or a result without a string subtype, is ambiguous and reported
    as invalid rather than completed. Usage and total_cost_usd are copied from
    the first result exactly as reported and are null when absent.
    """
    usage = None
    total_cost_usd = None
    terminals = 0
    failed = False
    invalid = False
    for event in _events(lines):
        if event is None:
            invalid = True
            continue
        if event.get("type") != "result":
            continue
        terminals += 1
        if terminals == 1:
            reported = event.get("usage")
            if isinstance(reported, dict):
                usage = dict(reported)
            total_cost_usd = event.get("total_cost_usd")

        is_error = event.get("is_error")
        subtype = event.get("subtype")
        if is_error is True or (isinstance(subtype, str) and subtype != "success"):
            failed = True
        elif is_error is False and subtype == "success":
            continue
        else:
            invalid = True

    return {"provider": "claude", "status": _status(invalid, terminals, failed),
            "usage": usage, "total_cost_usd": total_cost_usd}


def summarize(provider, lines):
    """Summarize one provider run from an iterable of JSONL strings.

    Returns a dict with provider, status (completed, failed, incomplete, or
    invalid) and usage; Claude reports also carry total_cost_usd. Statuses
    describe provider execution only, never review or task acceptance.
    """
    if provider == "codex":
        return _summarize_codex(lines)
    if provider == "claude":
        return _summarize_claude(lines)
    raise ValueError(f"Unsupported provider: {provider}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("codex", "claude"))
    parser.add_argument("path", metavar="PATH", help="UTF-8 JSONL run log")
    args = parser.parse_args(argv)
    try:
        with open(args.path, encoding="utf-8") as lines:
            result = summarize(args.provider, lines)
    except (OSError, UnicodeError) as exc:
        print(f"run_report: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
