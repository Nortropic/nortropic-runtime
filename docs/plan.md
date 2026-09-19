# Living plan — Runtime v0.1

## Current step: one accepted Codex development task through Temporal

RESULTAT: A real accepted task yields candidate source and raw provider results
through a native Temporal activity, then waits durably for the next permitted
executor. First phase only; v0.1 still requires real Claude continuation.

VARFÖR NU: PR3 integrated9278081 proves replay of completed steps and a waiting
state after real server/worker death. Its `executions` counts steps, not failed
model attempts. Need actual bounded development, preserved attempt history and a
candidate that cannot alter host acceptance/publication authority.

METOD: Customer Zero needs a trustworthy run report: current Claude JSON result
has subtype success yet is_error true, and manual extraction risks false passes.
Accept a small provider-log reporting CLI; Codex implements Codex parsing, Claude
adds Claude semantics, Codex finishes verification. No second status registry:
Temporal history/query owns phase, attempt and waiting. Candidate source and raw
artifacts live in isolated workspace/evidence, not editable acceptance state.

ARBETSYTA: work/accepted-codex-task based on integrated9278081 (PR3), own project
and isolated .runtime candidate only. Owner changed origin PUBLIC (D006).

FÖRUTSÄTTNINGAR: Pinned local Temporal1.9.1/SDK1.33.0 and Codex0.155.1 with ChatGPT
subscription, no API fallback. Claude D005 WAITING_ACCESS remains: org disabled
subscription access, no repeated call until new access evidence. Old Symphony and
Temporal probe processes inspected stopped; B1 launch remains disabled.

NÄSTA HANDLING: Obtain separate final review of the first Codex-phase delivery
and actual evidence, then integrate it via exact-SHA protected PR. Continue a
Codex-only slice for controlled candidate review/integration and recovery; owner
D015 defers Claude purchase. Do not call Claude again or pretend v0.1 is complete.

PROV OCH KLART-NÄR: This slice has real candidate behavior, external immutable
snapshot acceptance and durable attempt/wait evidence. Integration still requires
separate review of this exact revision. Overall v0.1 criteria remain below.

UTFALL: First Codex phase PASS at attempt2;12 host acceptance cases and15 candidate
tests passed. Same native workflow retains interrupted attempt1 and successful
phase2; waiting_access/count2/results survived actual worker/server restart.
All recorded provider and engine groups stopped. See
[evidence/accepted-task/result.md](../evidence/accepted-task/result.md) for raw links,
usage, conservative reporter behavior and limitations. Claude task phase NOT RUN.

ÅTERUPPTAGNING: Root driver active; no engine/model processes remain. Work exists
on work/accepted-codex-task and pending evidence is preserved before review.
Canonical SQLite .runtime/tasks/runtime-run-report-1/temporal.sqlite; portable
backup+hashes evidence/accepted-task/state/. Candidate remains in same task
workspace; immutable accepted phase snapshot is attempt-2/candidate under evidence.
No further retries: workflow is waiting_access with attempts2. Current driver resume
is ONLY for previous diagnosis attempt1 and MUST NOT be rerun against this state.
Next step is review/integration of this completed slice, then independent Codex work.

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
| Autonomous development completion | B1 fixture dispatch/result preserved; real development NOT RUN |
| Persistent continuity | Fresh Codex instruction probes and review navigation passed; full takeover/Claude pending |
| Replaceable execution | Claude blocked by server access; Runtime swap NOT RUN |
| Interruption/capacity | Support limiter tested; runtime restart/quotas NOT RUN |
| Controlled integration | Real host-led missing/stale rejection and legitimate PR merge; candidate rights/automatic gate NOT PROVEN |
| Repeatable use / Customer Zero | NOT RUN |

Runtime v0.1 is not complete. No project-wide time/token cap invented. Per-run
limits are local safeguards; resource history and failed results remain preserved.
