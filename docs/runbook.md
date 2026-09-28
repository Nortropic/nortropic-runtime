# Running the qualified local route

The living plan owns the current task, wait reason, attempt identity and next
specific action. Read it before starting any process. Both accepted tasks are completed; see docs/runtime-v0.1.md for measured scope and limits.

The current installation uses a pinned local Temporal 1.9.1 development service,
Python 3.12 with temporalio1.33.0 in `.runtime/temporal-venv`, and Codex0.155.1
under `.runtime/bin`. Dependency lock and recorded hashes are under config/ and
evidence/startup/. Authentication uses the already authorized Codex and Claude Max subscriptions;
GitHub authentication is available only to the host publication activity. No
Temporal Cloud or paid API fallback is configured. This is a trusted local Mac
installation, not a deployed multi-user service.

A new accepted task must have committed task JSON and brief in tasks/ plus a
reviewed host-owned acceptance module under acceptance/. Its digest, exact current
main base and explicit allowed paths are fixed before implementation. The qualified
route supports the measured Codex-only and Codex→Claude→Codex tasks with regular
files under tools/. This is not qualification of arbitrary provider/task sequences.

```sh
.runtime/temporal-venv/bin/python -m runtime.run tasks/evidence-index.json
```

This starts one loopback Temporal service and one worker, submits the frozen task
once, observes a bounded result, preserves history and stops service groups.
A completed existing task cannot be submitted again; existing task/evidence
folders are never overwritten. The native SQLite database at
`.runtime/runtime.sqlite` is canonical engine state. Frozen input/candidate files
are under `.runtime/tasks/<id>`; durable evidence is under `evidence/runs/<id>`.
The historical report task uses evidence/accepted-task/.

Inspect an existing run without resubmitting or buying access:

```sh
.runtime/temporal-venv/bin/python -m runtime.run tasks/evidence-index.json --resume
```

Exit0 means completed; exit1 can mean a deliberately preserved waiting state.
Read state.json and raw launch/result/acceptance/review artifacts before deciding
what to do. Inspect recorded process identities/groups and verify old writers
have stopped. The CLI also refuses observed unfinished writers. A lost connection
is not proof that a provider has stopped. Never erase launch evidence or lock
files to bypass this check.

After a concrete implementation diagnosis and materially changed prerequisite,
resume the SAME task with `--resume --diagnosis "what changed and why"`. This
signals native history and increments the implementation attempt. There are no
automatic model retries. The chain driver reads the failed attempt, acceptance
and process receipts, identifies the actual cause, makes a scoped correction or
restores the prerequisite, records it in the living plan, and sends this signal.
A timeout or missing output alone is not evidence of a source defect. If no
prerequisite changed, retain the wait; do not repeat the same call blindly.

If a publication response is ambiguous, first inspect remote PR/head/base and
preserved local evidence. Then use `--resume --reconcile "what was inspected"`.
The Publisher reconciles an already merged exact candidate before another remote
mutation; it rejects changed bases, heads, or inadequate receipts. Never post
success statuses to bypass a failed or missing mandatory result.

### Review continuation and chain-driver ownership

At `waiting_review`, query state and read the numbered `review-N` receipts.
`review_recovery=repair` means a completed, correctly bound independent rejection
contains concrete blockers; it permits `--resume --review-repair "diagnosis and
relevant correction"`. Runtime keeps the accepted task ID, base, paths, verifier
and earlier results, runs the final accepted implementation provider with those
findings, freezes a new candidate with changed file bytes, runs full acceptance,
and starts a new independent review. Failed repair tests return to
`waiting_diagnosis`; they do not bypass review. A repeated unchanged candidate
also waits for diagnosis. Only fresh approval for the new exact subject can publish.

`review_recovery=review_only` means missing, interrupted, inconclusive, malformed,
stale or non-independent review. It does **not** establish a candidate defect.
After diagnosing and correcting the review prerequisite, use `--resume
--review-retry "what changed"`. The same candidate/tests are reviewed again;
implementation attempts do not increase. Numbered outputs and native history
preserve every prior result. Signals bind task digest, candidate, review round
and attempt; stale, duplicate and mismatched actions cannot start extra work.

