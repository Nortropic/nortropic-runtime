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
