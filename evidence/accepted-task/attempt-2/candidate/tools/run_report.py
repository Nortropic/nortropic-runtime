"""Report provider execution from JSONL; this does not report task acceptance."""

import argparse
import json
import sys


def _reject_constant(value):
    """Python's NaN/Infinity extensions are not JSON."""
    raise ValueError(f"Invalid JSON constant: {value}")


def summarize(provider, lines):
    """Summarize one Codex turn from an iterable of JSONL strings.

    Invalid input outranks failure, which outranks completion. Both
    turn.completed and turn.failed count as terminal events; error and failed
    items mark failure without counting as an additional terminal event.
    Claude parsing is deliberately left for the next executor.
    """
    if provider == "claude":
        raise NotImplementedError("Claude reporting is not implemented yet")
    if provider != "codex":
        raise ValueError(f"Unsupported provider: {provider}")

    usage = None
    terminals = 0
    failed = False
    invalid = False
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line, parse_constant=_reject_constant)
        except ValueError:
            invalid = True
            continue
        if not isinstance(event, dict):
            invalid = True
            continue

        kind = event.get("type")
        if kind in ("turn.completed", "turn.failed"):
            terminals += 1
        if kind == "turn.completed":
            reported = event.get("usage")
            # Never synthesize zeroes for missing usage or missing counters.
            if terminals == 1 and isinstance(reported, dict):
                usage = {
                    key: reported.get(key)
                    for key in ("input_tokens", "cached_input_tokens", "output_tokens")
                }
        elif kind in ("turn.failed", "error"):
            failed = True
        elif kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("status") == "failed":
                failed = True

    if invalid or terminals > 1:
        status = "invalid"
    elif failed:
        status = "failed"
    elif terminals:
        status = "completed"
    else:
        status = "incomplete"
    return {"provider": provider, "status": status, "usage": usage}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("codex", "claude"))
    parser.add_argument("path", metavar="PATH", help="UTF-8 JSONL run log")
    args = parser.parse_args(argv)
    if args.provider == "claude":
        parser.error("Claude reporting is not implemented yet")
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