The chain driver owns this inspection and technical continuation within the
accepted task; the owner does not relay reviewer reports or fetch new prompts.
Record the current wait, evidence paths, diagnosis, changed prerequisite and next
command in docs/plan.md before leaving a task. A new receiver reads that record,
verifies old writers stopped, and resumes the same workflow. These are explicit
host decisions, not an unattended daemon or automatic retry policy.

For `waiting_publication_reconciliation`, the chain driver inspects the exact
candidate branch, PR/head/base, statuses, protection and server merge state before
signalling reconciliation. A confirmed merge of the exact tree is reconciled,
not published twice. If the PR is still open, retry only after the diagnosed
publication prerequisite is restored. A changed main/base or scope is **not**
fixed by blindly repeating `--reconcile`: preserve the rejected receipt and
prepare a separately reviewed continuation/candidate with new tests/review. The
current automated profile has no generic rebase continuation; the chain driver
handles that bounded source/input change explicitly before resumption. Ask the
owner only if it changes mandate, cost or business priority. Never manufacture
approval/status evidence to get past a wait.

### Actual target profile before the next useful task

Runtime currently validates `Nortropic/nortropic-runtime`, explicit regular
`tools/` files, a trusted exact base and this repository's host publisher. Its
sandbox write boundary is also `tools/`; changing task JSON alone cannot qualify
another target. A business task belongs in its actual business repository. Once
that outcome/target is known, qualify only the necessary repository/path mapping,
isolation and publication authority, preserving host-owned acceptance and review.
An isolated test-target qualification does not grant production permissions.
Do not place business code in Runtime to bypass the present validator.

Candidate and reviewer have no publication tools, no network, and no host evidence
write access. Reviewer source is read-only. A host creates exact Git objects,
executes frozen acceptance in the native sandbox and binds both real run identities
before protected publication. Required server checks must name explicit positive GitHub App IDs for both
`runtime/tests` and `runtime/review`. The branch rule is the existing host-owned
issuer authority; candidate input and installed-app discovery cannot choose it.
Publisher refuses null/missing/any-app bindings before push or PR, never posts its
own success statuses, and requires completed successful check-runs from those
exact issuers on the exact candidate before merge. Missing, malformed, truncated
or ambiguous readback, and an issuer change during publication, stop integration.
It does not infer success from combined commit status, neutral or skipped runs.

The current servers' null bindings therefore block this path. The historical
`config/branch-protection.json` has any-app (-1) entries and is not a qualified
configuration for this stricter path; this change does not apply or repair it. Selecting and
qualifying a genuinely independent issuer, its protected execution/input boundary,
and server configuration is still an external prerequisite. An arbitrary installed
App or GitHub Actions identity alone does not qualify that boundary. Do not weaken
protection or substitute a PAT status to get past the wait. This code grants no
new credentials and does not retrofit the active or integrated holder; adopting a
new Publisher still requires the existing separately reviewed holder transition.
If a PR was already created before checks became available, preserve it and
reconcile only after the diagnosed prerequisite is restored.

No general hostile detached-process or arbitrary-host-compromise guarantee is
claimed. Per-invocation deadlines and process-group cleanup are measured local
safeguards. See the evidence index and current limitations in docs/plan.md.

### Restored Claude access on the retained report task

The qualified Claude path uses the existing Max subscription, pinned CLI2.1.257,
Read/Edit/Write only, exact accepted file grants, strict empty MCP and native
AGENTS.md file loading. Host runs tests after cleanup. A changed binary/auth path
stops before model invocation; diagnose/requalify rather than enabling API fallback.

Historical transition command (already completed; DO NOT run again for this task):
the host generated, preserved and separately reviewed the same task's continuation
on clean integrated main, then invoked:

```
.runtime/temporal-venv/bin/python -m runtime.run tasks/run-report-continuation.json --resume --access-restored
```

This is for the existing waiting checkpoint only. It keeps the native workflow,
old workspace, attempt counter and resource history. A second signal cannot repeat
an already-running step. Do not rerun preparation into partial state; inspect the
preserved directories/receipt and native query before reconciling. After transition,
ordinary observation uses the same input with `--resume` alone. Follow docs/plan.md
for the actual current checkpoint; the command above is not a request to resubmit.

### Selected dependencies and installation record

