# Living plan — Runtime v0.1

## Current step: connect controlled integration to the native task workflow

RESULTAT: An accepted Codex-only development task can produce a frozen Git
candidate, undergo actual external tests and fresh independent review, and pass
the host-only publication boundary. The existing report task remains waiting.

VARFÖR NU: PR5 integrated the six-test publication component at f7bf8f4. Its remote
tests were simulated; actual receipt construction and independent review invocation
must now be connected before a live automatic integration claim.

METOD: Reuse Temporal activities/history and qualified candidate sandbox/snapshot.
Generalize task parameters rather than add a scheduler. Use native history replay
against existing report evidence before upgrading the workflow. Freeze the next
task/acceptance before any model invocation. D016 records selected old test reuse;
D017 scopes this connection and second useful evidence-hash CLI task.

ARBETSYTA: work/second-task-through-runtime based on integrated f7bf8f4 (PR5).
Origin PUBLIC by owner decision D006; branch protection active. Own project and
isolated test targets only. No new costs/rights; owner defers Claude usage (D015).

NÄSTA HANDLING: Obtain separate review of connected workflow, task freezing,
read-only review invocation and bounded submission/service entry point. Correct
concrete findings and integrate reviewed support before accepting the next live task.
Do not call Claude, discard report history, or invent approval from partial tests.

PROV OCH KLART-NÄR: Actual implementation/review runs differ; tests/review bind the
same candidate and frozen acceptance; incomplete old report still waits at attempt2.
Missing or invalid mandatory result cannot publish. A second accepted task must
show the complete route before its successful integration is claimed.

UTFALL: PR5 receipt evidence/integration-gate/integration.json. Connection and bounded CLI are implemented, not yet independently reviewed or
live-qualified. Sixteen support tests passed. Real native engine with explicit
no-model/no-remote fixtures passed seven cases, including failed tests, missing/
rejected/stale/self review, and lost publication acknowledgement followed by
reconciliation without duplicate simulated mutation. Evidence: native-fixtures-v2
under evidence/connected-workflow; real Git freeze and review parsing tests in
scripts/test_connected.py. Both older histories also replay under current code
(replay-v2.json). All fixture engine groups stopped; no model calls were made.
Native Replayer passed both preserved report histories with no model calls
(evidence/connected-workflow/replay.json); the original waiting history is compatible. Prior first Codex phase passed12 host cases and15 source tests;
post-cleanup restart preserved both attempts and waiting_access. Raw evidence and
limits: evidence/accepted-task/result.md. Full v0.1/Claude swap remain pending.

ÅTERUPPTAGNING: Root driver active. No model/engine processes remain. Current
canonical SQLite: .runtime/runtime.sqlite, established by native SQLite backup.
The actual bounded --resume CLI verified identical waiting_access/attempt2 and
cleaned both worker/server groups; evidence/accepted-task/observations/b45c9c9259834b9490959e3b42a1c2d7.
Backup/hash: evidence/connected-workflow/state/. Original old SQLite remains at
.runtime/tasks/runtime-run-report-1/temporal.sqlite; prior remote backup/hash in
evidence/accepted-task/state/. Report candidate and task ID
unchanged; immutable phase snapshot at evidence/accepted-task/attempt-2/candidate.
Do not run old launch/resume scripts: they are bounded historical experiments,
not a safe command for the current waiting_access state. No automatic retries.

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
| Autonomous development completion | First real Codex development phase passed; complete task integration pending |
| Persistent continuity | Fresh Codex instruction probes and review navigation passed; full takeover/Claude pending |
| Replaceable execution | Claude blocked by server access; Runtime swap NOT RUN |
| Interruption/capacity | Actual interrupted attempt and post-cleanup wait replay passed; in-flight crash fencing/quotas pending |
| Controlled integration | Real host-led missing/stale rejection and legitimate PR merge; candidate rights/automatic gate NOT PROVEN |
| Repeatable use / Customer Zero | NOT RUN |

Runtime v0.1 is not complete. No project-wide time/token cap invented. Per-run
limits are local safeguards; resource history and failed results remain preserved.
