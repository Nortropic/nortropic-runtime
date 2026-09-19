# Running the qualified local route

The living plan owns the current task, wait reason, attempt identity and next
specific action. Read it before starting any process. Runtime v0.1 remains
incomplete while required Claude and recovery proofs are missing.

The current installation uses a pinned local Temporal 1.9.1 development service,
Python 3.12 with temporalio1.33.0 in `.runtime/temporal-venv`, and Codex0.155.1
under `.runtime/bin`. Dependency lock and recorded hashes are under config/ and
evidence/startup/. Authentication uses the already authorized Codex subscription;
GitHub authentication is available only to the host publication activity. No
Temporal Cloud or paid API fallback is configured. This is a trusted local Mac
installation, not a deployed multi-user service.

A new accepted task must have committed task JSON and brief in tasks/ plus a
reviewed host-owned acceptance module under acceptance/. Its digest, exact current
main base and explicit allowed paths are fixed before implementation. The qualified
route supports one Codex implementation step and regular files under tools/.
Do not imply general multiphase support from this route.

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