The current workstation is installed and qualified. Do not reinstall or update it
as part of ordinary resume. [dependencies.json](../evidence/v0.1/dependencies.json)
records current binary hashes, Python3.12.13, macOS26.3 and arm64. Claude2.1.257's
binary SHA256 is enforced by runtime/claude_profile.py on the Runtime's own copy,
.runtime/bin/claude-2.1.257, never on whatever `claude` PATH resolves to (D023); it
uses existing account credentials. A changed version/auth route requires a new
bounded qualification, never automatic API fallback.

For a fresh isolated project installation, inspect these exact selected artifacts
and their retained download/inspection records before extraction:

- openai/codex release rust-v0.155.1: codex-aarch64-apple-darwin.tar.gz and
  codex-code-mode-host-aarch64-apple-darwin.tar.gz; extract only selected regular
  executables to .runtime/bin/codex-0.155.1 and .runtime/bin/codex-code-mode-host.
  Commands and outcomes: evidence/startup/codex-download/ and codex-host-download/.
- temporalio/cli release v1.9.1: temporal_cli_1.9.1_darwin_arm64.tar.gz; selected
  regular temporal member to .runtime/bin/temporal-1.9.1. Download and inspected
  archive hash/members: evidence/durable-probe/cli-download/ and cli-inspection.json.
- npm @anthropic-ai/claude-code-darwin-arm64@2.1.257, fetched with `npm pack`; only
  the regular member package/claude to .runtime/bin/claude-2.1.257, used only if its
  SHA256 equals BINARY_SHA256. Record: evidence/claude-host-copy/provenance.json.
- Python SDK and every transitive package/version/hash are fixed by
  config/temporal-probe-requirements.lock. The recorded installation used inspected
  wheels, no source build or extra startup .pth code (wheel-inspection.json).

The selected environment creation/install commands, for fresh paths only, are:

```sh
/opt/homebrew/bin/python3.12 -m venv .runtime/temporal-venv
.runtime/temporal-venv/bin/python -m pip download --only-binary=:all: --require-hashes -r config/temporal-probe-requirements.lock --dest .runtime/temporal-wheels
.runtime/temporal-venv/bin/python -m pip install --no-index --find-links .runtime/temporal-wheels --require-hashes -r config/temporal-probe-requirements.lock
```

No Symphony dependency is used by the delivered runner; its historical probe
artifacts remain. Runtime starts pinned Temporal on loopback ports7339/7340/7341,
namespace nortropic-runtime, task queue development, central SQLite and an exclusive
engine.lock. It stops service/worker groups after bounded observation. Never start
another service while a recorded writer or listener is alive.

Routine support checks are `python3 -m unittest discover -s scripts -p "test_*.py" -v`
and `git diff --check`. The suite builds real Claude commands, so the root it resolves
(the checkout itself, or NR_HOST_ROOT) must hold .runtime/bin/claude-2.1.257; an
integration worktree reaches the host's copy through its .runtime/bin link, and a fresh
checkout without one fails those tests closed (D023). Native replay runs without provider calls using
`.runtime/temporal-venv/bin/python -m scripts.replay_runtime`. Historical experiment
scripts refuse their existing state/output paths; they are evidence reproductions,
not restart commands. A new host restoration is not yet an end-to-end tested path.

## AP04: named office target

The host allowlist additionally maps `Nortropic/nortropic-projektkontor` to the
sibling checkout named `nortropic-projektkontor`. No task may supply a local root
or arbitrary remote. Its inputs must be committed under that checkout's tasks/
and acceptance/. Both input and Runtime revisions are recorded; office tasks pin
`runtime_revision`. Dirty host source/inputs refuse start. Existing accepted bases
remain immutable; publishing rechecks current remote main.

Office entry: `python3 -B tools/kontor.py start --task resultat.json` in the office.
`status` and later `resultat` read saved Runtime snapshots only and never call
`runtime.run`. Their age is explicit; they are not live engine/remote queries.
`fortsatt` invokes the existing resume path. Diagnosis/review repair/review retry/
publication reconciliation require the same explicit reasons as before. Legacy
Claude access/base replacement is not enabled for office tasks. Do not use
`--resume` as a read-only status query.

