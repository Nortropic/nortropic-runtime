# Living plan — Runtime v0.1

## Current step: execute the reviewed continuation on the original task

RESULTAT: One useful accepted Codex task completed automatically through external
acceptance, fresh independent review and protected integration (PR7). Its evidence
and runbook are integrated (PR8). Bounded abrupt-worker recovery and supplied-known-
quota wait passed; separately approved service fix/evidence are delivered in PR9.
Check PR9 server merged state and git origin/main when taking over; do not infer
integration from backup branch existence. Runtime v0.1 is NOT complete.

ARBETSYTA: Nortropic/nortropic-runtime, local /Users/elinhaggstrom/Nortropic Runtime.
Current branch work/report-continuation from main531f097 (PR11). Origin is public by owner
D006, required exact-SHA tests/review protection active. Earlier branches remain
preserved. No production changes, new API billing, purchases or expanded rights.

NÄSTA HANDLING: Exact continuation input tasks/run-report-continuation.json is
prepared, preserved and separately approved atc702728. Review receipt:
evidence/reviews/report-continuation-input.json. Adapter/full verifier are
approved and integrated via PR11 at531f097c85a42ac5afc86ace6bd8ee7f37fc5b8d.
Input SHA256 c892b92f1f1c5879b2b06021ee1b914be3ed8f8b049a6a75a7c617ebde4ab29c;
original task SHA25639aaab70858d584402e52c355c61479b0a0a5e252653b9589196857d02b61c17;
expected native attempt2. No real task mutation or model launch yet.
Preflight confirms old writers stopped, engine lock free, same qualified Max auth;
canonical DB backed up and hashed under evidence/accepted-task/access-prestate/.

Input review approved. Next launch ONCE from clean tracked worktree:
`.runtime/temporal-venv/bin/python -m runtime.run tasks/run-report-continuation.json
--resume --access-restored`. The controller owns model transitions/testing/review/
publication. Do not edit root source or candidate while running. Observe native
state under evidence/accepted-task/observations/<new id>/state.json and attempts3/4.
After any failure inspect preserved state and process groups; no blind rerun.
Candidate-before-continuation will preserve the original workspace when host
preparation runs. No history reset, resubmission, new subscription or API fallback.
Each implementation call remains bounded300s; review180s; zero automatic retries.
CLI observation is bounded to the accepted step count plus review/publication time.

Then use the actual delivered report on saved real provider logs, restart both
native tasks to prove retained completion, and audit every mandate§1/§9 row.
The second accepted evidence task already used this DevelopmentTask/Publisher.

UTFALL: Evidence task candidate38ecdaf7 integrated as0fba283 through PR7.25 host
observations including14 candidate tests passed. Actual independent model review
had a different thread identity; one implementation and one publication. Real
manifest use and fresh restart of both tasks passed (see result.md below).
Abrupt worker SIGKILL fixture passed in155.773s: contender lock/start blocked,
old sandbox writer bounded to3.063s, native attempt1 retained until153s timeout,
explicit diagnosis continued preserved source as attempt2, one simulated publish.
Known-quota-input wait survived engine restart with zero provider activities.
SO_REUSEADDR preflight fix passed real active-listener/TIME_WAIT tests and native
restarts. Independent reviewer approved source/evidence7723de2; final plan delta is
separately checked before PR9 integration. No real vendor quota or arbitrary
hostile detached-process/guardian-SIGKILL claim. D018 records limits.

ÅTERUPPTAGNING: No model, engine or worker remains active; actual process inspection
and free engine lock were checked after fixtures. Fresh receivers still verify
recorded launch PIDs/groups and Git before writes. Real canonical native database:
.runtime/runtime.sqlite. Backup/hash: evidence/runs/runtime-evidence-index-1/state/.
First report task: waiting_access, attempts2, retained candidate at
.runtime/tasks/runtime-run-report-1/candidate; immutable Codex phase snapshot under
evidence/accepted-task/attempt-2/candidate. Second task runtime-evidence-index-1:
completed, attempts1, publication_attempts1. Never resubmit either existing task.
No real-task Claude/model attempt is pending; no automatic retry is enabled.
Only isolated no-model fixture/test processes ran for this adapter delivery.

Fixture databases are separate and backed up under evidence/recovery-probe/state/.
Do not rerun historical experiments into existing output/state directories. They
are preserved proofs, not resumption commands. Current use instructions:
docs/runbook.md. Actual outcomes/usage/coordination: evidence/runs/runtime-evidence-index-1/result.md.
Recovery limits/raw pointers: evidence/recovery-probe/result.md.

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

Qualify restored Claude access and constrained execution, then continue the same
report task Codex→Claude→Codex through Runtime. Preserve its existing attempt
history. Complete whole-task review/integration and audit every §1 row; keep actual
proofs distinct from fixtures and scope limits. No repeated model/error probes
until access changes, and no extra task invented to substitute for the real swap.

## Mandate §1 evidence index

| Capability | Current result |
|---|---|
| Autonomous development completion | Evidence integrity task completed through actual implementation/test/review/protected merge (PR7) |
| Persistent continuity | Fresh Codex instruction probes and review navigation passed; full takeover/Claude pending |
| Replaceable execution | Claude access/profile qualified; Runtime swap NOT RUN |
| Interruption/capacity | Real controlled model interruption; abrupt worker + bounded harmless writer recovery; supplied known-quota wait survives restart without calls. Arbitrary guardian kill/detached descendants and actual vendor quota not proven |
| Controlled integration | Actual isolated candidate/read-only review and automatic exact-subject protected merge (PR7); negative fixtures and prior live missing/stale rejection |
| Repeatable use / Customer Zero | Second accepted task completed; first report task still waits for Claude, so two complete tasks not yet proven |

Runtime v0.1 is not complete. No project-wide time/token cap invented. Per-run
limits are local safeguards; resource history and failed results remain preserved.
