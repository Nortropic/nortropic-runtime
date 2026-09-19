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