The executor is an explicit accepted choice per role, for both targets: each step
names `provider` (`codex` or `claude`), and an optional `review_provider` names the
reviewer. An absent `review_provider` is the original Codex reviewer, so earlier
accepted tasks keep their digests and histories. Both values are inside the frozen
task digest; nothing switches executor automatically on quota or access loss, and a
caller cannot substitute an executor the accepted task did not name.

A Claude reviewer uses the read-only profile: `--tools Read`, no file grant, plus the
host-written `--json-schema`. Measured with the pinned CLI this yields exactly the
tools `Read` and `StructuredOutput`; any other inventory, a missing or second
terminal, an error terminal, a missing/conflicting structured object or an
interrupted run is an incomplete review, never an approval. A reviewer is a
separate process and context whose run must differ from every implementation run.
When author and reviewer use the same model family that separation is NOT a claim
of independent judgment. The Claude author has Read/Edit/Write only and cannot run
tests; host acceptance runs afterwards in the existing sandbox. Managed Claude
settings are bound with the other native instruction inputs.

Release-transition constraint: this revision extends the bound instruction inputs,
so its guard key set differs from every earlier frozen configuration. The frozen
active release is unaffected (it runs its own pinned copy). Do NOT advance the
primary operator checkout to a revision containing this change before the separately
reviewed controlled transition: `delegate()`-based commands (`runtime.run`,
`runtime.obligation`, `runtime.development_control`) and release staging compare the
checkout's guard set with the active configuration and would refuse. The new
release must be staged by code that contains this change, and the checkout is
advanced as one step of that transition. Integration alone activates nothing.

Office candidates receive exact-file write grants, plus scratch for Codex. The active entry
`tools/kontor.py` is host-owned and excluded from task write scope. Host verifier,
engine/publication source and authority remain outside the candidate workspace.
Acceptance must execute candidate code through the existing read-only sandbox,
never import it into privileged host Python. The result module is only loaded
by the office CLI's explicit read-only `resultat` action after delivery.

## AP11: operating the finite commitment

Operator commands run from the integration worktree with the host root named, never from a primary checkout whose
release code lacks the managed guards:

    cd "<runtime>/.runtime/ap11/integrations/evidence-access"
    LC_ALL=C NR_HOST_ROOT="<runtime>" ../../../temporal-venv/bin/python -m runtime.development_control <action> --reason "..."

`status` reads and starts nothing. `pause` and `resume` write the scope control and wake the waiting parent; a pause
stops new starts and retries and lets already started work finish; the pause and every consumed call persist over
restarts. `stop` is terminal for the commitment and cancels only its own running workflows. `continue` answers a
parent waiting for host diagnosis with a host fact; it is refused unless the scope is active. `assess` starts the
further whole-goal assessment the ACTIVE configuration binds: only after an actual review that was not approved,
only when every earlier run is closed, only with evidence that differs from what that review was given, and never
under an identity the scope has already seen run. Every refusal comes before anything is started or written.

A further assessment exists only as a separately reviewed decision bound in `development.assessments` by a controlled
release transition (D024). Its identity follows from its position in that list, and its calls count against the
same 48/6.

An approval by the continued half of an interrupted review in its own run pauses the scope instead of closing it
(D025); a separately bound further assessment then examines the whole event.

## The entry follows main

The primary checkout stands on `main` equal to `origin/main`, with no commits of its own; work happens in separate
clones or worktrees. Start every session with `python3 -B scripts/check_entry.py`: it fetches `origin` and warns when
the entry is on another branch or a detached commit, has commits of its own or lags, has changed tracked files, or holds
a local branch with no copy on origin that the plan on `origin/main` does not name. It changes nothing; its only write
is the fetch of remote-tracking references, and it always exits 0. When it warns, read the plan from `origin/main`
(`git show origin/main:docs/plan.md`) and report the deviation. After each protected publication, fast-forward the
entry if it is clean (`git fetch origin main` and `git merge --ff-only origin/main`); otherwise report the deviation in
the delivery note. A working branch ends published, archived as a git bundle under `.runtime/`, or kept with a named
reason in the plan.

The routine is deliberately not in `AGENTS.md`: the active release binds the entry's `AGENTS.md` as a native
instruction input (`release.instruction_guards`), so changing it makes every new model call refuse until a release
staged with the new bytes is active, and the code transitions refuse a changed instruction input by design (D032).

## Changing the model choice

