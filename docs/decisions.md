# Decisions

## D001 — 2026-09-19: clean project and engine-first compatibility probe

Observed: `/Users/elinhaggstrom/Nortropic Runtime` was empty and not a Git repo.
The requested private remote is `Nortropic/nortropic-runtime`; authenticated lookup
found no accessible repository with that name. Create new history, never overwrite.
Keep original mandate once in this directory. No older project imported.

First engine candidate: upstream `openai/symphony`, observed HEAD
`be10a1b79df723d6d7612b5651c8522704dafb2e`. Inspect pinned code, dependencies,
tracker and executor interface before installing. Do not reimplement SPEC.md.

## D002 — 2026-09-19: subscription-only executor checks

Observed outside sandbox: Codex CLI 0.147.0 reports ChatGPT authentication;
Claude Code 2.1.257 reports `claude.ai`, subscription `max`. No API-key/provider
environment override was present. Sandbox-only auth checks misleadingly failed
because network/keychain access was unavailable. No model run yet.

Claude is older than mandate's direct AGENTS support version. Use only `@AGENTS.md`
in CLAUDE.md and test actual loading at root and subdirectory. Global user settings
contain historic project permissions; these do not grant Runtime additional rights.
No global settings or hooks changed. Relevant managed settings still need checking.

Sources consulted: [Codex authentication](https://developers.openai.com/codex/auth/),
[app-server](https://developers.openai.com/codex/app-server/),
[AGENTS hierarchy](https://developers.openai.com/codex/guides/agents-md/),
[Claude memory](https://code.claude.com/docs/en/memory),
[Symphony](https://github.com/openai/symphony).

## D003 — 2026-09-19: distinguish backup from integration

Initial project records may be preserved before runtime acceptance. Subsequent
candidate deliveries need relevant verification and separate review. GitHub org
API reports Free plan. Server integration guarantees remain untested; do not
claim branch protection is enforceable until tested. A local review is not a
server permission boundary.


## D004 — 2026-09-19: private origin and local dependency updates

Private remote and first push verified; see evidence/startup. Server returns 403
for branch protection on the current Free organization. Owner asked about making
it public; recommended retaining privacy and GitHub Team (listed $4/user/month,
actual seats/tax must be confirmed in billing). Decision pending; no paid plan or
visibility change made. Sources: https://github.com/team and
https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches.

First Codex root probe failed: installed 0.147.0 cannot use requested gpt-6-astra.
Do not substitute model or repeat unchanged. Official release 0.155.1 will be
installed project-locally and checksummed before one new attempt. Global CLI and
other projects remain untouched. This is a technical prerequisite adjustment,
not new API billing.


## D005 — 2026-09-19: Claude subscription access is blocked server-side

Auth status was insufficient evidence. First real read-only CLI run returned
HTTP 403 `oauth_org_not_allowed`, saying the organization disabled subscription
access for Claude Code. Raw evidence: evidence/startup/claude-root. Reported usage:
0 input/output tokens, total_cost_usd 0. Treat the result's is_error=true and
terminal_reason=api_error as failure despite subtype=success. No repeat or API-key
fallback. Owner asked to check existing subscription access; remain WAITING_ACCESS
until changed evidence. Codex/engine work can continue independently.


## D006 — 2026-09-19: owner authorizes public repository

Owner explicitly said the repository need not be private and made it PUBLIC;
verified live with gh repo view. This supersedes the original privacy constraint
for this repository, not permissions to publish other projects or secrets. No
paid GitHub upgrade is required. Original mandate is retained unchanged as source.

Proposed main protection: PR required, no force push/deletion, administrators
included, up-to-date candidate, runtime/tests and runtime/review required. Zero
GitHub account approvals because separate agent review is issued by the trusted
host as an exact-SHA status; it is not a second GitHub identity. Separate agent
process is not itself a security boundary. Until restricted candidate access and
trusted status production are tested, this is only the server gate, not §5E.
Configuration: config/branch-protection.json.


## D007 — 2026-09-19: failed protection activation and corrected process limiter

First GitHub protection PUT returned HTTP422 because the payload supplied both
contexts and checks. A wrongly chained negative push continued and advanced main
from f2863df to 4dec677 before protection existed. This was an operator error and
is NOT approved integration evidence. No force push/rewrite was performed. Raw
outputs remain in evidence/integration/missing-checks-push.*. Corrected payload
uses only checks. PUT and verified readback succeeded; separate harmless same-tree
commit 3e894eef was rejected by GitHub (PR required; 2 checks expected), main
remained 4dec677. Future dependent mutation probes require successful checked
preconditions, executed separately or subprocess check=True.

Separate reviewer then found that bounded.py could leave TERM-ignoring children
alive and did not handle SIGTERM to the helper. Corrected shared cleanup checks
the process group even after leader exit, escalates KILL, handles INT/TERM, and
records removal before success. Three real-process regression cases pass (normal
leader exit, timeout, SIGTERM). Limit is configured run time plus up to 4 seconds
cleanup; children deliberately escaping the group and SIGKILL of the limiter are
not claimed covered. Review and remaining results must be tied to next candidate.

## D008 — 2026-09-19: narrow engine probe, no general replacement engine

Use unmodified official Symphony binary and GitHub adapter; wrapper only confines
its Codex protocol boundary and records the experiment. Remove github_api dynamic
tool because the available host token has broad rights. Disable desktop/app MCPs
in this invocation, retain global safety rules and subscription auth. Candidate
writes only isolated workspace, no network, no additional /tmp write roots.
Host hook independently checks known JSON and preserves before tracker transition.
One durable launch marker prevents blind model retries; a bounded experiment
launcher holds one lock. This is deliberately NOT durable production orchestration
or a claim that §5D/E are satisfied. Acceptance and baseline: docs/probe-b1.md.

Source inspection also identifies unresolved engine gaps: retry/blocked maps
initialize empty (orchestrator.ex:24–75); cleanup ignores before_remove failure
(workspace.ex:159–162,331–352); AgentRunner directly depends on Codex.AppServer.
After the small live probe, assess whether narrow integration can cover the mandate
or choose a smaller reuse route. Do not incrementally build a general replacement.


## D009 — 2026-09-19: B1 attempt 1 failed before model; bounded compatibility fix

Symphony found GH-1, created workspace, started app-server, called after_run and
preserved missing-result FAIL, then host removed dispatch label. No model turn
started: Codex 0.155.1 rejected upstream's legacy approvalPolicy reject (-32600);
its generated schema accepts never or granular. Raw traces are under
evidence/motor-probe-attempt-1. Engine returned 0 while verifier failed; no success
claimed. Process group removal measured true, no residual matching workers found.

Attempt 2 explicitly changes policy encoding to never (no approval requests,
sandbox retained), supported by generated 0.155.1 schema. Preserve attempt 1 and
record attempt=2 in the contract and launch metadata. No automatic retry; no
model usage in failed attempt. Same task, acceptance and artifacts remain.


## D010 — 2026-09-19: review discovers built-in MCP exposure in attempt 2

Separate result reviewer found cua_repl and codex_apps startup ready notifications
in the actual protocol, despite named MCP/plugin configuration disable flags.
Artifact and coordination proof remain valid; restricted-profile acceptance fails.
No completed MCP call appears. Profile is disabled in contract and launch paths.
Correct built-in feature flags (apps/computer_use/browser variants) per installed
CLI feature list, then query mcpServerStatus/list in a fresh thread without a
model turn. Do not rerun unchanged or describe intended isolation as observed.
Also corrected quota readout from initial 2% to final 3%, without attribution.

The first no-model correction removed codex_apps but still loaded plugin cua_repl
(evidence/startup/worker-profile-inventory.json). Disabling plugin loading for this
worker invocation, in addition to built-in app/browser/computer features, yielded
only three disabled named servers with zero tools; fresh-thread full inventory
passed (worker-profile-inventory-fixed.json), with no model turn. Global settings,
managed rules and hook configuration remain unchanged; this profile contains no
required safety plugin. The old fixture remains disabled; any later live profile
claim must refer to its actual invocation, not retroactively rewrite attempt 2.


## D011 — 2026-09-19: evaluate existing durable engine before more Symphony layers

The source gaps in D008 are core requirements, not failures of the fixture. A
Symphony-specific persistence/state/Claude orchestration layer risks becoming a
second general engine. Evaluate Temporal as a replacement candidate in one bounded
local no-model probe; do not run both orchestrators as the product or adopt a new
product scope. Same development task/permissions/subscription mandate remains.

Selected experimental dependencies: official Temporal CLI1.9.1 arm64 and Python
SDK temporalio1.33.0 (Python>=3.10). No extras, cloud account, subscription or API
usage. Local server supports an explicit SQLite persistence file; default without
that flag is volatile. start-dev is documented for development, not production,
and omits some HTTP security checks. Bind loopback and disable UI, no candidate
network access if later selected. Durability claim still requires actual restart
evidence; activity side effects and process fencing remain integration concerns.

Sources consulted: https://docs.temporal.io/cli/command-reference/server (flags and
development limits), https://docs.temporal.io/develop/python/best-practices/error-handling
(timeouts/retry policy), https://docs.temporal.io/develop/python/workflows/message-passing
(durable signals). Official release metadata and PyPI package metadata checked.
Decision is only to run a compatibility experiment, not yet to adopt the engine.


## D012 — 2026-09-19: select Temporal for next bounded execution slice

Comparison against required properties: Symphony has measured GitHub discovery and
Codex dispatch but volatile retry/waiting maps, no provider boundary, and cleanup
that proceeds despite failed preservation hook. Filling all three with host-side
state would duplicate orchestration. Temporal's existing history/signals/replay
preserved completed work and waiting in the actual abrupt-restart probe (9b770d1);
Python activities are a documented arbitrary executor boundary. This removes the
need to implement scheduler persistence or a general Codex↔Claude protocol server.

Choose Temporal for the next small Codex-connected task. It replaces Symphony as
the engine candidate, not a second running orchestrator. Reuse B1 learnings and
verified worker configuration; keep Symphony evidence and disabled experiment.
Task input remains accepted outcome/underlay/permissions/acceptance; native engine
workflow owns state. No second method schema/status registry or business logic.

This is limited technical replanning under mandate§2: same scope, no new billing,
no new external rights. Local pinned dependencies only. Existing dev-server SQLite
profile limits v0.1 to a single trusted local host if qualified; production is not
a promised goal. Candidate workspace isolation, attempt semantics, side-effect
reconciliation, independent review and exact GitHub integration remain to be built
and tested in narrow activities. Do not claim Temporal automatically supplies them.
If connecting those requires another generic engine, revisit instead of expanding.


## D013 — 2026-09-19: first useful accepted task and candidate boundary

Customer Zero task is a deterministic JSONL run-report CLI for actual provider
evidence. Current manual extraction and Claude success-subtype/error conflict
create a concrete false-pass risk. Use three meaningful implementation phases
(Codex parsing, Claude parsing, Codex final CLI verification), one workspace and
Temporal-owned task history. Claude phase waits on known server denial D005; no
API fallback or repeated denied call. The first delivery connects only Codex.

Use Codex's native named permissions profile with minimal reads, isolated workspace
writes and network disabled, plus disabled apps/MCP/plugins. Host acceptance and
GitHub authority remain outside candidate workspace. Test actual denial with
nonsecret canaries before a live turn. Official reference consulted:
https://learn.chatgpt.com/docs/config-file/config-reference (permissions filesystem
and network options); local 0.155.1 CLI/schema decides invocation compatibility.
No assertion of complete rights separation until observed, including escape routes.

The first thread preflight exposed a real compatibility error: restricted reads
blocked ancestor AGENTS discovery. Added read-only grants for AGENTS.md and
AGENTS.override.md at ancestor paths; no directory-wide host read grant. Fresh
thread now reports activePermissionProfile nr, writable roots exactly tools and
.scratch, no network/tmp writes, and only disabled MCP servers with zero tools.
The six harmless boundary checks also passed with this corrected profile. No model
turn was used for either inventory. Raw evidence: evidence/accepted-task/profile-*
and boundary-instructions.json. CLI sandbox syntax is `codex sandbox`, not the old
`codex sandbox macos`; the mistaken help invocation failed before doing any work.

## D014 — 2026-09-19: stop on verifier escape; preserve attempt and repair boundary

Separate review of f61b84d found a real host-write escape: candidate-owned
.scratch/sample.jsonl could be a symlink followed by host write_text. It also found
check/use races in candidate hashing/copying. Interrupted live attempt1 by SIGTERM
before acceptance, preserving raw events and source. Attempt result: interrupted,
34.166s, no terminal usage (unknown, not0), provider group removed. Workflow reached
waiting_diagnosis, attempt1 and same result survived server/worker restart. No
acceptance occurred and no provider completion claimed; all four engine groups
removed. evidence/accepted-task/engine and attempt-1 retain raw negative results.

Correction: pass CLI data through stdin, never host-write in candidate-owned paths.
Open every candidate path component with O_NOFOLLOW, require bounded regular fd,
read/hash those bytes and freeze them in a new host-owned evidence directory.
Execute acceptance against that snapshot with source read-only and no network.
Kill/reap verifier process groups on completion/timeout. Regression tests show CLI
stdin leaves candidate symlink target unchanged, frozen source write denied, and
symlink/file-parent/FIFO snapshot refusal. These are bounded host-file-handling
proofs, not a claim to fence deliberately detached hostile process trees.

Resume the SAME workflow/candidate only after correction review, with an explicit
native diagnosis signal carrying changed prerequisite. Attempt number increments
rather than restarting history. Driver checks old recorded PIDs/group absence.
No automatic repeated model attempt and no Claude call while D005 unchanged.

## D015 — 2026-09-19: owner defers Claude usage purchase

Owner plans to buy more Claude Code usage at a later time. Recommendation accepted
for work planning: no need to buy now to continue independent Codex, recovery,
review and integration work. No purchase, API fallback or periodic Claude calls.
Real executor swap and final v0.1 acceptance remain pending, not waived. Observed
server error D005 was oauth_org_not_allowed (subscription access disabled), not a
quota-exhaustion result; check correct account/organization access before assuming
additional usage will resolve it. Ask owner only when an actual access/cost choice
is needed, not for routine continuation.

## D016 — 2026-09-19: reuse publication checks, not old orchestration

Concrete need: reject stale/missing/failed review or test evidence at the actual
candidate publication boundary. Read only selected files in
/Users/elinhaggstrom/kernel-arbete at clean revision
2dfc58f362db100c179b7b738e9a720dae39a256:
- tests/scripts/nortropic-codex-autopilot/publication-callers.py
- scripts/nortropic-codex-autopilot.py publish/publication_authority sections.

Useful test ideas: every real publication caller supplies mandatory authority;
missing/wrong authority rejects; re-read exact base/head after push; final merged
tree must match tested candidate. Reuse these cases in Runtime-specific tests.
No old PASS imported; old tests were not executed. The old implementation depends
on its roadmap stages, canonical tasks.spec and normal two-parent merge, whereas
Runtime keeps acceptance outside candidate write access and uses protected linear
integration. Copying that engine would add irrelevant coupling. No source imported.
The briefly inspected nortropic-review.js is site/design/SEO-specific and has
multiple verifier fan-outs; it is not appropriate for this neutral small code task.
Originals remained untouched; no prior permissions/workflow mandates inherited.

Next slice: bind whole-task completion, tests and independent review to exact
candidate objects before any publishing action. A passed first phase must not
publish the unfinished report task. Keep its native WAITING_ACCESS state intact.
Then connect the same boundary to a second, Codex-only accepted task.

## D017 — 2026-09-19: connect a second useful task without waiting for Claude

PR5 integrated the separately reviewed publication boundary. Next connect it to
native workflow activities: accepted task input, bounded implementation, frozen
Git candidate, host acceptance, fresh independent read-only Codex review, then
protected publication. Existing report workflow remains waiting for Claude; it
must replay unchanged and must not publish as a completed task.

Second useful task will verify evidence file hashes with a small standard-library
CLI, replacing repeated manual backup/candidate hash checking. Its accepted scope
and verifier will be frozen before invocation. This remains Runtime development
Customer Zero, not a new method platform. Both tasks use the same DevelopmentTask
workflow and local Temporal engine. No new API billing/dependencies/permissions.

Generalize only task parameters and the missing reviewed activities. Preserve the
old workflow history using Temporal's native Replayer before running revised code.
A new central SQLite location may be established by backup after all writers stop;
retain original database, verify existing waiting workflow, and run only one local
server. Authority/test/review artifacts remain host-owned outside candidate write
access. A live automatic merge is not claimed until this wiring is actually run.

## D018 — 2026-09-19: prove bounded abrupt-worker recovery with existing primitives

Actual one-step task completed and automatically integrated via PR7; PR8 preserved
independently reviewed evidence/runbook. Next tested abrupt SIGKILL of a native
worker with a harmless sandbox provider under the real attempt guardian. Existing
flock, recorded-process inspection, guardian deadline, native history and retry1
policy prevented concurrent/duplicate execution; explicit diagnosis resumed the
same preserved work as attempt2. No new production recovery layer was needed.

An inherited-FD prototype worked mechanically but was rejected because candidate
tool descriptor exposure is not qualified. Keep authority outside candidate tools.
Do not claim arbitrary guardian SIGKILL/detached hostile descendants are covered.

One concrete service bug was exposed: preflight plain bind treated stopped-service
TIME_WAIT as active. Use SO_REUSEADDR like the actual listener, no SO_REUSEPORT;
real socket tests still refuse active listeners. Corrected native capacity-wait
restart passed with zero provider calls. Capacity was supplied as a known fixture
reason, not inferred from an actual vendor quota. Raw boundaries/limits and native
backups: evidence/recovery-probe/result.md. Claude D015 remains unchanged.

## D019 — 2026-09-19: qualified native Claude file-tool profile

Owner restored Claude and explicitly closed the interactive project writer.
Existing claude.ai/firstParty Max works with Claude Code2.1.257 and configured
model family claude-fable-5-1. No API key, new billing or changed global/managed
policy. Pin the observed binary SHA256 in runtime/claude_profile.py; a changed
binary requires qualification. No package update was needed.

Managed Bash sandbox is disabled, so use native --restricted with Read/Edit/Write
only, exact accepted-file Edit grants, dontAsk, empty strict MCP, no Chrome/slash
commands/plugins. Host runs tests after provider cleanup. Actual allowed write,
context/unaccepted denial, external read/new-write denial and symlink read denial
passed. Existing external/symlink writes stop at the read-first precondition;
the necessary reads are denied. These proofs cover this file-tool profile,
not arbitrary shell execution or a hostile host. Raw events and canary hashes:
evidence/claude-qualification/verification.json.

Automatic @AGENTS.md import passed from root but failed from tools/ because the
parent import is external to that working directory and existing consent is
absent. Restricted mode did not automatically inject project instructions.
Use the documented native --append-system-prompt-file pointing at the SAME
AGENTS.md source, preserving the default system prompt. Real tools-disabled probes
recovered its unique marker and plan path from both directories. No instruction
copy/sync system, trust relaxation, telemetry activation or hook policy change.
The fixture's instruction file is an isolated snapshot for a one-off canary.

Sources checked against actual CLI probes: official CLI reference
https://code.claude.com/docs/en/cli-reference (restricted/file prompt loading),
https://code.claude.com/docs/en/permissions (dontAsk and resolved file bounds),
https://code.claude.com/docs/en/memory (external-import consent).
Reported total_cost_usd is retained as CLI list-price usage metadata, not a claim
of money charged under the existing subscription. Initial failures remain visible.

## D020 — 2026-09-19: native access signal preserves the original task

PR10 qualified Claude without new billing/rights. Add execute_claude through the
same process guardian, lock, fixed deadline, frozen candidate, acceptance, review
and Publisher. Require pinned CLI and existing Max auth before invocation. Parse
one successful matching session/result with explicit false is_error, completed
terminal reason and exact qualified tool inventory; never trust subtype alone.

The report's original accepted base9278081 is stale after support deliveries.
A host-owned continuation explicitly changes that base and replaces phase-only
verification with the already accepted full contract. Outcome, ID, allowed paths,
provider order, prompts, attempt bound and zero automatic retries are immutable.
The original task JSON, native history, both attempts and old workspace remain.
A signal binds prior task digest + expected attempt2; a mismatched or duplicate
signal cannot reset/repeat work. Host freezes revised input/verifier outside the
candidate and verifies inherited files against the last preserved phase before
reconstructing the candidate on current base. Partial preparation stops for
inspection; no automatic overwrite/repair. New acceptance and base require
separate review before the real signal. This is an explicit acceptance-completion
step for the same outcome, not permission for candidates to change their tests.

Original brief required Claude usage dict and reported cost, but omitted cost
field placement. Clarify top-level total_cost_usd, preserving usage unchanged;
no new feature. A missing/nonboolean error flag cannot claim completed; the host
allows conservative other statuses instead of inventing a stricter classification.
Frozen partial Codex implementation fails full acceptance, as expected.

Temporal native Signal/wait_condition and Replayer are reused, no second engine:
https://docs.temporal.io/develop/python/workflows/message-passing and
https://docs.temporal.io/develop/python/best-practices/testing-suite. Selected SDK
remains1.33.0. Old report, completed evidence and recovery histories replay with
no activities/model calls. Separate native fixture exercises invalid/duplicate
signals and fresh worker reconstruction. These are structural proofs; only the
subsequent real execution can prove substantive Codex→Claude→Codex completion.

D020 pre-freeze correction: run candidate tests via unittest discovery, matching
their existing sibling import, with TMPDIR in the permitted .scratch directory.
Initial module-name invocation failed before testing code. Corrected isolated
baseline passes15 candidate tests and still fails16/33 full-contract observations.
Both raw runs are retained. Strengthen CLI status/usage/cost assertions before
freezing the new verifier. No implementation has yet been run against it.


## D021 — Bounded continuation after independent review (owner mandate)

The permanent waiting_review checkpoint gains two explicitly diagnosed actions.
A completed independent rejection bound to the current task/candidate, with
concrete findings, permits repair inside the same accepted task. Missing or
invalid review permits only re-review of the unchanged candidate. Every repair
must change candidate file bytes, pass the frozen whole-task verifier and receive
a fresh independent approval. All attempts, reviews and signals remain in native
history and numbered evidence; no automatic provider retries or engine change.

The host chain driver owns diagnosis and publication reconciliation, records the
next concrete action and proceeds within mandate without asking the owner to
relay technical reports. See runbook for stop/inspect/resume conditions. Existing
v0.1.0 tag and historical evidence are immutable. New proof explicitly separates
native engine/real Git/test processes from provider fixtures and remote publishing.
The next business task is qualified against its actual target; tools-only Runtime
scope is not a reason to relocate business source into this repository.

## AP04 — named Project Office target, owner accepted 2026-09-20

Owner AP04-ACCEPT in Nortropic/nortropic-projektkontor/docs/decisions.md permits
only the required office-target adapter, frozen inputs, instruction/write boundaries,
candidate/publication paths and relevant tests/docs. Existing histories/evidence
stay. Office business code stays in its repo. Start connection is separately reviewed
before Runtime builds office result retrieval through it. No additional targets,
accounts, billing, daemon or permissions. Existing Runtime protected integration
continues; office receives the same server gates. This is not a general hardening
mandate or resolution of historical audit findings.


## AP10-ACCEPT — shared local lifecycle and private Office observation

2026-09-21. Explicit owner mandate preserved privately by Office, SHA256
163a08b4fe9e55e37c4c5bb280576ecea663255975566b61af83780c386b734d.
Allows only named Office monitoring activation, persistent coordination and
private read/assessment completion after relevant review without code publication.
User-specific login start allowed; no root/new exposure/security changes.
Existing development gates and histories remain. Pin active code/config; make
pause/stop persistent; bounded model/reviewer/time/retry budgets per native round.
Office plan owns whole phase. Runtime implementation/review/integration and
limited public evidence allowed. No upgrades/new paid services/models/targets.


## AP11-EXECUTORS — 2026-09-21: executor-neutral roles, explicit choice, no fallback

Owner mandate recorded by the Office as AP11-UTFÖRARNEUTRAL (exact words preserved
privately there): the working model must never matter; both Claude and Codex shall
be able to drive everything. This is the separately accepted qualification that the
AP04 selector restriction was waiting for, and it restates mandate §1 Replaceable
execution. No new subscription, model connection, API billing or paid fallback.

Decision: executor choice is explicit per role and bound in frozen input — step
`provider`, optional `review_provider` (absent = Codex, preserving earlier digests).
Quota or access loss remains a persisted wait; nothing switches automatically. The
Codex route is unchanged. D019's pinned binary, subscription check and restricted
file-tool profile are reused; binary hash and auth status are preflight, not proof
of a new role.

Two bounded real pre-probes with the pinned CLI preceded the build. Reviewer role:
the read-only profile plus `--json-schema` exposes exactly Read and StructuredOutput,
cannot edit, is denied reads outside its workspace, and returns the verdict in the
single terminal's `structured_output`; an interrupted run has no terminal and an
invalid schema stops before any model call. Interactive role: a trust dialog whose
default is exit appears unless an ancestor is already trusted; trust is inherited;
the permission mode confines writes to the one granted file; `/exit` is disabled by
the profile and two Ctrl-C end the session with exit 0; the native record is
`~/.claude/projects/<cwd-slug>/<session>.jsonl`; `~/.claude.json` changes only
volatile bookkeeping, so a byte-hash guard on it would fail every honest run.
Reduced measured rows: evidence/claude-office-roles/review-terminal-shape.json.
Raw events stay in the private host area. Construction usage is reported apart
from the AP11 application ceiling, which stays 48 with 3 already consumed.

Limits: same-model author and reviewer are separate runs, not guaranteed independent
judgment. The Claude author cannot execute tests. Driver calls, the interactive
session and the private watch still use Codex until their own reviewed increments.
[The driver-call and interactive part of this sentence is SUPERSEDED by
AP11-EXECUTORS-2 below; the private watch statement stands.]

## AP11-EXECUTORS-2 — 2026-09-21: goal roles and the interactive session

Same owner mandate. `development.executors` in the frozen release configuration
selects `codex` or `claude` for each finite-goal role (interactive, driver,
preparation-review, diagnosis, final-review) and for the child task's author and
reviewer; absent is Codex. A misspelt or misplaced selection is refused instead of
becoming the default, and `freeze()` refuses a task whose author or reviewer differs
from the release's selection. Nothing in the repository writes that key: only a
separately reviewed controlled release transition does. Integration activates
nothing, and a selection is not a qualification: every role still needs its own real
run under the active release, accounted apart from the 48/6 application ceiling.

A third bounded pre-probe measured the two couplings the interactive route depends
on: the pinned TUI honours a host-chosen `--session-id` and names its native record
by it, for a working directory with a space and dots as well; and under
`--restricted` it loaded the delivered workspace instructions but not an ancestor
directory's project instructions. The host therefore reads exactly the record it
named and opens no other session. Quota or access is classified only from the
provider's own error status or wording. The provider-error row of an interactive
session is still unmeasured: it fails closed as an incomplete session.

Before a retry slot is bound, the scope resumed or the parent signalled, the control
command checks terminal, executor selection, subscription, trusted ancestor and
project-local layers; a bound call that never reached its consumed receipt is
delivered again instead of binding another slot. The authority comparison covers the
global keys and the delivered directory's own ancestor chain, because other
sessions, the operator's included, honestly rewrite their own entries meanwhile.

Limits: author, reviewer, driver and whole-goal examiner may all be the same model
family. They are separate runs with separate identities, never a claim of
independent judgment. The private watch keeps its Codex executor.

## AP11-GOAL-AMENDMENT — 2026-09-21: a reviewed goal amendment reaches every role

The frozen overall acceptance forbids another model and any fallback. The owner's
changed mandate narrows that, and the owner requires a reviewed amendment that is
traceable to the original and weakens neither the goal nor the final proof. A separate
review of the first draft found that the amendment was bound to nothing: the final
whole-goal examiner, and every driver and reviewer, would have judged a chain run by
the newly selected executor against the unamended text alone.

Decision: `development.amendments` in the frozen release configuration lists, by
SHA256, an amendment and its external review record, both stored with the frozen goal
in the release. The host delivers them, next to the goal and the authority, to the
driver, the preparation review, the diagnosis and the whole-goal examination, and
names them in the delivered context. An amendment has effect only with a record that
approves exactly its bytes as an amendment of exactly the contract's goal; changed
bytes, another goal, a verdict other than approved or a malformed selection are
refused. The contract and its hash never change, because the scope and its consumed
calls are keyed to them. Absent means none, with the delivered context unchanged. The
Office policy's exact source set is untouched. Nothing here writes that key or
activates anything: only the separately reviewed controlled release transition does.

Limit: the host checks that a review record exists and binds the bytes. It cannot
check that the review was good; amendment author and reviewer may be the same model
family, which the record itself must state.

## AP11-HISTORY-BOUND — 2026-09-21: a waiting parent must survive its own polling

Measured on the real paused finite parent: its five second wait cycle costs about eleven
native history events (one short activity, one timer and their workflow tasks), so the
execution reached 32 000 events in 4 h 20 min with no work done. Measured with the pinned
engine CLI on a throwaway engine: an execution is terminated at its history count limit
("Workflow history count exceeds limit"; default 51 200). Measured by replaying the real
history locally: a full replay took 10 s, the whole default workflow task timeout, so a
restart, including a controlled release transition, could no longer be relied on. A
terminated parent cannot be started again under its reject-duplicate identity.

Decision: every wait cycle of the finite parent (interactive wait, control wait, following
a child) uses one 30 s interval; capacity and evidence waits already did. The recorded
history replays unchanged under the longer timer (verified by replaying the real 33 802
event history against this code). The local engine is started with an explicit history
safety margin (count 200 000, size 128 MiB). That margin changes no model, attempt,
schedule or business limit. Latency cost: the parent notices a finished interactive
session or child within 30 s instead of 5 s.

Limits: this bounds growth, it does not remove it (about 1 300 events per waiting hour,
more while following a child), and replay time still grows with history: keep waits short,
and treat a very long history before a planned restart as a condition to resolve first.
Signal-driven waits or continue-as-new would be the structural remedy; both change
workflow structure and are deliberately not part of this increment. An already grown
execution is not shrunk by new code: that needs an operator's native reset, which
preserves the old history and is recorded separately.

## AP11-PAUSE-WAIT — 2026-09-21: a pause is waited for, not polled

Owner requirement: before AP11 is called finished its pause and wait state must be able
to persist without recurring manual history rescue, by the smallest sufficient use of the
engine's existing mechanisms; no new engine or platform. With 30 s polling a pause still
costs about 32 000 events per day, and the measured point at which a cold restart stops
being safe (about 25 000 to 30 000 events, the ten second workflow task timeout) is reached
within a day, far below the explicit engine margin.

Decision: the two waits that can last days, the control wait (paused, quota, exhausted) and
the wait for the host's whole-goal evidence, are no longer polled. The parent waits for a
data-less native signal, `host_state_changed`, with a six hour fallback timer that keeps it
live if a signal is ever lost: about 44 events per day plus about 12 per pause, resume or
wake, so from a history of N events (25 000 - N) / 44 days of an untouched pause before a
restart stops being safe; more than a year from a small history. The control command sends the signal, best effort,
after `pause` and `resume`, and a new explicit `wake` action sends only the signal. The
signal carries no data, changes no state by itself and starts nothing: the parent merely
re-reads the host's control, which stays the only authority. `status` never signals. The
wait for the interactive session stays host-polled at 30 s, because no signal may follow a
session's exit, and that wait is bounded by the session itself. The same native command (a
timer) is recorded as before: the real preserved 36 684-event history of the running parent
and a recorded 44-event fixture replay without failure, and the repository now replays that
fixture offline with a negative control.

The wake flag is cleared before the host step reads the state, never at wait entry. A
separate review measured why: a resume whose signal was processed while a host step that
had already read "paused" was in flight was dropped at wait entry, and the parent slept
on a fresh fallback timer. With the flag cleared before the step, such a wake ends the
wait at once and the control is read again (shown on a throwaway engine with a slowed
step: noticed, not missed). The control command writes the scope control before it
signals, and reports whether the engine accepted the signal.

What has been shown, and what has not. Shown on throwaway engines with the real parent
code: no history event during 60 to 75 s of pause; a restart of worker and engine adds
none and the pause persists; resume and wake are noticed within a second after such a
restart, also through the real control command and the real host step on a synthetic
scope; a 30 s engine timer survived an engine restart and fired into the fallback path;
an accepted signal survived a worker stop and an engine restart. NOT shown: any rest
longer than 75 s, so nothing here proves long or unbounded event-free waiting; the six
hour timer firing at its real length; a restart while a signal call is still in flight.

Limits: not unbounded. Continue-as-new would be, but it needs the parent's position and
carried results to become resumable state, which is a structural change this increment
deliberately avoids. Following a child still polls at 30 s (about 2 000 events per hour):
bounded by the child, not by this change. The six hour timer is the ONLY automatic
recovery from a lost signal; otherwise the operator repeats `wake`, and a status that
shows the scope active while the parent still waits in control is the sign. A paused
parent that wakes while capacity is unobservable polls at 30 s until capacity returns.
Nothing signals when the host preserves the whole-goal evidence: the operator runs `wake`
afterwards, or the examination starts at the fallback. Forward-only: once this signal has
been processed, the history no longer replays under earlier parent code, and the signal
must never reach a parent still served by an earlier worker (measured: the new code
cannot replay such a history); control command and worker change together, through the
release transition only.

## AP11-DAEMON-HISTORY — 2026-09-21: a daemon start must survive the engine's retention

Found by a separate review of the release transition and confirmed by reading: at every
start the daemon queried three delivered task executions on the engine and refused to
start if a query failed. Measured: the local engine's namespace retention is one day, and
the engine had already removed the first of the three; the other two were hours from
removal. From that moment neither the active release nor any stageable one could start
again after a stop, and a transition's promised return to the previous release was
impossible. The running service kept working only because it was not stopped.

Decision: the requirement is stated once, in `delivered_histories`, which the daemon calls
at every start and which a controlled release transition calls against the running engine
BEFORE it stops the service. The engine is always asked first. Only for an execution the
engine answers not-found for, the delivery is evidenced by an archive that the release
itself binds: run id and SHA256 in the pinned configuration, the bytes inside the release
under its file map, and the archived history must itself show that execution by name, that
run of the task workflow, closing with the completed phase the live query would have returned. No binding,
other bytes, another run, another workflow type or another outcome refuses the start; any
other engine error is not mistaken for retention. What the daemon observed is written
beside its launch record, not into the service receipt.

Limits: an archive proves what was delivered, not that the database is the same one. The
earlier live query also tied a start to the established database; once the engine has
removed those executions that is lost, and nothing at daemon start then distinguishes the
established database from another intact, non-empty database at the canonical path (the
native service identity cannot: the daemon creates it when absent). A current-source
continuity anchor that never expires is a separate, later increment. Nothing in the repository writes `historical_archives`: only
a separately reviewed controlled release transition stages verified archives. Executions
of a release activated before this change cannot be started again at all.

## AP11-DISCOVERABILITY — 2026-09-22: a delivered file the reader cannot find is not delivered

Measured on the third interactive retry of the AP11 application: the restricted
interactive Claude profile (Read and Write, one scratch grant, no directory listing)
opened the seven files that CONTEXT.json named, then tried some fifty guessed names, and
answered `hold` because the verification recipe and the result readers were "missing".
They were present: VERIFICATION_RECIPE.py, tools/kontor_result.py, tools/agarbild.py and
AGENTS.md were delivered and bound by the host (input.json workspace_sha256), but no text
the reader could see named them. The earlier Codex driver had listed the directory with
its shell. The stop was controlled (the parent waits for host diagnosis), the cause is
the host's context delivery and its fit with the restricted profile, not a missing
mandate and not a candidate fault in A. The third retry stays as it ended: completed,
hold, its answer and traces untouched.

Decision: every workspace the host delivers carries, inside CONTEXT.json, the host's
existing file binding restated as `delivered_files`: every delivered file with its exact
workspace-relative path, SHA256 and size, plus named entries for the frozen recipe, the
result readers, the instruction file and the answer schema. It is built at the single
delivery point (prepare_call), so the driver, the preparation reviewer, the diagnosis
role and the whole-goal reviewer all read through it. The inventory is a finding aid,
not authority: the meaning of authority, goal, amendments and observation still comes
from `sources` and `goal_amendments`, which the Office policy keeps exactly as before.
The Office policy's common role instructions name the files and the limit of the tools
(a separate Office change). Nothing is added to the profiles: no listing tool, shell,
network or write grant. Hold remains the right answer when source or authority is truly
insufficient; the model is not told to always propose.

Measured with the actual profiles on a synthetic workspace shaped like a real delivery,
every file carrying a random marker (qualification consumption, separate from the
application; no draft of A, no answer key): the interactive profile opened all ten
inventoried files and reported every marker, twice (the second run also through the
one writable answer file); the print profile with Read and structured output reported
every marker; with the recipe listed but absent it reported that path as unreadable
and invented nothing. The host's own binding refuses a missing or changed delivered
file before any model call, as before.

Owner decision of the same day: one further interactive start for this commitment,
interactive-retry-4, after the third retry ended correctly with hold. It exists only
when the active configuration binds the owner's decision document and its separate
review (`development.interactive_extension`), and only after a third retry whose
result is completed with the answer hold: the binding carries the SHA256 of that
result and of that answer, so nothing of the earlier session is rewritten, and a
different decision does not fit the binding. Four consumed calls, the ceilings of
48 model calls and 6 implementation attempts, every identity and the journal stand.
It is not a general retry right: no fifth start exists, and a next stop is preserved
as it falls. The whole-goal reviewer receives the hold answer and the fourth binding.

Limits: the probe used synthetic contents; the real fourth session is a real run. The
interactive profile still cannot list directories by design; a file that no text names
remains undiscoverable, which is why the inventory is complete by construction.

## AP11-PROMPT-DELIVERY — 2026-09-22: the host must hand the provider its whole prompt

Measured on the live application after the host-recovery release was activated. The host answer released the wait,
the parent re-diagnosed, the diagnosis produced a continuation and the child re-ran its review — the chain moved.
Review 2 then ended exactly as review 1 had: exit 124, `interrupted: deadline`, at 302.0 s under the raised 300 s
bound, with a **zero-byte event stream and an empty stderr** while the process had started. Review 1 did the same at
182.2 s under 180 s.

So the raised review bound did not solve this cause and was never going to: it turned 182.2 s into 302.0 s and
changed nothing else. The frozen bound is left exactly as it is — not reverted, not quietly adjusted — because it is
a separate, reviewed decision about how long a review may take, and nothing here contradicts it.

What the cause is, measured rather than reasoned. The same invocation, the same workspace and a prompt of the same
shape and size (19777 bytes) answer in seconds when the prompt is written and stdin closed up front: init at 2.0 s,
the assistant producing within 9 s. The account's quota was not blocking. So the invocation, the prompt, the
workspace and the quota are all sound, and the difference is how the host delivers the prompt. `attempt.py` handed
it over with `communicate(first_input, timeout=min(1, remaining))` inside a one-second polling loop, setting
`first_input = None` after the first `TimeoutExpired`. If that first call's timeout fires before the write has
finished, the rest of the prompt is never written and stdin is never closed — so the child waits for an EOF that
never arrives, emits nothing, and is killed at the deadline. Reproduced without a model: a child that reads at once
receives the whole payload on the first pass; a child busy for three seconds first receives nothing at all, thirty
one-second passes in a row. CPython issue 141473 describes the same mechanism. Neither that issue nor the
reproduction is treated as proof that this correction works; the tests exercise the corrected function itself.

Decision: one `transfer(proc, payload, command, seconds, started, control=None)` does the delivery for both the
scope-reserved and the plain run. It writes to a non-blocking descriptor, one write per pass, closes stdin as soon
as the payload is exhausted, and only then waits. The delivery is deliberately NOT a blocking write: it stays inside
the run's own `seconds` and re-reads the scope control on every pass, so a stop is honoured while the prompt is
still going out and a child that never reads is ended by the run's own deadline rather than by anything new. A child
that ends early surfaces as a broken pipe, its own result decides the outcome, and process cleanup is unchanged.

A separate review then reproduced the defect in the LIVE output shape — the recorded reproduction had used a piped
stdout, which is not what `execute` does — and measured the number that makes it fatal: a subprocess stdin pipe
stalls at 16384 bytes on this host while `communicate` writes it in 512-byte chunks, so the 19777-byte review prompt
was just past the ceiling and 3393 bytes were abandoned. A prompt below that ceiling would not have failed, which is
why the implementation run on the same task succeeded. The same review found three things wrong with this
correction's own work, all fixed here: a stop signal arriving during the stdin close was swallowed, because
`InterruptedError` is an `OSError`; a comment claimed a child that ended always surfaces as a broken pipe, which is
untrue when a descendant still holds the read end; and the single most important property had no red guard, since
neutering the non-blocking write made the suite hang rather than fail.

Tests: `scripts/test_prompt_delivery.py` (9), all with model-free children and a payload well past where a stdin
pipe stalls, so a delayed transfer is really exercised rather than a message that fits in one write. Every run is
bounded by its own watchdog, so a delivery that blocks fails instead of hanging the suite. A child that reads at once
and a child that starts late both receive a byte-identical payload and an EOF; a child that never reads meets the
run's deadline and is reaped; a child that exits early is not recorded as the host failing; a stop during the
transfer is honoured; a paused scope keeps sending, because a started run may finish. One of them drives the real
`execute` path with a model-free provider, because `transfer` being correct is not the same as the run using it —
a mutant that emptied the payload at that call site survived the whole suite until that test existed. Nine in-place mutants, all killed,
each by a test that names the broken behaviour; the guard against swallowing a stop signal is measured directly,
without a child, so it cannot pass or fail by ordering.

Limits: this corrects the delivery, not the review itself. What it makes possible is that the real review process
receives its whole brief and returns a judgeable verdict. A rejection with concrete findings is a working review
result; nothing here is aimed at producing an approval. The earlier reviews 1 and 2 stay preserved as incomplete,
and a missing review stays a missing review, never an approval.

## AP11-HOST-RECOVERY — 2026-09-22: a host failure is named as one, and the host can answer its own diagnosis

Measured on the sixth and last approved interactive start: its task's candidate passed the frozen acceptance recipe,
and the separate review was then killed by the host guardian at 182.2 s against a 180 s model bound (exit 124,
interrupted deadline, an empty event stream) and produced no verdict. The parent `office-ap11` has stood in
`waiting_host_diagnosis` since, at sequence 12, with the child `ap11-step-5` in `waiting_review`; twelve of the
forty-eight calls are consumed and no approved interactive start remains. `interactive-retry` is itself refused while
the parent has a child, so this wait had no exit at all.

The diagnosis answered `hold`, correctly, and said in its own words what it lacked: the review run's own evidence
directory, so that the cause of the deadline hit could be told apart from a provider stall; a resolution of the
host's `waiting_reason`, which read `Stale or mismatched evidence: task_id` and described an identity mismatch where
a host interruption had happened; and the readers the frozen goal names, which every other role receives and it did
not. All three are host defects in how the host describes itself and what it hands the role that must judge.

Decision.
1. The review model bound is derived (`model_seconds`) and raised from 180 to 300 s for a task carrying the finite
   development binding, inside the unchanged 360 s activity envelope and never above the task's own attempt bound;
   a task without that binding keeps exactly its former bound.
2. `require_gate` checks completeness and scope before identity and names them, so an unfinished review reads
   `Mandatory review evidence unfinished or wrong scope: incomplete`.
3. The diagnosis receives `host_bounds` (the bounds of the ACTIVE release, stated as `undetermined` rather than
   raising, because a diagnosis must never fail because the host could not describe itself), the host's own earlier
   answers as `HOST_DIAGNOSIS_ANSWERS.json`, the host's own record of each recent review run as
   `review-N-run.json`, the same record for each recent implementation attempt as `previous-N-run.json`, and the
   readers the goal names. The raw run files are deliberately not delivered: the event stream's name is not one the
   delivery point accepts; `launch.json` carries the host's own account state, absolute host paths, the provider argv
   and process ids; and `result.json` carries the provider's own usage, denied tool calls, thread id, reported cost,
   the run's evidence path and its scope reservation. The record carries the bound that applied, how long the run
   took, how it ended, the stream's size in bytes and, when the host can read it, its line count. An empty stream is
   reported as empty, because the emptiness is the evidence. Three provider-written values are reduced rather than
   delivered: `permission_denials` becomes a count, because its tool input is the interrupted model's own text and
   was measured on this host to contain an absolute path; `usage` becomes a boolean; and `interrupted` is passed
   through only when it is one of the host's own words, because the host sets it to the text of an OSError on a
   failed start, which also carries an absolute path. A run the host cannot read is reported as unreadable rather
   than omitted, so the diagnosis can tell that from a run that never happened, which yields no record at all. What
   this bounds is the record; it is not a claim about the whole workspace — see Limits.
4. `development_control continue --reason "<host fact>"` signals the existing `continue_after_diagnosis` and then
   records an append-only answer with its parent phase and sequence. It requires the parent to be in
   `waiting_host_diagnosis` and the goal to be active, it starts no work and resumes nothing, and it is an operator
   intervention, recorded and reported as one, never evidence of autonomous continuation.
5. A recorded host answer lets an interrupted review be re-run. `recovery_request` returned `hold` for everything but
   `repair`, because free model text cannot establish that a host prerequisite changed. A host answer is not model
   text: only the host operator's own command writes it. Where a readable answer bound to this child exists, a
   `review_only` diagnosis may continue — the model still decides the action, the host must still measure the wait
   the same way, and the continuation is bound to the ANSWER, so one host fact authorizes exactly one continuation
   and a second re-run needs a second host fact.

The host answer is therefore a real operator-to-model channel that unlocks a re-run, and is treated as one: its text
is bounded at 8000 characters, an answer that cannot be read back is reported as unreadable and states no fact and
authorizes nothing, an answer bound to no child is never delivered as a fact about one, and every answer is part of
the whole-goal evidence as `HOST_ANSWERS.json`.

Found before review, by reading the path the chain would actually take: `recovery_request` binds a returned diagnosis
back to the observed wait by comparing the workspace context, so the new context keys would have refused every
non-hold diagnosis — the class review C measured when the delivered-file inventory was added. `DIAGNOSIS_HOST_KEYS` is
now the single place the delivery point and the binding agree. Two separate reviews then rejected the first candidate
and are answered here: an unbounded answer could write a file `read_regular` refuses, which made `host_answers` raise
for the whole scope and took every future diagnosis with it, while the only command out of that wait read the same
directory (so the live goal could not be recovered from inside itself); the answer was recorded before the signal was
accepted, so an undelivered signal could leave an answer that authorized a continuation the parent never heard of; an
answer recorded before any child existed carried a null task and was delivered to every later child as a fact about
that child; and `record_host_answer` created its directory without the symlink guard its reader applies.

Replay safety, corrected: not every change is outside workflow context. `require_gate` is called from the child
workflow, and its reorder is a control-flow change, not a message string. The raise predicate is unchanged — the old
order is reimplemented in the tests and compared against the real gate across the whole space the reorder touches —
so the same branch is taken and no command differs; only which message is raised changes, and that message is
query-only state (`waiting_reason`). It is observable: on the first replay the preserved child's `waiting_reason`
changes from the old sentence to the accurate one, and a host-written observation taken afterwards differs from
`step-12` for a child that did nothing. That is host-caused evidence drift, recorded here rather than discovered
later. Measured rather than argued: both live histories (`office-ap11`, 1745 events; `ap11-step-5`, 16 events) were
fetched read-only and replayed offline against this candidate, and against the active release as a control. All
passed. The histories are preserved under `.runtime/ap11/claude-path/host-recovery-20260922/live-histories`.

Tests: `scripts/test_host_recovery.py` (44) through the real review activity, the real gate, the real delivery point,
the real recovery binding and the real control action. One test runs the real `diagnosis_call` and then hands the
names it actually built to the real, unpatched `prepare_call`, so the rule is owned by the code that enforces it
rather than restated in the test; others stage review and implementation results, and both causes of a failed
acceptance — the two branches the LIVE recipe actually returns, the host's own raising, a candidate the verifier
cannot finish on, and a record from before the markers — and pin `RUN_FIELDS`, `ACCEPTANCE_FIELDS`, `VERIFIER_FIELDS`
and the host's interruption vocabulary to exact literals, so any field added to a whitelist fails there. Both
branches of `execute_implementation` are measured, because both were changed. One drives the real
activity and reads back the record it wrote, because a mutant that removed the host's own cause marker had been
"killed" only by an unrelated timing test — nothing was actually holding it. Those assertions replaced one derived from the
whitelist itself, which review L proved was a tautology by putting the provider's reported cost back on it with
every test still green. Sixty in-place mutants
against the new guards, all killed, recorded in
`.runtime/ap11/claude-path/host-recovery-20260922/mutants.json`; the survivors along the way each showed a guard that
was not measured where it acts — the raised bound, the run record, the readers, the answer numbering, the field
whitelist, the pre-signal refusals and the unreadable-run report. Whole suite 238.

Seven separate reviews rejected earlier candidates, each on something that would have acted on the live chain rather
than on style. The record of what they found, and of what closed it, is kept beside the measurements in
`.runtime/ap11/claude-path/host-recovery-20260922/`.

The whole delivery path was then measured as one chain, with the REAL revision-bound recipe executed on real
candidates in an isolated area — nothing in it asserts what that recipe returns, because it is run and its own bytes
are carried forward (record: `.runtime/ap11/claude-path/chain-proof-20260922/chain-proof.json`; recipe
`1ff7338e…`, the acceptance identity of the live child). Four courses, each through the real `run_verifier`, the real
wrap, a real `acceptance.json` on disk, and the receiver's actual workspace written by the real `diagnosis_call`
through the real `prepare_call`:

- the real candidate that passed: the recipe passes it in 0.2 s, the host marks it passed, the receiver reads that;
- a candidate whose code raises: the recipe's own output names an absolute host path, the host marks it a verifier
  rejection, and the receiver's workspace does not carry that path;
- a candidate that prints at import, so the recipe cannot parse its own result: a verifier rejection, not a host
  failure — the branch whose exact `{'passed', 'reason'}` shape a shape test had read as the host's fault;
- a candidate that never returns: the recipe's own 120 s timeout fires, and the host marks a verifier rejection,
  because a candidate that hangs is the candidate's outcome. The receiver is told the verifier did not complete, not
  that it ran and rejected the candidate.

Each course runs through the real `execute_implementation`, so the clause that sets the marker is the shipped one;
only the model call and the Git freezing around it are stood in for, because this harness has no model and no
candidate commit. What the recipe raises is carried forward as the exception object itself, and the record states
when a raise would have escaped the host instead of being caught. Review L found both of those simulated, which
would have proved the correction's outcome with a substituted exception and a copy of the very clause under test.

The last link, through the real recovery path: a correct diagnosis of a candidate finding, an answer claiming a
change it cannot show, and an answer naming an action the host did not measure all fail to produce a continuation —
the first two hold with "model text is not recovery authority", the third is refused outright. Missing or
insufficient material never yields a positive outcome. The host-failure branch of the same marking is measured at the
activity itself rather than here, because a host tooling failure has no recipe result to carry.

A third review then rejected the corrected candidate and is answered here too. Delivering the raw run files would
have refused every diagnosis of a child that has a review attempt, before any model ran: `prepare_call` accepts only
`.md`, `.json` and `.py`, and `events.jsonl` is none of them — the chain would have stalled permanently on activation,
and the test written to prove the name check survived had staged a name the code cannot build. The continuation was
bound to the whole review record, which a re-run rewrites (new attempt number, evidence path and reservation nonce),
so one host answer could have authorized an unbounded chain of automatic re-runs until the terminal call ceiling. And
because the signal is now sent before the answer is written, a refusal at the write would have consumed the
operator's one continuation while reporting failure, so every refusal runs before the signal.

Honest limit on the confidentiality of the diagnosis workspace. The records above are bounded, and so, now, are the
implementation attempts: `previous-N-result.json` was a raw copy of the provider's own result and carried every field
the review record excludes. Nothing binds those files, so they could be narrowed and are. One carrier remains and is
not narrowed: `CONTEXT.json`'s `actual_child_wait` is the child's own state exactly as the diagnosis must bind back
to it. Measured in the live workspace of `step-12`, that state carries the run's evidence path, its scope reservation
nonce, a usage object and a reported cost. `recovery_request` compares the returned context against that same state,
so filtering it would refuse every non-hold diagnosis. It stays as it was before this release, and the workspace as a
whole is therefore not free of host path or reservation material. The host's verdict on the frozen acceptance recipe
is narrowed too, and this is where review L found the sharpest defect of the whole release — in a correction of mine.
A non-pass has two causes, and the host recorded them identically: its own tooling raising (`str(error)`, and a Git
error stringifies the whole command, so it names host paths) and the frozen verifier rejecting the candidate. The
first version of this narrowing collapsed both into one sentence saying a failure there is the host's tooling
failing, never a finding about the candidate. On the commonest path into a diagnosis that sentence is false, and it
was worse than the raw file it replaced: the diagnosis lost the verifier's findings and was told the opposite of the
truth, in the one role whose whole job is that distinction. The host now marks its own cause where the failure
happens, and carries it through the wrap. Review L then measured the replacement against the LIVE recipe and found
the same inversion from the other side: that recipe returns exactly `{'passed', 'reason'}` on one of its own
rejection branches, which the shape test read as the host's failure, and returns up to 6000 bytes of raw subprocess
stderr on the other, which the new field delivered whole — reopening the leak in a new place. So the shape test is
gone entirely: `activities.py` now marks BOTH causes where each is known, and the delivery reads the marker. A host
failure delivers the verdict, the candidate hashes and the withheld sentence — which says the host's own tooling
raised and that this is not the verifier's verdict, without claiming it can never be about the candidate, because the
same `try` also catches a candidate that wrote outside the paths its task allows. A rejection delivers the verifier's
own verdict fields, whitelisted by `VERIFIER_FIELDS` and bounded, and its note separates a recipe that ran and did
not pass from one that did not complete at all, since `run_verifier` also catches a recipe that never started. A record written before either marker existed says its
cause is unrecorded and delivers neither text, because asserting a cause the host did not record would be an
invention. Two named carriers remain, by decision rather than oversight: `actual_child_wait` above, and the frozen
verifier's `checks` and `scope` on the pass path, which are the recipe's own words rather than the host's.

Limits: the raised bound is a measured margin over one cut-off review, not a proof that every review fits; a review
that exceeds 300 s is still an honest incomplete. Each `continue` spends one of the 48 counted calls through the
diagnosis it triggers, and that ceiling is terminal. The opening is for an interrupted review only: a
`waiting_diagnosis` retry still requires host recovery, and `repair` still requires an independently bound rejection.
The host answer is not matched to a particular review number or candidate: it authorizes one continuation of whatever
interrupted review the child is waiting on.

## AP11-ANSWER-CONTRACT — 2026-09-22: what the receiving policy enforces is stated where the model reads

Measured on the fourth interactive start (the single extra start after the hold): the driver found every
delivered file through the inventory and answered a concrete task for A, and the frozen Office policy
refused it on one field: `depends_on` carried an explanation ("none: first task of the application …")
where the policy requires the empty string for A. The delivered schema allowed any string and the
instruction said "explain the dependency"; the Codex driver of the first retry had written the same kind
of prose. Two drivers, one reading: the host's delivered text did not state the host's own rule. The
parent picked the session up by itself and stopped controlled in the host diagnosis wait; the answer,
session, refusal and consumption are preserved as they fell.

Decision, Runtime side: the delivery point hands the Office policy the WORK it prepares, so the instruction
and the answer schema are delivered per work (`instructions(role, work)`, `schema(role, work)`); the
Office policy states one contract in both and enforces exactly it in `prepare()` (a separate Office change).
The single extra start becomes an ordered list of separately reviewed owner decisions
(`development.interactive_extensions`), each bound to the start it follows and to how that start really
ended: `hold`, or `task-refused` (a completed session whose task answer the host produced no draft for).
The previous session's result and answer are bound by SHA256 and never rewritten; a decision that names
the wrong ending does not fit; the chain has at most two entries and no further start exists. Whole-goal
evidence carries every followed ending as answered.

Measured before the next start, with the candidate's real functions on an isolated area: the two preserved
prose answers are refused with the stated reason and violate the A schema; a controlled copy of the fourth
answer with the field emptied passes policy, AP06 preparation and Runtime validation (a test copy, not a
delivered task); synthetic A and B pass; an explanatory, invented or premature dependency, a hold, and
every field rule the text now states are refused. With the actual restricted profiles on a separate
synthetic probe goal, the unedited answers of the interactive profile and of the print profile (whose
pinned CLI accepted the per-work schema) passed the whole receiver path. Qualification consumption: two
Claude model processes, separate from the application.

Limits: the interactive answer file is not schema-checked by the host (the policy is the enforcement, as
before); the fifth start is a real run under the corrected release; five calls of forty-eight are consumed.


## D022 — 2026-09-22: the model is an explicit release choice, checked against what actually ran

D019 qualified the native Claude profile with a configured model family and pinned the binary by SHA256.
The model was a source constant used BOTH to build every command and to verify the identity the provider
reports back, so changing it meant editing source and re-qualifying the profile each time.

Owner decision of 2026-09-22: finish AP-11 with claude-opus-5 through the existing qualified installation,
make only the model binding that requires, and keep it reusable so the next change is a configuration
value rather than another source migration. The global CLI is NOT updated in this step; D019's binary pin
and version check stand unchanged.

The selection is part of the frozen release configuration, `development.models.{claude,codex}`, resolved by
`development_model.models(config)`. It mirrors `executors(config)`: a per-executor choice, changed only
through a separately reviewed controlled release transition, and it refuses rather than defaults. Unknown
executor key, a singular `model` key at either level, and any name that is not a plain provider model id
are refused before reaching an argument list.

D019's identity requirement is not relaxed. `provider_result.parse` compares the provider's own reported
model against the SELECTED one, an unbound call still demands the profile's own model, and the CLI version
check is untouched. A run reporting a different model than the one chosen is not a valid terminal. Because a
release that changes only the selection keeps the same runtime_revision, which previously implied the model,
the run record now states both the model started and the model the provider reported.

Qualification is per model and proportionate, not a blanket claim. Measured for claude-opus-5 on the real
non-interactive path before the change: the read-only and the writable profile shapes both ran, the provider
echoed the selected name back verbatim, the review role's tool inventory was unchanged, and the restricted
file tools edited an allowed path with no permission denials. The init row and its raw hash are recorded in
evidence/claude-model-binding/. Other models remain UNPROVEN; being selectable is not being qualified.

Also measured: provider capacity is model-specific. At one moment, in one command shape, claude-opus-5
answered while claude-fable-5-1 returned its own limit message naming another model as the remedy.

The Codex startup chain still specifies its own model (`gpt-6-astra`, reasoning effort `high`, in
`worker_command()`), so a Codex selection that differs from that recorded baseline is REFUSED rather than
accepted and silently not run. Wiring the Codex route to this selection is separate, later work, and its
baseline is asserted against the real function so drift on either side fails a test.

Limits: `--effort` stays pinned at medium and is not part of the selection; the choice binds at release
activation, not at task freeze, so a frozen task carries its executor but not its model; and no allow-list
of qualified models exists yet — the check proves the model that answered is the one asked for, never that
it is one already proven.


## D023 — 2026-09-23: the Runtime keeps its own copy of the qualified Claude CLI

D019 pinned the Claude CLI by SHA256, but `qualified_binary()` resolved `claude` on PATH: the Runtime
shared one binary with the owner's own chat. On 2026-09-23 that global install updated itself from 2.1.257
to 2.1.280 (`npm install --global @anthropic-ai/claude-code@latest`, 12:44:52Z). The pin did what it was
built to do and refused every Runtime Claude role; it also turned the published suite red, because the
model-binding tests build real commands. D022's owner decision that the global CLI is not updated for
AP-11 could not hold once the owner's own tool updated itself.

Decision: the Runtime keeps exactly the qualified bytes in `.runtime/bin/claude-2.1.257`, beside its pinned
`codex-0.155.1` and `temporal-1.9.1`, and `qualified_binary()` reads that copy. The hash, the version the
provider must report and both refusal messages are unchanged; a missing copy, a symlink in its place or
changed bytes refuse before any model could start, and nothing falls back to PATH. The owner's global CLI
is left as it is.

The copy is the member `package/claude` of `@anthropic-ai/claude-code-darwin-arm64@2.1.257`, fetched with
`npm pack` (which verifies the registry integrity) and accepted only because its SHA256 equals the D019 pin.
Provenance, code signature and the subscription route measured through the copy are in
evidence/claude-host-copy/provenance.json.

This is not a requalification and not a new version: no model, right, payment path or acceptance
requirement changes. Moving to a newer CLI remains a separate qualified step.

## D024 — 2026-09-23: a whole-goal package the reviewer cannot read is refused, and an assessment identity never runs twice

Two whole-goal reviews in a row named delivered evidence they could not open. The common cause was not one file:
host-derived JSON was written with `json.dumps` on one line, which every byte check passes, while the reviewer's
own reader refuses any read over 25000 tokens and pages by LINE, so a long line can never be opened (measured with
the reviewer's profile: "File content (79468 tokens) exceeds maximum allowed tokens (25000)"). The second review
could not open SCOPE_JOURNAL.json (82631 bytes on one line); SCOPE.json and ACTUAL_REPORTS.json had the same shape
and were readable only because they were shorter.

Decision, readability: every derived JSON delivery of the final-review package is printed over short lines, and
`prepare()` refuses a package in which any delivered line exceeds READER_LINE_BYTES or any file exceeds the per-file
bound. The only exception is a verbatim native-history line, accepted where the index records it as unreadable in
place, with its readable companion or, where no companion the reader could open can be made, as a named gap. The package also carries every earlier whole-goal review of the commitment
verbatim (WHOLE_GOAL_REVIEWS.json; an incomplete one only as the host measured it, never its partial stream), the
decision and review binding each further assessment, and the release revision's own proof sources.

Decision, further assessments: the n-th entry of `development.assessments` IS `office-ap11-assessment-(n+1)` and
follows the entry before it; a decision can no longer choose a name, and a new entry needs no code change. Each
run's counted keys use its own identity (`key_prefix`), so the second assessment replays under exactly the keys it
ran under. `assess` refuses when the selected evidence is the package the followed review already had, and refuses
any identity the scope has seen run - a counted call in its namespace or a recorded start - because the engine's
duplicate refusal forgets a closed run one day after it closed. The start record is written only after the engine
accepted the start.

Unchanged: the 48/6 ceilings, the duplicate-start refusal, the requirement that each further assessment is a
separately reviewed decision bound in the active configuration through a controlled transition, and that an
assessment follows only a review that was not approved.

## D025 — 2026-09-23: the continued half of an interruption never closes the commitment by approving

The third whole-goal assessment found that a G6 demonstration carried inside an assessment run has no independent
examiner inside that run: the interrupted review is its subject and the continued review is its second half, so an
approval by the continued review would be self-approval (amendment section 5). A separate review of the next form found
that the code would nevertheless close the commitment on such an approval.

Decision: close() withholds the closure when the approving review continues an interrupted whole-goal review of its
own run (another final-review call of the same run with no completed result). The approval is recorded as given, the
scope is paused with that reason, nothing is stopped and no final record is written. preserved_refusal() lets a
further, separately bound assessment follow such a withheld approval, and still refuses to follow an approval that
closed the commitment. An approval by a review that continues nothing closes exactly as before.

This only narrows when the commitment may close. It changes no ceiling, role, bound, verdict or acceptance criterion.

## D026 — 2026-09-23: a termination signal to a running model guardian ends the call

The fourth whole-goal assessment's interruption was sent as fixed in advance: SIGTERM to the guardian of the first
counted review, after its pid, start time and module were verified against the record the Runtime wrote at launch.
The signal was delivered - nothing pending, nothing blocked - and the review ran on to its verdict 197 seconds after
it started. Measured cause: the guardian's handler raised `InterruptedError`, and the loop waits almost all the time in
`streams.select()`, whose standard implementations catch `InterruptedError` and return no events. The exception was
swallowed and the loop continued. Reproduced with the unchanged release code in an isolated scope. No test had ever
sent a signal to a real guardian process; every earlier test called `execute()` in-process.

Decision: the handler only records the signal, and the loop ends the call on its next pass with the same reason as
before (`goal call signal`), so the provider group is removed and the incomplete result is written by the guardian
itself. A signal that arrives before the provider runs ends it on the first pass; one that arrives after the provider
has finished changes nothing. A real-process test sends SIGTERM to a real guardian waiting on a silent provider and
fails against the previous code.

The same raising handler exists in `private_stage.model` (AP10's private stage, outside this commitment's mandate)
and in `development_interactive` (the interactive route, every start of which is spent). Neither is changed here.
`attempt.py` is not affected: it waits in `select.select`, which lets the handler's exception through.

This changes no ceiling, role, bound, verdict or acceptance criterion.

## D027 — 2026-09-24: the examining review gets the room the whole evidence needs, and the reader B reuses

Each further assessment adds its own native history, decision, separate review and run record to the package the
next whole-goal review receives, and history parts that do not fit are dropped oldest first as named review gaps.
Measured with the ACTIVE release d17d562e's own preparation against the real scope after the fifth assessment, with
the qualification index then bound (35 records) and before the sixth assessment's own additions: under the 3 MiB
bound the package was 2935830 bytes in 136 files because the first part of the application's history (part 1 of 7,
events 1 to 510) did not fit and was delivered as a named gap. With this change the same preparation delivers every
part: 3196024 bytes in 139 files, 998280 bytes under the new bound, no gaps. The 3 MiB bound was the owner's
decision of 2026-09-23; on 2026-09-24 the owner decided that what is required to make it work is done. The 4 MiB
figure is the operator session's choice under those words.

Decision: the final-review delivery bound is 4 MiB. Every other role keeps 2 MiB, the per-file and per-line reader
bounds are unchanged, and a shortfall still becomes a named gap, never a silent shortening.

Also: the package delivers the Office owner-view reader from the release's own Office copy under the name the
reviewer's instructions give it, `tools/agarbild.py`. The continued review of the fifth assessment found B's reuse of
that reader checkable only from its caller, because the instructions name the reader and the inventory did not carry
it.

This changes no ceiling, role, verdict or acceptance criterion.

## D028 — 2026-09-24: the Codex startup chain runs the release's model choice

D022 made the model an explicit release choice, `development.models.{claude,codex}`, but only the Claude route read
it. The Codex startup chain specified its own model in `worker_command()` (`gpt-6-astra`, reasoning effort `high`),
so a Codex value that differed from that baseline was refused rather than configured and silently not run. This is
part 1 of step 3 of the owner decision of 2026-09-22, a reusable model choice for both executors, which the owner
confirmed on 2026-09-24 after AP-11 closed. It is accounted for separately from AP-11.

Decision: `worker_command(model)` takes the model as a parameter whose default is the recorded baseline, and
`profile.command(..., model=None)` passes `profile.selected_model(model)`, checked by the same plain-model-id rule as
the Claude profile before the name can reach an argument list. `models(config)` returns the chosen Codex model
instead of refusing it. Every development route Codex can drive passes the release's choice: task attempts
(implementation and review, whose preflight now resolves the selection for either executor, and whose run record
states the Codex model started), the read-only goal roles and the interactive route. As for Claude, an invalid
selection now refuses a Codex call in its preflight, before anything is launched or consumed. The choice replaces the
model argument and nothing else: the reasoning effort stays pinned and is not part of the choice, as Claude's
`--effort` is not.

Unchanged by design: without a choice the command is byte-identical to what the active release builds. Measured in
separate interpreters, each reporting that it imported its own code root, with the active release's code (runtime
2def3667) and with this change for the same inputs: `worker_command()` and all four command shapes (read-only,
writable, writable with allowed paths, interactive) are identical, and a probe name changes exactly the one model
argument. AP-10's private stage is outside the development selection: it does not read `development.models` and keeps
the recorded baseline, and a test fails if it launches anything but the default command.

What the CLI itself does was measured, not assumed. `codex exec --json` reports no model identity in its event stream
(a thread id, items and usage), so the per-run identity comparison D022 applies to Claude has nothing to compare for
Codex. What can be checked is the pinned CLI's own resolution of the arguments. The 0.155.1 app-server, started with
exactly the global argument prefix the exec route carries, answered `config/read` (no thread, no turn) with the
passed model verbatim as its effective model, from the command-line layer and over the owner's own config.toml that
names a model too, with the reasoning effort unchanged; this held for the baseline and for a probe name. The reduced
shape is in evidence/codex-model-binding/, bound to a test that rebuilds the same arguments from this code; the raw
protocol stays private.

Limits: selectable is not qualified. No Codex model other than the baseline has run under this chain, and a
different choice still needs its own proportionate qualification and a controlled release transition. The Codex
binary is identified by its versioned project-local path and is not hash-checked at run time as the Claude CLI is
(D019, D023). As before, the Codex interactive completion check reads no model and the goal-call record names the
provider but not the model. Nothing is activated by this change: the active configuration names no Codex model, so
every running path builds the same command as before.

## D029 — 2026-09-24: a model change is one run of a reviewed tool, not a new derived transition

D022 made the model part of the frozen release configuration, changed only through a controlled release transition.
Every change so far needed its own transition script, derived from the previous one by counted replacements (the last,
for AP-11, is some 1,400 lines, most of them about that commitment), and its own separate review. This is part 2 of
step 3 of the owner decision of 2026-09-22: a simple existing entry for changing the model without editing source.

Decision: `scripts/model_choice.py` is that transition written once, with the model as its parameter: `show`,
`stage [--claude MODEL] [--codex MODEL]`, `check`, `activate` (the owner), `forward` and `rebind`. Its one invariant is
that the staged configuration equals the active one except `development.models`; it is checked mechanically at staging
and again before activation. Staging copies the active release byte for byte, every bound file with its mode, verified
against the configuration on both sides, and the copy holds exactly the bound files. The new release directory is
named `<runtime>-<office>-models-<UTC time>`, since release directories were named by their revisions and a model
change keeps them. The release's own `models()` judges the selection before anything is written, so a choice that
release could not run is refused at staging, not after a switch. Existing releases and records are never overwritten.

Every action runs only as the copy inside the release the active pointer names, and refuses otherwise, including a
byte-identical copy in another release. Every module it uses, and the tool itself, are then bytes that release binds
and `installed()` verifies; a copy in a checkout would judge a choice by code the release does not run. Staging also
requires the active release to bind these tool bytes, and every later action compares the staged record's tool hash
with its own bytes. After a switch the new release is the active one, so `rebind` is run with its copy. The first release that carries the tool therefore has to be activated by a controlled code
transition as before. From then on, each release the tool makes carries the same tool.

Activation is the sequence of the reviewed AP-11 transitions (executor-transition-13) without their AP-11 checks. It
first measures the preconditions, and refuses before anything is stopped unless all of them hold:
- the tool bytes, the staged configuration and the active selection are unchanged since staging, and the staged files
  verify;
- no AP-10 run is in progress, and the next one is at least 20 minutes away;
- the AP-10 schedule is bound to the active selection, and the recorded service is alive;
- no work is in progress in the engine: running workflows are allowed only when idle, and the idle development tasks
  are listed, because a resumed task runs the new choice;
- the staged release meets its own daemon start requirements now;
- there is a way back: the active release passes its own offline start check.
Then it takes an online database backup, stops the service, selects and starts the staged release and confirms it. On
a failed start it restores and restarts the previous release. After a confirmed start it rebinds ONLY the config hash
of the AP-10 schedule and reads everything back. Without a way back it does not begin: a switch that could leave the
service and AP-10 down with nothing to restore is a changed operational risk, which is the owner's to decide and not
a tool run's.

Measured without changing anything, 2026-09-24: the tool's own engine-facing reads against the live engine and
service returned the schedule shape its tests assume, a schedule bound to the active selection, no busy work, two idle
development tasks (`office-watch-policy-1`, `office-assignment-cli-1`), the service alive and bound, the active release
startable offline, and the daemon start requirements met from the archives the release binds. Tested on a synthetic
host, with real staging, copying and database backup, the real control flow of the stop, the start confirmation,
the forward path with its restore, and the decision whether to rebind, and doubles with the real signatures for the
engine and launchctl; each of twenty guards was removed in turn and the test that carries it failed.

Limits: the switch itself has run only against doubles until the first release carrying the tool is active and the
owner activates a change. The choice still binds at activation, not at task freeze. A selectable model is not a
qualified one. The idle service-identity workflows of earlier configurations stay running (23 measured on 2026-09-24,
4 events each, beside the two idle development tasks), and each activation adds one; that is unchanged here. The tool starts no model and changes no ceiling, role, executor,
revision, scope or AP-10 setting beyond the schedule's config hash, which every transition rebinds.
