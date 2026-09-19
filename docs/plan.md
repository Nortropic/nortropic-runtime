# Living plan — Runtime v0.1

## Current step: bounded durable-engine compatibility decision

RESULTAT: Determine whether an existing engine can preserve workflow position,
attempt count and a waiting state across worker/server restart, without rebuilding
these features around Symphony. This is a prerequisite experiment, not v0.1.

VARFÖR NU: Symphony B1 proves discovery/dispatch/hooks but source inspection shows
retry and blocked state reset on boot and a hard-coded Codex session boundary.
A general new scheduler around it would violate the mandate's reuse constraint.

METOD: Compare existing Symphony with a local Temporal workflow using the same
criteria: persistence, explicit executor activity boundary, bounded retries,
operational dependencies and cost/permissions. Run a deterministic no-model
restart/signal experiment first. Stop the expansion if the proposed integration
becomes a general new engine; no production/Cloud service is being introduced.

ARBETSYTA: /Users/elinhaggstrom/Nortropic Runtime, work/durable-engine-probe,
based on integrated d07fd7eb351d9b367bebfe25bae4e6963e843cc4 (PR #2).
Remote PUBLIC by owner's explicit change, D006. Main protection is active.

FÖRUTSÄTTNINGAR: Existing Python3.12, pinned Temporal CLI1.9.1 official arm64
binary (SHA256 41e0425378fcb4fb5766340b97435e20fe47bbff2d7bf644ec2d51f7662b7c56),
SDK temporalio1.33.0 with reviewed wheel-only transitive dependencies. Install only
under .runtime, no global changes or paid services. Local development service
loopback127.0.0.1:7339 with explicit SQLite file and no UI. Check port before use.
Sources and limits: D011. Claude is WAITING_ACCESS, D005, no repeated model calls.

NÄSTA HANDLING: Download official CLI and SDK wheels with bounded commands; verify
archive hash and inspect wheel metadata/.pth/lifecycle concerns before installation.
Pin every installed wheel with hash. Then a minimal workflow performs activity1,
waits for a signal, survives both worker and server termination/restart, and finishes
activity2 without rerunning activity1. Export actual history and filesystem result.
No model or GitHub publication during this compatibility test.

PROV OCH KLART-NÄR: Persisted waiting workflow remains waiting after restart,
attempt counter stays1 until deliberate continuation, side effect1 occurs once,
continuation gives count2, unique workflow ID rejects duplicate start. A failed
or empty history is not a pass. Server/workers stopped and SQLite retained after
experiment. Next decision selects reuse path, not automatic architecture adoption.

UTFALL: NOT RUN. Dependencies selected, download/installation not yet complete.

ÅTERUPPTAGNING: Root chain driver active. No engine/model worker remains from B1;
completed attempt2 process group removal measured. Check process records and PIDs
before writes. Existing B1 workflow is execution_enabled=false; do not re-enable
it blindly. Last integrated slice PR2 is complete and server merge readback is in
evidence/integration/merged-pr-readback.json (new branch preserves this receipt).

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
