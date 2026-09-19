# Provider run report — candidate Codex phase

Contract: [TASK.md](../TASK.md). `run_report.py` uses only the Python standard
library. `summarize(provider, lines)` consumes JSONL strings and returns
`provider`, `status`, and `usage`. It reports provider execution only; completion
does not imply review or task acceptance.

```sh
python3 tools/run_report.py --provider codex PATH
python3 -B -m unittest discover -s tools -p 'test_*.py' -v
```

The CLI reads UTF-8 and emits one JSON object for a readable log. Exit codes are
0 for completed, 1 for failed/incomplete/invalid, and 2 for argument or file errors
(including decoding errors), which produce stderr diagnostics instead of JSON.
It does not modify the input or create report files.

Codex behavior implemented:

- One `turn.completed` completes a run unless a failure was reported. Usage keeps
  the exact reported `input_tokens`, `cached_input_tokens`, and `output_tokens`.
  Absent usage is null; absent counters within a usage object are null.
- `turn.failed`, `error`, and `item.completed` with `item.status=failed` record
  failure. A later completion cannot erase an error or failed item.
- Both `turn.completed` and `turn.failed` are terminal events. Any second terminal
  makes the log invalid, including failed followed by completed. Errors and failed
  items do not themselves add to that count.
- Malformed/non-object JSON or duplicate terminal events take precedence over
  failure and completion. Blank lines and unknown event types are ignored.
  No terminal and no failure means incomplete.
- Usage comes from the first terminal only if it is a completion with a usage
  object. Invalid reports may retain that usage as evidence; it is not aggregated
  across multiple turns. Non-object usage is treated as unavailable.

Tests cover status precedence, all terminal pairs, exact and absent usage,
malformed input before/after terminal events, generators, and subprocess CLI
output, exit codes, determinism, and input preservation.

Validation in this candidate: all 15 tools tests and all 6 existing operator
support tests passed with `/opt/homebrew/bin/python3.12`. Both suites ran with
`-B`, `PYTHONDONTWRITEBYTECODE=1`, and `TMPDIR="$PWD/.scratch"` to keep temporary
test writes isolated. Git whitespace checks passed, including checks of the
three new files. The system Python/Git launchers lack developer tools here;
existing Homebrew executables were used without installing anything.

Next action: the next executor implements the Claude phase from TASK.md in these
same allowed files. The current API raises `NotImplementedError` for Claude;
the CLI explicitly rejects it with exit 2. Replace these temporary guards and
their tests with substantive Claude parsing and tests: a `result` is terminal,
success requires explicit `is_error=false` plus `subtype=success`, errors override
success, and usage/cost stay as reported. Include the `subtype=success` plus
`is_error=true` regression and duplicate/missing result cases. No live provider
access is needed to implement these deterministic parsers.

After Claude's continuation, the final Codex phase verifies both parsers and CLI
and updates this handoff. Frozen acceptance tests and separate review remain
external. This candidate has not been committed, published, or accepted.
