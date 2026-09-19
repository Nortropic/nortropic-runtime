# Provider run report

Contract: [accepted task](../tasks/run-report-complete.md). `run_report.py` uses only the Python standard
library. `summarize(provider, lines)` consumes JSONL strings and returns
`provider`, `status`, and `usage`; Claude reports also carry `total_cost_usd`.
It reports provider execution only; completion does not imply review or task
acceptance.

```sh
python3 tools/run_report.py --provider codex PATH
python3 tools/run_report.py --provider claude PATH
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.scratch" \
  python3 -B -m unittest discover -s tools -p 'test_*.py' -v
```

Run from the repository root; quote paths containing spaces. Tests need an
existing writable `.scratch` directory (provided in the candidate workspace).
For example, a Claude result with `subtype: success`, `is_error: false`, usage
`{"input_tokens": 4}` and `total_cost_usd: 0.0523` produces:

```json
{"provider": "claude", "status": "completed", "total_cost_usd": 0.0523, "usage": {"input_tokens": 4}}
```

The CLI reads UTF-8 and emits one JSON object for a readable log. Exit codes are
0 for completed, 1 for failed/incomplete/invalid, and 2 for argument or file errors
(including decoding errors), which produce stderr diagnostics instead of JSON.
It does not modify the input or create report files.

Shared rules for both providers: malformed or non-object JSON lines make the
report invalid, as does more than one terminal event. Invalid outranks failed,
which outranks completed. No terminal event and no failure means incomplete.
Blank lines and unknown event types are ignored. Usage is never invented; absent
usage stays null.
Nonstandard `NaN`/`Infinity`, numbers that overflow Python's finite float range
(such as `1e400`), and input exceeding the JSON decoder's nesting limit make the
report invalid. The offending line is discarded; other valid terminal evidence
may still be retained. These cases produce JSON and exit 1 without a traceback.

Codex behavior:

- One `turn.completed` completes a run unless a failure was reported. Usage keeps
  the exact reported `input_tokens`, `cached_input_tokens`, and `output_tokens`.
  Absent usage is null; absent counters within a usage object are null.
- `turn.failed`, `error`, and `item.completed` with `item.status=failed` record
  failure. A later completion cannot erase an error or failed item.
- Both `turn.completed` and `turn.failed` are terminal events. Any second terminal
  makes the log invalid, including failed followed by completed. Errors and failed
  items do not themselves add to that count.
- Usage comes from the first terminal only if it is a completion with a usage
  object. Invalid reports may retain that usage as evidence; it is not aggregated
  across multiple turns. Non-object usage is treated as unavailable.
- The Codex report keeps exactly three keys; it gains no cost field.

Claude stream-json behavior:

- Only `type: result` is terminal. Every other event type, including `system`,
  `assistant`, `user`, and a bare `error`, is ignored for status.
- Completed requires `is_error` to be the JSON boolean `false` **and**
  `subtype` to be `success`. `is_error: true` is failed even when the subtype
  says `success` (the real-log regression). Any string subtype other than
  `success` (for example `error_during_execution`, `error_max_turns`) is failed
  regardless of `is_error`.
- A `success` subtype whose `is_error` is missing, null, a string, a number, or
  anything other than boolean `false` is reported as invalid, never completed.
  A result without a string subtype is likewise invalid unless `is_error` is
  true, which is failed. This is the conservative classification the host
  clarification allows.
- Missing result is incomplete. A second `result` makes the log invalid.
- `usage` is a shallow copy of the reported usage object, unchanged and with all
  keys kept (Claude's cache counters and nested fields included). Non-object
  usage is treated as unavailable. `total_cost_usd` is returned as a top-level
  field exactly as reported; missing cost is null and is never inferred from
  usage. Both are taken from the first result, whatever its outcome, so failed
  and invalid reports retain them as evidence.
  Reported cost is provider metadata, not a statement of subscription charges.

Tests cover, for Codex, status precedence, all terminal pairs, exact and absent
usage, malformed input before/after terminal events, and generators; for Claude,
the `subtype=success` plus `is_error=true` regression, every error subtype with
every `is_error` shape, success without explicit boolean false, missing or
non-string subtype, absent usage/cost, usage copy fidelity, missing result,
duplicate result with first-result evidence retention, ignored non-result
events, and malformed input; and for the CLI, both providers' exit codes,
single-line JSON output, determinism, input preservation, top-level cost, file
errors (including decoding errors after terminal events), and argument errors.
Numeric overflow and excessive nesting are checked through both the API and CLI;
repeated argument/file failures must have identical exit codes and output.

Final Codex verification (2026-09-19), using `/opt/homebrew/bin/python3.12`
(Python 3.12.13), `-B`, `PYTHONDONTWRITEBYTECODE=1`, and
`TMPDIR="$PWD/.scratch"`:

- All 44 tools tests passed: 30 run-report tests and 14 evidence-index tests.
  Both provider paths, usage/cost retention, precedence and deterministic CLI
  success/failure behavior were verified. Overflow and excessive nesting
  previously raised uncaught exceptions; both now report invalid.
- Operator support command: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`.
  Twenty tests passed; `test_stdin_does_not_follow_candidate_symlink` could not
  set up because it requires `.runtime/`, which is absent and outside this
  candidate's writable scope. The host must run that test in its proper workspace.
  Git tests used process-local `GIT_CONFIG_GLOBAL=/dev/null`,
  `GIT_CONFIG_SYSTEM=/dev/null`, and `XDG_CONFIG_HOME="$PWD/.scratch"` because
  global Git configuration is inaccessible in this sandbox.

Runtime owns prior-writer checks, frozen acceptance and separate review before
integration. Process inspection is blocked in this candidate sandbox. No live
provider calls were needed for these deterministic parser tests. This candidate
has not been committed, published, or accepted; host verification/review is next.
