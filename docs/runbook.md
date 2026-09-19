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
automatic model retries. The present route does not yet automate remediation of
a rejected review; it waits without publication.

If a publication response is ambiguous, first inspect remote PR/head/base and
preserved local evidence. Then use `--resume --reconcile "what was inspected"`.
The Publisher reconciles an already merged exact candidate before another remote
mutation; it rejects changed bases, heads, or inadequate receipts. Never post
success statuses to bypass a failed or missing mandatory result.

Candidate and reviewer have no publication tools, no network, and no host evidence
write access. Reviewer source is read-only. A host creates exact Git objects,
executes frozen acceptance in the native sandbox and binds both real run identities
before protected publication. Required branch statuses are exact-candidate checks;
the current GitHub plan accepts status writers from any app, so host credential
isolation remains essential.

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
binary SHA256 is enforced by runtime/claude_profile.py; its native installed CLI
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
and `git diff --check`. Native replay runs without provider calls using
`.runtime/temporal-venv/bin/python -m scripts.replay_runtime`. Historical experiment
scripts refuse their existing state/output paths; they are evidence reproductions,
not restart commands. A new host restoration is not yet an end-to-end tested path.
