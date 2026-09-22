# AP11 — host recovery active; the review stalls because the host never finishes handing over its prompt

2026-09-22T18:40Z. Office **docs/plan.md alone owns the milestones, next action and resume point.**
The host-recovery release is active (runtime ff9d336a, configuration 9a62788d) and did what it was built to do,
measured live: the host answer released the wait without spending an interactive start, the parent re-diagnosed, the
diagnosis produced a continuation, the child re-ran its review, and one host fact authorised exactly one
continuation — the parent is parked at `waiting_host_diagnosis` sequence 18, not looping. Consumption is 15 of 48.
Review 2 was then cut off at 302.0 s under the raised 300 s bound with a zero-byte event stream, exactly as review 1
was at 182.2 s under 180 s. The bound was never the cause. This candidate corrects the cause: the host abandoned a
partially written prompt and never closed stdin, so the provider waited for an EOF that never came. See decisions
AP11-PROMPT-DELIVERY. Reviews 1 and 2 stay preserved as incomplete; nothing restarts from an interactive start and
the frozen review bound is left untouched. Activation needs a new reviewed transition; after it, the waiting
diagnosis is answered again through the same reviewed host-answer path.

# AP11 — release de89de0e-23692bde active; the sixth start's review was cut off at its host bound; host recovery under construction

2026-09-22T13:40Z. Office **docs/plan.md alone owns the milestones, next action and resume point.**
The parent `office-ap11` waits in `waiting_host_diagnosis` at sequence 12 and the child `ap11-step-5` in
`waiting_review` (measured 12:26Z; scope active, 12 of 48 calls consumed, no approved interactive start left, and
`interactive-retry` is itself refused while the parent has a child); both are preserved, unreset, and measured to
replay identically under this candidate. The waiting diagnosis answered hold and named what it lacked: the review
run's own evidence, a resolution of a misleading host message, and the readers the goal names. This candidate
answers all three (the review run's own record, written by the host from its own files, with the provider's denials
reduced to a count, its usage to a boolean and a host error string classified rather than passed through; the gate
message; the named readers), narrows the implementation attempts through the same record, derives and raises the review model bound (180 -> 300 s
inside the unchanged 360 s envelope), and adds `development_control continue`: a recorded host answer that spends no
interactive start and that authorizes exactly one re-run of an interrupted review, while the model still decides. Tests: scripts/test_host_recovery.py. See decisions
AP11-HOST-RECOVERY. Activation needs a new reviewed transition; after it, the host answers the waiting diagnosis
with the raised bound as the changed prerequisite, the child re-runs its review under the new bound, and the chain
continues on its own.

# AP11 — release 3cc1f945-5ea26473 active; fourth interactive start answered a task the policy refused on depends_on; answer contract made coherent, one further bound start under construction

2026-09-22T10:30Z. Office **docs/plan.md alone owns the milestones, next action and resume point.**
This candidate: instruction and schema delivered per work; extensions as an ordered list bound to how the
previous start really ended (hold or task-refused); tests in scripts/test_discoverability.py. Its Office
counterpart states and enforces the answer contract (tools/development_policy.py). See decisions
AP11-ANSWER-CONTRACT. Activation needs a new reviewed transition.

# AP11 — release 52ee556a-3c1c992a active with claude in every role; third interactive retry ended with hold; discoverability fix and one bound extra start under construction

2026-09-22T08:10Z. Office **docs/plan.md alone owns the milestones, next action and resume point.**
The release transition was activated by the owner at 05:08Z. The Claude executor and reviewer ran a real
Runtime task through the daemon (PR35). interactive-retry-3 ran and answered hold; the parent waits for
host diagnosis; cause and decision in decisions AP11-DISCOVERABILITY. This candidate: the delivered-file
inventory at the single delivery point, the handover text naming it, and the bound single extra
interactive start (tests: scripts/test_discoverability.py). Its Office counterpart changes the common
role instructions (tools/development_policy.py). Activation of both needs a new reviewed transition.

Previous plan text (2026-09-21) follows unchanged.

# AP11 — executor-neutral roles under construction; application paused at 3/48

2026-09-21T14:40Z. Claude Code is sole Runtime/Office writer after a receiver-verified
handover; the Codex root ended on its provider usage limit at 13:17Z. Office
**docs/plan.md alone owns the milestones, next action and resume point.**
interactive-retry-2 was launched and ended on that limit before any draft; scope
paused, 3/48 consumed, no child, no G2. Owner mandate AP11-UTFÖRARNEUTRAL: both
executors shall be able to drive everything; see decisions AP11-EXECUTORS.

