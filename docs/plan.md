# Living plan — Runtime v0.1

## Current step: bounded in-flight interruption recovery

RESULTAT: Kill an active native worker while a bounded isolated writer is running;
verify observed old writers prevent concurrent startup, retained artifacts and
native attempt count survive worker restart, and explicit diagnosis permits a
new attempt only after old groups stop. No model calls or remote publication.

VARFÖR NU: Real task runtime-evidence-index-1 completed through Runtime and PR7;
its evidence/runbook integrated via PR8 at1b020b55. Existing interruption proof used
controlled SIGTERM; the remaining abrupt-worker case needs concrete evidence.

METOD: Use actual Temporal DevelopmentTask, real attempt guardian and sandbox,
with an explicitly injected harmless fixture provider. Kill only the recorded
fixture worker PID, restart worker on the same native DB/history. Retry policy
remains maximum_attempts1 and old process groups must stop within the per-attempt
bound. Native activity timeout is deliberately retained, not shortened for green
results. Fixture review/publication avoid models and remote writes.

ARBETSYTA: work/inflight-recovery from main1b020b55. Only this project and isolated
.runtime/recovery-probe plus evidence/recovery-probe. Owner defers Claude (D015).

PROV OCH KLART-NÄR: An active writer causes CLI process inspection to refuse a
new start; a second same-task guardian cannot obtain the lock; abrupt worker death
does not rerun the activity or reset attempts; after bounded old-group cleanup,
same workflow reaches waiting_diagnosis. Explicit diagnosis starts attempt2, which
preserves first work. No duplicate simulated publication. Inspect separate review
before integrating experiment results or needed runtime corrections.

NÄSTA HANDLING: Implement and run bounded fixture<=240s, model_calls0. Do not alter
completed task histories, use real Claude, expand permissions or inherit a locking
file descriptor into candidate tools. A small no-model probe found pinned Codex
retains inherited FD locks, but that route is not adopted: descriptor exposure to
candidate tools has not been qualified and would add avoidable authority.

UTFALL: Abrupt-worker experiment ACTIVE: worker1 SIGKILLed, old guardian stopped
its provider at3.063s, a concurrent guardian failed the lock, and CLI inspection
refused active-writer restart. Worker2 is observing native activity timeout153s;
state remains running_codex/attempt1 with no duplicate launch. Service/worker2
may be active; inspect evidence/recovery-probe and recorded launches before writes. Inherited-FD prototype used no model
turn and its app-server group was removed; preserve it as rejected design evidence.
Real task evidence remains evidence/runs/runtime-evidence-index-1/result.md.
25 host cases (including14 source tests), actual fresh review, protected automatic
merge0fba283 and identical completed-state restart passed. One attempt/publication.

ÅTERUPPTAGNING: Root driver active. No model processes run. The explicitly isolated recovery fixture engine/worker
may remain active until its bounded controller finishes; do not start another server. Canonical
real-task DB .runtime/runtime.sqlite, backup/hash in evidence/runs/runtime-evidence-index-1/state/.
Old report still waiting_access/attempt2 after fresh native restart. New task is
completed; do not resubmit. Current fault experiment uses a separate native DB and
never publishes. Earlier report completion and Codex→Claude→Codex remain pending.

## Completed delivery and evidence

PR2 integrated d07fd7e. Exact reviewed candidate8743f56, separate reviewer
/root/startup_review. Legitimate protected merge succeeded; real missing-check
push and old-SHA-status merge rejected. Source and raw artifacts:
- evidence/motor-probe/result.md: B1 file/coordination PASS, historical MCP-profile
  restriction FAILED; later no-model corrected inventory passed. Do not conflate.
- evidence/startup/operator-tests-final.log: six support tests passed.
- evidence/startup/codex-root-0155 and codex-subdir: real instruction loading.
- evidence/startup/claude-root: 403 oauth_org_not_allowed, 0 tokens/$0 reported.
- evidence/integration: protection/readback, missing/stale status denial, merge.
- evidence/reviews/startup-and-b1.md and PR2 body: separate review scope/findings.

Initial protection setup mistakenly pushed4dec677 after a rejected PUT; D007
records it. That event is not a approved-integration claim; corrected delivery
went through PR2 with required checks on exact candidate and server acceptance.

## Later steps (refine the next only)

Select minimal existing engine path; connect official Codex/Claude programs.
Prove real Codex→Claude→Codex continuation, interruption with one writer, durable
capacity wait and retained attempt history. Complete candidate-authority isolation
and automated exact-candidate review/test/integration. Then useful Customer Zero
implementation plus another accepted task over the same route.

## Mandate §1 evidence index

| Capability | Current result |
|---|---|
| Autonomous development completion | Evidence integrity task completed through actual implementation/test/review/protected merge (PR7) |
| Persistent continuity | Fresh Codex instruction probes and review navigation passed; full takeover/Claude pending |
| Replaceable execution | Claude blocked by server access; Runtime swap NOT RUN |
| Interruption/capacity | Actual interrupted attempt and post-cleanup wait replay passed; in-flight crash fencing/quotas pending |
| Controlled integration | Actual isolated candidate/read-only review and automatic exact-subject protected merge (PR7); negative fixtures and prior live missing/stale rejection |
| Repeatable use / Customer Zero | Second accepted task completed; first report task still waits for Claude, so two complete tasks not yet proven |

Runtime v0.1 is not complete. No project-wide time/token cap invented. Per-run
limits are local safeguards; resource history and failed results remain preserved.
