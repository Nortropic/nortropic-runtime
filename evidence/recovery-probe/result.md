# Abrupt worker and known-capacity wait proofs

The actual DevelopmentTask and execute_codex activity used the real bounded
attempt guardian and native candidate sandbox, with an explicitly injected
harmless Python provider (no model calls). The provider appended attempt1 to an
isolated source file, then waited. Killing the native worker with SIGKILL left
its separately grouped guardian alive. CLI process inspection refused startup
while that writer was recorded alive; a concurrent same-task guardian failed
flock before creating another attempt directory. Raw contender traceback retained.

The existing3s guardian bound removed the provider group at3.063s. A second
worker replayed the SAME native workflow. No implementation retry occurred during
the existing153s activity timeout. Native history then entered waiting_diagnosis
with attempt1 and the retained file. An explicit reasoned signal started attempt2,
which appended to the same source, froze an actual Git candidate, passed the
fixture assertion, and reached one simulated review/publication. Final native
counter2 and exact retained text prove continuation rather than starting over.
result.json, history.json and evidence/runs/runtime-recovery-fixture-1 contain
raw observations. Test elapsed155.773s. All six recorded process groups and the
service group were removed. No real provider or GitHub publication occurred.

Known capacity: capacity-wait-v2 uses an explicit frozen quota reason in an
accepted step. The actual native workflow waits before provider invocation;
a separate service/worker restart returns identical waiting_access, attempts0,
results[] and reason. Histories contain no activity scheduling and the forbidden
fixture provider was never called. This tests supplied known quota, not automatic
quota detection or an actual provider quota response. Historical actual Claude
403 access denial and its no-retry waiting state remain separate evidence.

A first capacity-probe start failed before launching a service: plain socket bind
mistook stopped-service TCP TIME_WAIT on7339 for a live listener. No listener was
present (lsof); port-diagnosis.json records reuse/no-reuse results. A small service
preflight correction uses SO_REUSEADDR, never SO_REUSEPORT. Two real local socket
tests confirm live listeners remain refused while stopped-listener TIME_WAIT is
accepted. The corrected native two-start capacity probe passed. This is the only
production code change in this delivery; abrupt-worker behavior needed no change.

Rejected alternative: a no-model pinned Codex app-server probe retained an
inherited flock descriptor. It was not adopted: exposing that descriptor to
candidate tool descendants is unqualified and unnecessary for this measured
recovery route. Its source/output/cleanup are retained as exploratory evidence,
not part of production qualification.

Scope: abrupt death of the native worker, existing bounded guardian, ordinary
process groups and explicit inspected retry on this trusted Mac. This does not
prove arbitrary SIGKILL of the guardian, deliberate detached descendants or
host compromise. Real model interruption via controlled SIGTERM is already
recorded under evidence/accepted-task. Actual Claude swap and first task completion
still require restored access; no new Claude calls, purchases or API fallback.

Native SQLite backups and hashes are under state/; canonical REAL tasks remain in
.runtime/runtime.sqlite, untouched by these separate fixture databases. Experiment
scripts refuse existing output/state paths, so never blindly rerun them in place.
