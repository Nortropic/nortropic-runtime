# MODELLVAL — GÄLLANDE INGÅNG: modellvalet för Claude Code och Codex är levererat och aktivt (steg 3)

Detta är planens ordinarie ingång. Avsnitten under den är historik och anger inte nästa steg.

LÄGE 2026-09-24. AP-11 är avslutat och återöppnas inte; posten närmast nedan är dess avslut. Gällande uppdrag är det
ägaren beslutade 2026-09-22 och bekräftade 2026-09-24: ett återanvändbart modellval för både Claude och Codex, i
befintliga Office och Runtime, med separat granskning och skyddad integration, redovisat skilt från AP-11. Kontorets
beslutspost MODELLVAL-FORTSÄTTNING-20260924 bär beslutet; här står Runtimes steg. Meningen "Nästa uppdrag är
ägarens" i AP-11-posten nedan är ersatt av detta.

Tillgodoräknat och inte att börja om: valet i den frysta releasekonfigurationen med vägran i stället för reserv,
identitetskontrollen mot valt namn och körposten (D022), kvalificeringen av `claude-opus-5` och Runtimes egen kopia av
den kvalificerade Claude-CLI:n (D023).

Del 1, Codex-startkedjan kopplad till valet: D028, integrerad som PR 52. Kedjan tar valets namn som sin enda
modellparameter på alla utvecklingsvägar som Codex kan driva. Utan val är kommandot byte för byte detsamma som den
aktiva releasens, uppmätt mot dess egen kod; AP-10:s privata steg läser inte valet.

Del 2, ingången för modellbyte utan källkodsredigering: D029, integrerad som PR 53. `scripts/model_choice.py` är
övergången skriven en gång, med modellen som parameter och `development.models` som det enda den kan ändra; den körs som
den aktiva releasens egen kopia, och `activate` är ägarens steg (runbook, "Changing the model choice"). Den aktiva
releasen bär den sedan del 4.

Del 3, modellvalsfrågan vid kapacitetsbrist: D030, integrerad som PR 54. När ett målanrop eller ett task-försök slutar
med leverantörens egen kapacitets- eller åtkomstvägran skriver värden en fråga till ägaren - vänta, eller byt modell med
verktyget, med exakta kommandon och de kvalificerade alternativen - och byter ingenting själv. `show` listar frågorna.

Del 4, aktiveringen: övergång 14 (`.runtime/modellval/transition-14/`), komponerad av verktygets granskade sekvens med
kodövergångens egna kontroller och separat granskad, stegades och kontrollerades mot den levande värden och aktiverades
av ägaren 2026-09-24T07:26Z: konfiguration `416517ae`, runtime `221df157`, kontoret oförändrat `df5ed5dc`. Efterkontrollen
fann tjänsten igång under sin nya identitet, AP-10:s schema ombundet i sin konfigurationshash och i övrigt oförändrat
(nästa körning 2026-09-25 07:00Z), AP-10:s kommando oförändrat och AP-11 orört (scopet `stopped` på rad 144).

Modellbyten görs nu med verktyget (runbook, "Changing the model choice"). Dess första verkliga körning: `show`, och
`stage` plus `check` av ett uttryckligt Codex-val av den nuvarande modellen (konfiguration `145edd45`, samma modeller
körs), där varje förvillkor höll. Ägaren aktiverade det valet 2026-09-24T11:51Z, verktygets första verkliga byte:
tjänsten igång under sin nya identitet, AP-10:s schema ombundet till `145edd45` och i övrigt oförändrat (nästa körning
2026-09-25 07:00Z), inget arbete i motorn och AP-11 orört. Bytet har därmed körts i drift och inte bara mot dubbletter.
Aktiv konfiguration är `145edd45`: runtime `221df157`, kontoret `df5ed5dc`, och Codex-modellen står nu uttryckligen i
valet.

Nästa: inget kvar inom steg 3.

