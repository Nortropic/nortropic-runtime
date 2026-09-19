# Provider run report — candidate Claude phase

Contract: [TASK.md](../TASK.md). `run_report.py` uses only the Python standard
library. `summarize(provider, lines)` consumes JSONL strings and returns
`provider`, `status`, and `usage`; Claude reports also carry `total_cost_usd`.
It reports provider execution only; completion does not imply review or task
acceptance.

```sh
python3 tools/run_report.py --provider codex PATH
python3 tools/run_report.py --provider claude PATH
python3 -B -m unittest discover -s tools -p 'test_*.py' -v
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

Codex behavior (unchanged from the Codex phase):

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

Claude stream-json behavior (this phase):

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

Tests cover, for Codex, status precedence, all terminal pairs, exact and absent
usage, malformed input before/after terminal events, and generators; for Claude,
the `subtype=success` plus `is_error=true` regression, every error subtype with
every `is_error` shape, success without explicit boolean false, missing or
non-string subtype, absent usage/cost, usage copy fidelity, missing result,
duplicate result with first-result evidence retention, ignored non-result
events, and malformed input; and for the CLI, both providers' exit codes,
single-line JSON output, determinism, input preservation, top-level cost, file
errors, and argument errors.

Validation in this candidate: the Codex phase ran all suites with
`/opt/homebrew/bin/python3.12` (see the prior handoff). The Claude phase was
authored with Read/Edit/Write only and had no process execution; its tests were
not run by the Claude executor. The host runs the suites after Claude exits,
using `-B`, `PYTHONDONTWRITEBYTECODE=1`, and `TMPDIR="$PWD/.scratch"` to keep
temporary test writes isolated, plus `git diff --check` on the three files.

Next action: the final Codex phase runs both suites, verifies both provider
paths and the CLI against TASK.md, fixes anything the unexecuted Claude tests
surface, and updates this handoff with the verification result. Frozen
acceptance tests and separate review remain external. This candidate has not
been committed, published, or accepted.