Integrated: the office executor and the separate reviewer as an explicit per-role
choice (PR29, 3b31a548), the Office side of that choice (Office PR25, 3c1c992a) and
the goal roles with the genuine interactive session (PR30, 459d7db1; decisions
AP11-EXECUTORS-2) and the delivery of a separately reviewed, hash-bound goal amendment
to every role that receives the goal (PR31, c8d1c8a5; AP11-GOAL-AMENDMENT). This
and the bound on the waiting parent's native history (PR32, 68b91e8e; 30 s wait cycles,
explicit engine margin; AP11-HISTORY-BOUND) and the event-driven pause and evidence wait
(AP11-PAUSE-WAIT). This increment lets a daemon start survive the engine's one day
retention through release-bound verified archives (AP11-DAEMON-HISTORY): measured, the
running service could otherwise never be started again after a stop. Codex route unchanged, no automatic switching. Next: ONE
separately reviewed controlled release transition that stages both revisions and
writes `development.executors`, then real per-role qualification, then the diagnosed
interactive-retry-3, which is the LAST interactive slot. Integration here activates
nothing: the active release stays 1148c945 / Office 7e6230a7 / config bee6ee5d until
then, and AP11 preparation refuses meanwhile because Office main has moved.
AP10 remains active and untouched; its executor choice is a separate later step.

---

# AP10 — private workflow qualification in progress

CURRENT STEP: shared service PR17 and focused startup correction PR18 integrated.
The active pinned Runtime22aedb + Office10875 service successfully ran the real
Office intake task through repair, independent review and protected Office PR17.
The named watch is NOT installed/active. Root is sole Runtime writer; Office
host-contract preparation is explicitly delegated with a separate write handoff.
NEXT ACTION: separately review this bounded private workflow/schedule increment,
then protected integrate and activate only after Office policy is ready. Complete
actual source/schedule/cancellation/recipient/coexistence acceptance before leaving
standing watch active. Office docs/plan.md owns all five phase milestones.
RESUME: work/ap10-private-profile, .runtime/ap10/build-evidence; accepted owner
mandate is in Office evidence/ap10/local/accepted-mandate.md. No new owner prompt
needed for technical transitions. Preserve failed review/test attempts.

Private tests bind native Schedule, no retry/publication, cancelled-stage cleanup,
quota-like unavailable output, spent budget and actual OS IO/credential/network
boundaries. Isolated fixture schedules on the existing engine were deleted after
qualification; raw evidence retained. They are not actual business observations.
Periodic storage cap is not an exact disk quota; source/review usage is preserved.
See docs/private-obligation.md. Login start currently has no schedule to unpause.

Only named Office target and existing subscriptions. No upgrades, new costs/models/
rights, external listener, root service or business logic in Runtime. Development
review/publication gates and earlier histories are unchanged. AP09's decisions and
open graceful-drain gap remain. At an incomplete phase end do not leave unverified
standing service active; stop/unregister after checking unrelated work.

---

# Living plan — AP04 named office target

CURRENT STEP: AP04 office result task completed and protected-integrated at
5a6084ee156bb2d12537f5e58af62e125d83be14 (office PR2), using Runtime
09268df5f59a180afe863d4cf7f95c9ad95f8639. Only closing evidence/docs remain here.
NEXT ACTION: Separately review this closing receipt, integrate it through existing
main protection, then bind final remote and archive rereads. If the matching final
receipt exists, this action is done: stop; no new task or model invocation.
RESUME: work/ap04-receipt, based on 09268df. Office docs/plan.md owns package
closure. Inspect before writes. Native task office-result-1 is completed; two
attempts (first deliberately interrupted), one publication. A completed resume
added no model calls or publication. All recorded groups stopped. Do not resubmit.

Evidence: evidence/ap04/result-run.json, result-acceptance.json,
native-preservation.json. Raw/native data stays locally under .runtime and ignored
evidence/runs/office-result-1; archive and consistent DB were reread successfully.
After the used revision, one narrow selector restriction permits only Codex for
office tasks until any future provider qualification. Original Runtime providers
are unchanged. Its focused regression passed; old histories/evidence are unchanged.
Other closing changes record results/docs and portable raw-evidence exclusions.
Office tasks pin exact Runtime HEAD; an active task must run its accepted revision.
Status/result inspection remains read-only on later documentation revisions.