Öppna poster, inte del av steg 3 om inte ägaren beslutar det: resonemangsnivån ingår inte i valet (Claude `medium`,
Codex `high`); valet binds vid aktivering, inte vid uppgiftsfrysning, så de två vilande utvecklingsuppgifterna
`office-watch-policy-1` och `office-assignment-cli-1` kör den nya koden om de återupptas; ingen tillåtlista över
kvalificerade modeller finns; Codex-binären kontrolleras inte med kontrollsumma vid körning, som Claude-CLI:n gör;
tjänstens identitetskörningar från tidigare konfigurationer ligger kvar vilande, en till per aktivering.

Iakttagelse utanför steg 3, inte åtgärdad: AP-10:s privata steg sväljer en avslutningssignal på samma sätt som AP-11:s
väktare gjorde före D026 (reproducerat 2026-09-24 med den då aktiva releasens egen kod: anropet gick vidare till sin
tidsgräns). Det hör till AP-10:s mandat och är ägarens att avgöra.

# AP11 — historik 2026-09-24: AP-11 godkänt och avslutat

LÄGE, återläst 2026-09-23T23:00Z. Det ändliga åtagandet `office-ap11` är avslutat. `office-ap11-assessment-6`, dess
enda räknade granskning (anrop 31), godkände hela slutacceptansen utan blockerande fynd, och `close()` satte scopet
till `stopped` (journalrad 144) och skrev `final.json`. 31 av 48 anrop förbrukade, implementationsförsök 1 av 6 per
arbetsdel. Aktiv release runtime 2def3667 / kontor df5ed5dc, konfiguration d4f2e63e (övergång 13). AP-10 är orört:
schemat opausat, nästa körning 07:00Z.

Vägen: sex helhetsbedömningar; de fem första inconclusive och bevarade. G6-demonstrationen bars av den femte (anrop
29 avbrutet av en verifierad SIGTERM, anrop 30 fortsatte ur bevarat läge) och prövades av den sjätte. Två fel funna
live och rättade: väktarens avbrott (D026) och slutgranskningens leveransgräns (D027).

Nästa: inget inom AP-11. Det stängda scopet återöppnas inte, och inget startas under dess identiteter. Nästa uppdrag
är ägarens.

Stängningsposten: `.runtime/ap11/claude-path/sixth-assessment-20260924/CLOSURE-READBACK.json`.

# AP11 — historik 2026-09-23T22:15Z: demonstrationen genomförd; den sjätte bedömningen prövar den

LÄGE, mätt 2026-09-23T22:15Z. Aktiv release runtime d17d562e / kontor df5ed5dc, konfiguration 8d3c0ada (övergång 12).
Scopet står `paused` med 30 av 48 räknade anrop. `office-ap11-assessment-5` bar G6-demonstrationen enligt formens
revision 6: anrop 29 avbröts med en verifierad SIGTERM och väktaren skrev själv sitt ofullständiga resultat (D026),
körningen parkerades, en fortsättning vägrades medan scopet var pausat, och efter återupptagning och värdsvar gjorde en
färsk session (anrop 30) den återstående granskningen. Anrop 30 svarade inconclusive: den är händelsens andra halva.
Posterna G6-LIVE.json och FIFTH-ASSESSMENT-RUN.json är bundna.

Nästa, i ordning:

1. D027: slutgranskningens leveransgräns 4 MiB, vald av operatörssessionen under ägarens ord 2026-09-24 att det som
   krävs görs (under 3 MiB föll historikens första del bort som lucka), och ägarvyläsaren levererad; publiceras genom
   den skyddade integrationen, isolerad provkörning på den nya revisionen.
2. Övergång 13 aktiverar D027-revisionen och binder `office-ap11-assessment-6`, vars enda räknade granskning (anrop 31)
   prövar hela kedjan med den genomförda demonstrationen. Förväntad förbrukning 31 av 48.

Återupptagningsposten var då den som RESUMPTION-CURRENT.json pekade på.

Operatörsvägen: docs/runbook.md, avsnittet "AP11: operating the finite commitment".

# AP11 — historik 2026-09-23T21:30Z: väktarens avbrott rättat (D026); demonstrationen i den femte bedömningen

