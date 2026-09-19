# Living plan — Runtime v0.1

## Current step: exact-candidate integration boundary

RESULTAT: One host-only boundary rejects unfinished task or missing/failed/stale
mandatory evidence before publishing. It rechecks remote base/head and reconciles
an acknowledged or lost-response merge against the exact candidate Git tree.

VARFÖR NU: PR4 integrated the first real Codex phase and persistent access wait;
publication is still host-operated. Before wiring automatic candidate integration,
prove its decision boundary and preserve the incomplete task's waiting state.

METOD: D016 needs-driven reuse of selected prior negative test ideas. Test real
local Git identities and counted remote effects, then inspect actual GitHub
protection read-only. Do not treat fake remote tests as live Runtime publication.

ARBETSYTA: work/controlled-codex-integration based on integrated0ab88f1 (PR4), own project
and isolated .runtime candidate only. Owner changed origin PUBLIC (D006).

FÖRUTSÄTTNINGAR: Pinned local Temporal1.9.1/SDK1.33.0 and Codex0.155.1 with ChatGPT
subscription, no API fallback. Claude D005 WAITING_ACCESS remains: org disabled
subscription access, no repeated call until new access evidence. Old Symphony and
Temporal probe processes inspected stopped; B1 launch remains disabled.

NÄSTA HANDLING: Separate review of runtime/integration.py and six targeted
publication regression tests, then integrate this small component. Next connect
it to actual independent review and a second accepted Codex task in Temporal;
receipts must come from host-owned actual runs, not candidate-created dictionaries.

PROV OCH KLART-NÄR: Missing/failed/stale/wrong-scope/same-author review and incomplete
whole task reject before publication. Changed base/head denies merge. Reconcile
existing merge without publishing again, checking actual Git tree/parent identity.

UTFALL: Implemented;6 targeted tests passed with counted remote fixtures and real
local Git objects. Current GitHub protection readback passed. New publisher live
merge NOT RUN. See evidence/integration-gate/result.md. First phase remains PASS
but entire run-report task waits for deferred Claude access; see accepted-task/result.md.

ÅTERUPPTAGNING: Root driver active; no engine/model processes remain. Current work is on
work/controlled-codex-integration; completed first-phase Runtime support is in main.
Canonical SQLite .runtime/tasks/runtime-run-report-1/temporal.sqlite; portable
backup+hashes evidence/accepted-task/state/. Candidate remains in same task
workspace; immutable accepted phase snapshot is attempt-2/candidate under evidence.
No further retries: workflow is waiting_access with attempts2. Current driver resume
is ONLY for previous diagnosis attempt1 and MUST NOT be rerun against this state.
Next step is D016 boundary implementation; owner defers Claude usage per D015.

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