The model each executor runs is `development.models` in the active release configuration (D022, D028). It is changed
by one reviewed tool (D029), never by editing source and never by hand: the active release's OWN copy of
`scripts/model_choice.py`, which refuses to run from anywhere else. From any directory:

    R="<runtime>"; A="$(dirname "$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["config"])' "$R/.runtime/ap10/active.json")")"
    "$R/.runtime/temporal-venv/bin/python" -B "$A/runtime/scripts/model_choice.py" show
    "$R/.runtime/temporal-venv/bin/python" -B "$A/runtime/scripts/model_choice.py" stage --claude <model> [--codex <model>]
    "$R/.runtime/temporal-venv/bin/python" -B "$A/runtime/scripts/model_choice.py" check
    "$R/.runtime/temporal-venv/bin/python" -B "$A/runtime/scripts/model_choice.py" activate

`show` reads the selection, what each executor runs and which executor drives which role. `stage` copies the active
release byte for byte into a new release directory whose configuration differs ONLY in `development.models`, after the
release's own rule has accepted the names, and prints the next two commands with their paths; nothing is stopped or
selected. `check` measures every precondition of the switch and changes nothing. `activate` is the owner's step, in
their own logged-in terminal: it backs up the database, stops the service, selects and starts the staged release,
restores and restarts the previous one if the new one does not start, and then rebinds only the config hash of the
AP-10 schedule. It refuses to begin while an AP-10 run is in progress or less than 20 minutes away, while any work
runs in the engine, or without a way back. After a stop that did not complete, `forward` continues; after a switch
whose schedule rebinding failed, `rebind` completes only that, run with the NEW release's copy, which is then the
active one (the message names it). Staging again makes a new record; `check` and `activate` always take the newest.
The tool sets `LC_ALL=C` and the host root itself. Records: `.runtime/ap10/model-transitions/<time>/`.

A model that is selectable is not thereby qualified; a new model needs its own proportionate qualification. The choice
binds at activation: an idle development task that is resumed afterwards runs the new choice, and `check` lists them.

When the chosen model has no capacity, the run waits exactly as before and the host writes a question to the owner
(D030): `show` lists the newest ones under `questions`, each with the executor, the model, the provider's own words and
whether that model is still the chosen one; the record itself, under `.runtime/ap10/model-questions/`, holds the two
choices with the exact commands and the models qualified for that executor. Waiting needs no action. Nothing is
switched until the owner runs the tool, and buying credits or upgrades is never one of the choices.

## The web profiles (D034)

Three host commands for a management function's recurring steps: `runtime.web_measure` (no model),
`runtime.web_critique` and `runtime.web_visitor` (model as a parameter). After the owner's transition they run only as
the active release's own copy, with the host root named; before it only from a candidate checkout, and the receipt says
which. Run from the code root:

    NR_HOST_ROOT="<runtime>" "<runtime>/.runtime/temporal-venv/bin/python" -B -m runtime.web_measure \
        --mal https://... | --fil /absolute/page.html  --etikett NAME [--sektioner 2] [--delar skarm,rubrik,axe,lighthouse,detektor] \
        [--handling-text TEXT | --handling-selektor CSS] [--undantag-fil /private/file] \
        [--vyer NAME=WIDTHxHEIGHT@SCALEm|d,...] [--axe-taggar TAG,...]
    ... -m runtime.web_critique --underlag MANIFEST.json --fraga FRAGA.md --schema SCHEMA.json \
        --utforare claude|codex --modell NAME --etikett NAME [--tid 1200]
    ... -m runtime.web_visitor --start URL --tillatna ORIGIN[,ORIGIN] --uppgift UPPGIFT.md --vy mobil|desktop \
        --utforare claude|codex --modell NAME --etikett NAME [--max-handlingar 40] [--tid 1200] [--undantag-fil FILE] \
        [--bindning key=value ...]

The measurement's views and axe tags are the management function's parameters with D034's values as defaults (D037);
the receipt records which ran and whether the defaults were used, and the module's `PARAMETRAR` says the code takes
them. Each run writes `.runtime/profiler/<matning|kritik|provare>/<UTC time>-<label>/`, closed by `KVITTO.json` and
`KVITTO.sha256`; read the receipt's `outcome` first. Nothing is written into a repository, published or deployed, and
no run is retried automatically. A protection exception is only ever a private file (exactly 0600, one line of at least
16 characters, outside `/tmp`, `/etc`, `/var/folders` and the run area); never pass the value on a command line.