LÄGE, mätt 2026-09-23T21:30Z. Aktiv release runtime 5edc7338 / kontor df5ed5dc, konfiguration ebf792b2 (övergång 11).
Scopet står `paused` med 28 av 48 räknade anrop. A och B är integrerade. Fyra helhetsbedömningar är inte godkända och
står oförändrade: `office-ap11` (step-36) och `office-ap11-assessment-2`, `-3` och `-4` (anrop 26, 27 och 28), alla
inconclusive. Den fjärde skulle bära G6-demonstrationen enligt formens revision 5. Avbrottet skickades som bestämt
(SIGTERM till den verifierade väktaren) men verkade inte: väktarens hanterare kastade `InterruptedError`, som
standardbibliotekets selectors sväljer, så granskningen gick till sin dom. Orsaken är mätt och återskapad isolerat och
rättad i D026. Ägarens delegering (AP11-DELEGERING-20260923) gäller; slutkraven och 48/6 är oförändrade.

Nästa, i ordning:

1. Publicera D026 genom den skyddade integrationen och spela in den isolerade provkörningen på den nya revisionen,
   med provet som skickar en verklig signal till en verklig väktare.
2. G6-formens revision 6: `office-ap11-assessment-5` bär demonstrationen, `office-ap11-assessment-6` bedömer den i
   en separat körning. Separat granskning före körning.
3. Övergång 12 aktiverar D026-revisionen och binder den femte bedömningen; övergång 13 binder den sjätte efter att
   den femte har slutat. Förväntad förbrukning 31 av 48.

Återupptagningsposten var då den som RESUMPTION-CURRENT.json pekade på.

Operatörsvägen: docs/runbook.md, avsnittet "AP11: operating the finite commitment".

# AP11 — historik 2026-09-23T20:10Z: G6-demonstrationen i egen körning, bedömd av en separat

LÄGE, mätt 2026-09-23T20:10Z. Aktiv release runtime 6c7a6db8 / kontor df5ed5dc, konfiguration e99d20a4 (övergång 10).
Scopet står `paused` med 27 av 48 räknade anrop. A och B är integrerade. Tre helhetsbedömningar är inte godkända och
står oförändrade: `office-ap11` (step-36), `office-ap11-assessment-2` (anrop 26) och `office-ap11-assessment-3`
(anrop 27), alla inconclusive. Den tredje bar G6-provet enligt formens revision 2, men avbrottet kunde inte göras innan
granskningen var klar, och dess dom fann formens struktur otillräcklig: demonstrationen och dess bedömning måste
ligga i olika körningar. Ägaren har delegerat den tekniska ledningen (AP11-DELEGERING-20260923); slutkraven och
48/6 är oförändrade.

Återupptagningsposten var då den som RESUMPTION-CURRENT.json pekade på. I sammandrag:

1. Publicera revisionen där ett godkännande från den fortsatta halvan av ett avbrott aldrig stänger åtagandet (D025).
2. Övergång 11: binda `office-ap11-assessment-4`, som bär demonstrationen: dess första räknade granskning avbryts vid
   en mätt punkt, körningen fortsätter ur bevarat läge och en färsk räknad session gör den återstående granskningen.
3. Övergång 12: binda `office-ap11-assessment-5`, en separat körning vars enda granskning bedömer hela kedjan med
   den färdiga demonstrationen. Förväntad förbrukning 30 av 48.

Operatörsvägen: docs/runbook.md, avsnittet "AP11: operating the finite commitment".

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

## AP-11 komplettering och andra helhetsbedömning (2026-09-23)

Tillämpningen `office-ap11` levererade A (`ap11-step-5`, reconciliation) och B
(`ap11-step-28`, handoff); båda är integrerade. Helhetsgranskningen `step-36` gav
`inconclusive` med tio blockerande fynd. Körningen är COMPLETED med sitt verkliga
resultat och scopet står `paused` med skälet bevarat. Ägaren godkände 2026-09-23
komplettering av bevisen och en andra helhetsbedömning av samma åtagande.

Domen och originalkörningen bevaras. Ingen reset, ingen omkörning av A/B, ingen
ny köridentitet som suddar avslaget eller budgeten. Samma scope, samma faktiska
förbrukning och samma tak 48/6.

Åtgärdade fynd, genom leverans snarare än beskrivning: oläsbara bevis (delad
historik med en händelse per rad), namngivna men oinventerade källor, frysta
tasks och deras förberedelsegranskningar, G8:s isolerade takvägransprov (källan
läses ur releasens egen revision), G2:s utlösningspost (härledd ur bevarade byte)
samt C1/C3-förutsättningarna (levereras via ACTIVE_SELECTION.json).