Office execution is qualified for Codex only. [SUPERSEDED 2026-09-21 by decisions
AP11-EXECUTORS: the executor is an explicit per-role choice; retained as history.]

Scope: host allowlist adds Nortropic/nortropic-projektkontor; frozen inputs from
its reviewed Git revision, candidate clones and publisher use that binding.
Codex office grants are exact files. Active office entry and all host authority
remain outside candidate write scope. Read-only inspection never starts workers.
Office tasks pin Runtime revision. Legacy access/base migration remains Runtime-only;
office uses existing diagnosis, review repair/retry and publication reconciliation.

Evidence: evidence/ap04. Raw/local logs excluded from publication. No new costs,
services, daemon, arbitrary target support or business logic in Runtime.
Separate preliminary review by /root/ap04_review identified boundaries now tested.
A3/A6 and preparation findings are unaffected.

---

## Prior delivered plan (historical)

# Living plan — bounded review continuation and next useful task

## Current state / mandate

Owner requests the known waiting_review gap fixed before relying on autonomous
continuation, followed by a useful Project and Innovation Office task. No engine
replacement, total audit or general hardening. v0.1.0 remains immutable at
580630bcb9d46bb11e17e25053664eec4e23b8ae; its evidence remains valid.
Current branch: work/review-continuation, based on that release/main.
Read-only startup confirmed clean main, original tag and no recorded unfinished
writers or live project worker/provider/service processes.

## Coherent delivery plan

1. Add explicitly diagnosed, identity-bound continuation at waiting_review.
   A valid independent rejection with concrete blockers permits repair within the
   same accepted task, a new immutable candidate, full tests and fresh review.
   Missing/incomplete/inconclusive/invalid review permits review-only recovery;
   it does not establish a candidate defect. Keep every attempt and review.
2. Verify old histories still replay; exercise rejected→repair→tests→review→
   controlled integration and missing-review recovery in bounded isolated runs.
   Distinguish fixtures, actual model calls and actual remote integration.
   Obtain separate review of exact source/evidence before protected integration.
3. Document chain-driver ownership of diagnosis, review and publication waits:
   inspect evidence/processes/remote identities, record a concrete changed
   prerequisite, resume the same task; ask owner only real mandate/cost/priority.
4. Define the next business outcome and target, then compare them with the actual
   qualified profile. It currently admits only Runtime/tools regular files and
   this repository's publisher. Qualify only capabilities the actual task needs;
   never relocate business source into Runtime to circumvent that boundary.
   The saved prior plan contains no concrete business brief or target. Owner was
   asked only for that priority/outcome while the technical correction proceeds.

## Next concrete action

Implementation and focused verification are complete. Separate reviewer
/root/startup_review approved be157ed662a9c3333ea5a46e12d9d3de1a8df400 without
blockers after confirming the previous finding closed. PR14 is the bounded
integration: https://github.com/Nortropic/nortropic-runtime/pull/14.
If PR14 is not merged, finish exact-head review (including subsequent docs-only
receipt), required statuses and protected integration; preserve the server receipt
on state/review-continuation-receipt. If PR14 is merged with the reviewed tree,
this correction is delivered: do not rerun fixtures or completed tasks. Continue
with the pending business outcome/target decision and narrow profile qualification.
The state receipt branch is observation, not extra approved source integration. Evidence: evidence/review-continuation/result.md.
First independent review rejected nonobject handling; preserved patch/finding,
scoped correction and eight-case native rerun now exist. One proof-harness failure
is preserved explicitly, not erased. No model invocation was needed for native
provider fixtures. Existing subscribed review agent supplied independent review.
The business outcome/target question remains pending; no profile expansion or
business source placement has been attempted. Existing completed workflows
must not be resubmitted. Canonical DB: .runtime/runtime.sqlite.

## Release baseline (historical checkpoint, retained)

# Living plan — Runtime v0.1

## Current state: Runtime v0.1 verified; release checkpoint

RESULTAT: Both useful accepted tasks completed and integrated through Runtime.
Actual report Codex→Claude→Codex, external tests, separate fresh review and automatic
protected PR12 merge succeeded. Restart of both tasks returned identical completed
states with no new model attempts/publications. A fresh read-only Claude session located the mandate, current state, decisions,
proofs and next action without owner retelling; no missing §1 evidence was found.
This mandate is complete once the reviewed evidence/docs merge and v0.1.0 tag
are present. Before that checkpoint, do only the final release action below.