The visitor starts no model until the model-free host check of its barriers has passed for exactly the current bytes,
Chrome and Node (`.runtime/profiler/vardprov/godkant-<identity>.json`); otherwise it runs that check first (about a
minute). Nor does it start one when the start page did not open without an error, below status 400, inside the
allowlist: the run then closes as `start_misslyckades` (D035), with the reason in the receipt's `start_problem`.
Whether a scenario succeeded is decided by a separate reading of `KONTROLL.md`, the trace and the site, never by the
visitor's own report.

A stopped run leaves none of its processes running (D035, D036). One Ctrl-C, SIGTERM or SIGHUP to a profile command
ends its model session, holder, Node and Chrome before it exits with `avbruten` (exit 3) and no receipt; further signals
are ignored until then, and the final cleanup ignores them too. The run's Chrome profile is removed, since after priming
it holds the protected host's cookie. The run directory and the temporary workspace otherwise stay as they were, nothing
in them counts, and they are not searched for the protection value. Should the command be killed outright, the holder
and the measurement end themselves within seconds and remove the profile; a model CLI ends by itself. To check for
leftovers, look for processes naming the run's `.chrome-profil`.

Tools: the pinned copy is installed once from an existing npm install whose lock names the same versions, and is
checked tree by tree against `config/web-tools.lock.json`; nothing is downloaded:

    "<runtime>/.runtime/temporal-venv/bin/python" -B scripts/install_web_tools.py --source <existing node_modules>
    "<runtime>/.runtime/temporal-venv/bin/python" -B scripts/install_web_tools.py --check

The engine binary is `.runtime/bin/impeccable-0.1.6`, checked by SHA256 at every measurement. Host checks, outside
the published suite, with their own receipt:

    "<runtime>/.runtime/temporal-venv/bin/python" -B scripts/run_web_host_checks.py <new receipt path>


## Release-bound Office operations (D038)

This candidate requires protected integration and an activated release before ordinary use.
`python -B -m runtime.operation_schedule status OPERATION` reads only the release-bound operation.
The same command takes `install`, `resume`, `pause`, `stop` and `rebind`. Installation refuses duplicates
and starts paused. Resume requires explicit action; stop disables future starts and lets a bounded
in-flight operation finish and record its effects. Rebind requires a paused, idle schedule and retains
all scope checks. These commands never modify the AP-10 schedule.

The release configuration must bind `scheduled_operations[OPERATION]` to
`{"input":"operations/NAME.json","interval_seconds":300}` and include hashes for that input and
`office/tools/driftoperation.py`. Only 60–86400 seconds are accepted. The Office input uses schema
`office-drift/1`, a private `state` directory, and optional `intake` and `monitor` objects. Intake binds
Digitala's frozen consumer bytes, an absolute resolved `python_path` and exact `python_sha256`,
customer directory, executor, HTTPS base URL and credential file;
monitor binds the exact HTTPS health address and 40-character candidate SHA. Secrets remain in private
0600 files outside repositories. A bypass is internal monitor access, never customer authentication.

The worker process runs a separate `office-operations` queue and activity slot; a model/AP-10 activity
on `development` cannot occupy this slot. Both workers retain the same managed worker process identity.
Status reads recent native execution states and completed business outcomes, plus missed/overlap counts.

Runtime returns the actual Office result. `completed: false` is not a successful business check just
because the workflow ended. Office persists per-run config bindings, intake output hashes and health
observations. Incident/recovery delivery is acknowledged only after the private recipient record is read
back, independently for intake and monitor transitions. Pending events and stored states use closed
validated shapes and UUID identities. Malformed state is preserved under an `.invalid-UUID` filename,
reported as an explicit incident and can recover on the next run; resumed delivery is recorded.
That is a local Office recipient, not a claim of email delivery. Native schedule status cannot
substitute for these results. An offline host yields no checks; the hosted product remains independently available.

For native input drift, `python -B -m scripts.inspect_native_config` checks release file hashes and reports
only differences and safe version/feature metadata. It never selects code or rewrites private settings.
Do not copy a new guard hash into the active config. Requalification and a reviewed release transition
with verified rollback are required.