LÄGE VID SKRIVARBYTE 2026-09-23 (andra bytet). G6, dokumentationen av den andra
bedömningsvägen, samt beslut och separat granskning för `office-ap11-assessment-2`
är utförda. PUBLICERAT: PR #43, merge-commit 6bb78de263aed35f09379c1fd6bd0909c3ae56cb.

G6 är demonstrerat: verkligt kvarvarande kompletteringsarbete avbröts vid en mätt
punkt, skrivaren verifierades borta efter inhämtning, och en färsk auktoriserad
mottagare fann och genomförde det återstående steget genom den dokumenterade vägen
utan facit. Underlag i qualification/G6-RECEIVER-TAKEOVER.json; det kasserade
försöket, avbrutet före varje skrivning, är bevarat och INTE tillgodoräknat.

Beslut och granskning för bedömningsidentiteten ligger i kontorets
`evidence/ap11/local/`: `assessment-2.md` (1cd959b9...) och
`assessment-2-review.json` (438eff30...).

OPUBLICERAD KANDIDAT, som nästa skrivare tar vid i:
  arbetsplats  .runtime/ap11/integrations/evidence-access
  gren         ap11/evidence-access
  kandidat     huvudet på grenen - en commit ovanpå basen. Exakt hash i
               `.runtime/ap11/claude-path/RESUMPTION-20260923.json`; en commit kan
               inte innehålla sin egen hash, och kandidaten bär denna plan.
  bas          origin/main = 6bb78de2
  status       OPUBLICERAD och OGRANSKAD

VAD KANDIDATEN GÖR. Den gör de obligatoriska värdkontrollerna till en del av den
verifieringsväg publiceringen faktiskt förlitar sig på, i stället för ett påstående
bredvid den. Kontrollerna ligger avsiktligt utanför det mönster publiceraren
upptäcker, eftersom en överhoppning inuti den körningen inte går att skilja från en
kontroll som tyst slutat köra. Följden, som oberoende granskning fann, var att
ingenting grindade på dem alls.

  - `scripts/run_host_checks.py` kör dem och skriver ett kvitto bundet till commiten
    publiceraren mäter, till modulens och basklassfilens byte, och till det bevarade
    scopets journalhuvud.
  - `publish_construction` VÄGRAR en runtime-publicering vars kvitto inte stämmer.
    Prövat, i den publicerade versionen, mot 25 manipulerade kvitton och 5 förhandsposter;
    alla vägrade av rätt skäl (`.runtime/ap11/claude-path/hostcheck-binding-20260923/`).
  - Kvittot är pinnat i `PREVIEWED` och i invokationsposten, så det inte kan bytas
    mellan torrkörning och skarp körning.
  - `required_scope()` använder värdens egen `Scope`-kontroll och förankras i DEN
    AKTIVA RELEASENS kontrakt - utifrån, inte i katalogen som prövas. En helkopia av
    scopet avvisas.
  - Skip-bindningen fångar anrop, `raise`, dekorator inklusive den enkla, tilldelning av
    klassattributet och en `load_tests`-definition. Några ovanliga former (annoterad
    tilldelning, `setattr`, aliasimport, `load_tests` bunden till en lambda) ser den inte
    statiskt; en sådan överhoppning fälls ändå av kvittots `skipped == 0` och av att
    svitens sista rad måste vara exakt `OK`.

VIKTIGT OM GRANSKNINGEN. Publiceraren ligger i `.runtime/ap11/build/`, UTANFÖR
kandidatrepot, så den syns inte i `git diff origin/main..HEAD`. Två granskningar i rad
avslog delvis för att underlaget inte nådde granskaren: först filer lagda platt medan
diffen pekade på `scripts/…`, sedan publiceraren som en fil bredvid i stället för som
egen diff, i en katalog granskaren inte kunde lista. Nästa granskning måste få
publicerarens ändring som EGEN DIFF, och varje fil på den sökväg diffen namnger.

