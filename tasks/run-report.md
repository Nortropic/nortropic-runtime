# Accepted development task: run-report

The project currently extracts provider run status/usage manually. A real Claude
log has `subtype: success` together with `is_error: true`; treating the subtype as
approval is wrong. Build a deterministic Python standard-library reporting CLI.
This is Customer Zero Runtime development work, not the full project office.

Change only tools/run_report.py, tools/test_run_report.py and tools/README.md.
No installs, network, commits, permission/configuration changes or publication.
Implement `summarize(provider, lines)` where lines is an iterable of JSONL strings.
Return a dict with provider, status, usage. Status is completed, failed, incomplete,
or invalid. These report provider execution only, never review/task acceptance.
CLI: `python3 tools/run_report.py --provider codex|claude PATH` writes one JSON
object; exits0 for completed,1 for other statuses,2 for usage/file errors.

Codex phase (first executor):
- `turn.completed` terminal event with usage input_tokens/cached_input_tokens/
  output_tokens means completed if no failure; expose those exact values.
- `turn.failed`, `error`, or a failed item (`item.completed` with
  item.status=failed) means failed even with a later completed event.
- Missing terminal event, empty input or only start/item messages means incomplete.
- Malformed JSON or non-object JSON means invalid. Blank lines may be ignored.
- Unknown event types may be ignored. Missing usage stays null, never invented0.
- Multiple terminal events are invalid (a file should contain one run/turn).
- No side effects beyond the CLI's stdout/stderr. Deterministic output.

Claude phase (next executor; currently awaiting access):
- `type: result` is terminal; completed only when is_error is explicitly false
  and subtype is success; is_error true or an error subtype means failed.
- Keep reported usage dict and total_cost_usd as reported; no inferred cost.
- Missing result incomplete; duplicate result or malformed input invalid.

Final Codex phase verifies both parsers and CLI with clear handoff documentation.
Frozen acceptance tests remain outside candidate write access. Candidate tests
are useful implementation work but do not replace that verifier or separate review.
