# First useful Codex phase through durable engine — bounded PASS

Runtime implementation: a23d94e (plus evidence-only a4ad5f6 at launch), Temporal
CLI1.9.1/SDK1.33.0, Codex0.155.1/gpt-6-astra, ChatGPT subscription. Same task ID
runtime-run-report-1, same candidate base9278081. Not complete Customer Zero/v0.1.

Attempt1 was interrupted after34.166s on independent review of two real host
file-handling flaws, before acceptance. No terminal usage: unknown, not zero.
Waiting_diagnosis/attempt1 survived actual worker/server restart. See D014.

After reviewed correction and explicit changed-prerequisite signal, attempt2 ran
134.029s, emitted a completed provider terminal and passed12 frozen host acceptance
cases against a read-only snapshot. Three SHA256 identities are in
attempt-2/acceptance.json. Candidate's15 tests also passed independently on that
snapshot (candidate-tests.json). Git candidate status lists only the three allowed
source files plus host-created TASK.md; no candidate commit/publication occurred.

Engine-owned actions: restored previous history; consumed explicit diagnosis
signal; incremented attempt count; launched bounded Codex; captured raw JSONL and
usage; cleaned provider group; froze/hashes candidate files; ran external tests;
entered waiting_access for known unavailable Claude. Restarting server and worker
restored the same phase, both attempt results and count2. All4 engine groups removed.
Raw: engine-resume-2/history-before.json, result.json, attempt-2/*.

Usage reported by actual Codex terminal: input240607, cached input202368,
output6151, reasoning output358, cache-write input0. No API pricing conversion;
exact subscription cost/remaining capacity and interrupted attempt tokens unknown.
The next task should reduce irrelevant inherited bootstrap context where possible,
without discarding required shared instructions. No project-wide token cap inferred.

Actual use: reporter says attempt1 incomplete and attempt2 failed. The latter is
correct for its deliberately conservative contract: two failed command items remain
in the raw log despite a later completed turn and successful final tests. An initial
operator assertion expecting completed failed; inspection corrected that expectation,
not the implementation/acceptance. See real-log-use.json. Provider terminal status,
individual command errors and candidate acceptance are different evidence fields.

SQLite backup after all recorded processes stopped: state/temporal.sqlite.gz,
SHA256 and successful integrity_check in state/manifest.json. Canonical working
state remains .runtime/tasks/runtime-run-report-1/temporal.sqlite. Do not overwrite
it, launch a duplicate or infer that waiting is approval. Snapshot+native history
are preserved remotely with code; no credentials are in task input or workflow.

Still unproven: Claude continuation, second accepted task, automatic independent
review/publication, abrupt in-flight worker-death fencing and general exactly-once
side effects. Current restart was after provider cleanup. Owner defers Claude
purchase (D015); independent work continues. Actual403 access denial D005 persists.