Prov vid överlämning. Standardsviten: 384 prov, rent `OK`, inga överhoppningar,
`python3 -m unittest discover -s scripts -p "test_*.py"`. Värdkontrollerna:
`scripts/hostcheck_preserved_state.py`, 27 kontroller, noll fel, noll överhoppade,
körda med NR_HOST_ROOT mot primärutcheckningen. Kvitton i
`.runtime/ap11/claude-path/` och i `.runtime/ap11/build/ap11-hostcheck-binding-hostcheck.json`.
Ett rent `OK` från standardsviten ersätter INTE värdkontrollerna.

Drift- och förbrukningsläge. Tjänsten körs och ska fortsätta köra: daemon, Temporal
på 127.0.0.1:7339 och workern. Scopet står `paused` med skälet "Whole-goal review not
approved; preserve specific evidence gaps", 25 räknade anrop mot taket 48, båda
arbetena integrerade, `office-ap11` COMPLETED med `whole_goal_not_approved`. AP-10
orört. Inget skrivande arbete lämnat aktivt.

Bevarat, får inte skrivas över: grenen `ap11/assessment-path-history`, samtliga
publiceringskvitton och suite-loggar under `.runtime/ap11/build/`, och granskningarnas
råströmmar. Nya prov ska använda nya filnamn.