ARBETSYTA: /Users/elinhaggstrom/Nortropic Runtime, Nortropic/nortropic-runtime.
Current branch work/runtime-v01-evidence, based on integrated main98b92a7 (PR12).
Completed evidence commits were cherry-picked from preserved backup branch
work/report-continuation, without rewriting that branch. Origin public by owner
D006; required exact-SHA tests/review, strict base/admin and linear protection.
No production changes, new API billing, purchases or expanded external permissions.

NÄSTA HANDLING: Check `git rev-parse v0.1.0` and origin/main. If the tag points to
the protected merge containing this final record, no further implementation is
required by this mandate; report/inspect the delivered result and wait for a new
accepted task. Do not start an optimization loop. If the tag is absent, finish
separate final-documentation review, protected integration of work/runtime-v01-evidence,
verify exact merged tree/base, create the tag on that reviewed merge and preserve
the server receipt on state/v01-release-receipt. That receipt branch is observation,
not an additional approved code integration. No owner decision is missing.

Fresh Claude audit: evidence/v0.1/claude-receiver/assessment.md and verification.json.
It inspected Git/source state itself and read the host's process/auth preflight,
explicitly distinguishing those evidence sources. Latest README/audit were then
preserved on origin. Source implementations already received independent review;
this release step reviews final evidence/documentation rather than repeating code review.

UTFALL / EVIDENCE:
- docs/runtime-v0.1.md maps every mandate§1 row and §9 report requirement.
- evidence/v0.1/claude-receiver/verification.json records the fresh receiver audit,
  bounded94.985s, Read only, successful terminal and complete process cleanup.
- evidence/accepted-task/result.md: report candidatef86a85c27d7cb2567d3c600292f213fa45067b7a,
  PR12 merge98b92a72da2671c0a517f674f8b023667c070bcb. Native4 attempts (first interrupted),
  one publication. Old20 events remain exact prefix of final49. Claude147.813s,
  final Codex131.891s, separate review26.755s; 33 host observations/30 candidate tests.
- evidence/runs/runtime-evidence-index-1/result.md: candidate38ecdaf7, PR7 merge0fba283,
  one attempt/publication, actual independent review and real manifest use.
- evidence/v0.1/restart-and-state.json: fresh restart of both completed tasks,
  unchanged counters/state and no new provider calls; final database backup/hashes.
- evidence/accepted-task/real-use/result.json: delivered report used on actual
  completed/error/interrupted streams. Failed tool items remain failed in this
  conservative report even if later host task acceptance passes; details in result.md.
- evidence/recovery-probe/result.md: actual worker SIGKILL with harmless bounded
  sandbox writer, refusal of competing writer, preserved attempt/state, inspected
  retry; supplied known-quota wait survives restart without calls. Real vendor quota,
  arbitrary guardian SIGKILL/detached hostile children and host compromise unproven.
- evidence/claude-qualification/result.md: actual Max access and native file tools,
  root/subdirectory instruction loading, preserved initial failures and limits.
  D019/D020 own qualified profile and explicit same-task continuation decisions.

ÅTERUPPTAGNING: No model, controller, worker or service remains active after the
recorded restarts. Fresh receivers still verify Git and recorded process state
before writes. Canonical database .runtime/runtime.sqlite; both tasks completed.
Do not resubmit either task or repeat --access-restored. Existing task inspection:
`.runtime/temporal-venv/bin/python -m runtime.run tasks/run-report-continuation.json --resume`
or the same command with tasks/evidence-index.json. These are observations, not new
work. Do not delete state/launch evidence to bypass a guard.

Frozen accepted input/verifiers, candidate and candidate-before-continuation remain
under .runtime/tasks/runtime-run-report-1; all meaningful source/inputs/bundles/raw
results are preserved in Git. Final SQLite backup: evidence/v0.1/runtime.sqlite.gz.
Before any future execution verify old writers stopped, subscriptions still use
the qualified route and exact selected binaries match. Follow docs/runbook.md.
No project-wide time/token budget was invented; individual calls are bounded.

After final release checks are complete, this mandate ends. Further improvements
need a concrete accepted task; do not start an open-ended optimization loop.