LÄGE VID TREDJE SKRIVAREN 2026-09-23. Överlämningen verifierades innan något skrevs:
kandidaten effc5799 med exakt de överlämnade byten, basen lika med origin/main, ingen
annan skrivare aktiv, tjänsten igång, scopet `paused` vid sekvens 112 med 25/48. Den
överlämnade kandidaten är bevarad på den lokala grenen `ap11/hostcheck-binding-handover`.
Publicerarens före-version (den som publicerade PR #43, sha256 3e48124e) fanns bara som
hash i kvittona; den är återställd ur efter-versionen och verifierad mot just den hashen,
och bevarad bredvid den överlämnade efter-versionen (c184d260) i `.runtime/ap11/build/`.
De tidigare granskningspaketen och råströmmarna är kopierade från den flyktiga
sessionskatalogen till `.runtime/ap11/claude-path/hostcheck-reviews-20260923/`.

Denna kandidat stänger, före granskningen, tre luckor i just den koppling som ska
granskas. Ankaret var fortfarande självrefererande en nivå upp: `required_scope()` läste
pekaren i den rot NR_HOST_ROOT anger, så en kopia av hela roten bar sin egen pekare. Nu
används värdens egen läsning av den accepterade bindningen, `release.installed()`, som
kräver att konfigurationen är den pekaren hashar och att den namnger just denna rot.
Publiceraren läste scopets huvud i den katalog kvittot själv namngav; nu måste kvittot
avse värdens eget scope under publicerarens rot. Och kvittot säger nu var den prövade
koden faktiskt importerades ifrån, vilket publiceraren kräver ligger i kandidaten.

NYTT HINDER, upptäckt vid övertagandet, och dess rättning i denna kandidat. Den globala
Claude Code-installationen uppdaterade sig själv 12:44:52Z (`npm install --global
@anthropic-ai/claude-code@latest`) från den kvalificerade 2.1.257 till 2.1.280. Eftersom
`qualified_binary()` slog upp `claude` på PATH vägrar D019:s pin nu varje Claude-roll i
den aktiva releasen, också den andra bedömningens enda räknade anrop (kontrollen sker
före reservationen, så ingen av de 48 förbrukas, men bedömningens nyckel skulle
förbrukas). Den gjorde också standardsviten röd, eftersom modellbindningsproven bygger
riktiga kommandon; publiceraren kör hela sviten, så ingen runtime-kandidat kunde
publiceras, och grinden kräver en värdkontrollöpare som bara finns i denna kandidat.
Rättningen hör därför hit: Runtime håller en egen kopia av exakt de kvalificerade byten,
`.runtime/bin/claude-2.1.257`, bredvid Codex- och Temporal-binärerna (D023). Samma hash,
samma version, samma vägran; ingen fallback till PATH; ägarens egen CLI lämnas orörd.
AP-10:s privata steg använder Codex och berörs inte av detta.

PUBLICERAT 2026-09-23: `ap11-hostcheck-binding` som PR #44, merge-commit
4c6789b9079fafa5f635eedbec8261a109df0f48 (kandidat d5c95980), efter en separat
skrivskyddad granskning som godkände utan blockerande fynd. Dess icke-blockerande
observationer har var sin motiverad disposition i granskarposten
`.runtime/ap11/build/ap11-hostcheck-binding-reviewer.json`.

PUBLICERAT 2026-09-23: `ap11-assessment-start` som PR #45, merge-commit
9ae9e5617a84c2aff73a8daad0f0fa01c297e85d. `assess` räknar NOT_FOUND för applikationen
den följer som stängd; varje annat motorfel stoppar fortfarande.

ÖVERGÅNG 8 AKTIVERAD av ägaren 2026-09-23T14:34Z (`executor-transition-8.py`, granskad):
release 9ae9e561 med konfiguration c1c539e7, `development.assessments` bunden till
`office-ap11-assessment-2`, Claude-kopian 2.1.257. Återläsningen var fullständig och
utan problem, AP-10-schemat ombundet. Scopet återupptogs 14:38Z med bokfört skäl och
den andra bedömningen startades 14:38:59Z.

DEN ANDRA BEDÖMNINGENS FÖRBEREDELSE VÄGRADES innan någon modell körde, och det är
bevarat: steget `preserved-delivery` passerade, men `final-review`-förberedelsen föll i
`development_final.prepare` med `[Errno 2] No such file or directory: 'acceptance'`.
Ingen reservation gjordes (fortfarande 25 av 48), ingen stegkatalog skapades, och
bedömningen väntar i `waiting_host_diagnosis` vid sekvens 2 - en otidsbestämd väntan som
bara ett värdsvar släpper. Orsak: kontorspolicyns `RECIPES` anger recepten relativt
kontorets rot (`acceptance/ap11_reconciliation.py`), men raden som PR #43 lade till läste
dem under `office/acceptance/` och dubblerade katalogen. Provets fixtur hade nakna
filnamn och kunde därför inte se felet.

KANDIDAT `ap11-final-review-recipes` (denna). Recepten läses nu under `office/` med
policyns egen relativa sökväg, precis som bygget läste dem (`development_host`), och
levereras under samma sökväg. Fixturen har policyns uppmätta form. Den verkliga
förberedelsen är körd med den rättade koden mot det verkliga scopet och den aktiva
releasen, med bara stegkatalogen omdirigerad: hela leveransen byggdes, 84 filer och
2 258 515 byte av 3 MiB, och scopet var oförändrat. Samma körning med den aktiva
releasens kod återskapade exakt driftfelet (`.runtime/ap11/claude-path/final-review-recipes-20260923/`).

NÄSTA HANDLING, i ordning:

1. Riktad granskning av denna kandidat och publicerarens nya profilrad.
2. Publicera under namnet `ap11-final-review-recipes` med nytt värdkontrollkvitto för
   commiten. Läs tillbaka integrationen.
3. Bygg övergång 9 ur övergång 8: pinna den nya revisionen, bär bedömningsbindningen
   oförändrad, kräv att bedömningen väntar orörd i värddiagnos, och pröva den nya
   releasens verkliga förberedelse mot det verkliga scopet utan att skriva i det.
4. Lämna ägaren aktiveringsbegäran. Efter aktiveringen besvaras diagnosen genom den
   granskade värdsvarsvägen (`continue`), och bedömningen fortsätter under en ny nyckel.

GENOMFÖRT (tillagt i efterhand, inget ovan ändrat): övergång 9 aktiverades av ägaren 2026-09-23T15:17Z, den
andra bedömningen körde som anrop 26 och gav inconclusive. Gällande nästa steg står i planens ingång överst.

A/B, den första helhetsdomen, samma åtagande och faktisk förbrukning bevaras. Taken
48/6 ändras inte. Ingen ny interaktiv start, reset eller ombyggnad av de levererade
arbetsdelarna. Mandatet för riktad granskning, publicering och övergångsförberedelse
består över skrivarbytet; invänta inget nytt körbesked.

Färska mottagare läser AGENTS.md, därefter denna plan, verifierar att tidigare
skrivare stoppat och inspekterar bevarat läge före varje skrivning.
