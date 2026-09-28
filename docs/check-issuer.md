# Bound host check issuer

This is a candidate implementation, not an adopted authority or a live GitHub
integration. Its App has not been registered, installed or given a credential.
The previously reviewed D039 consumer now calls `HostIssuer` in the ordinary
Publisher path after pushing the exact candidate. The construction wrapper reads
the holder's sealed credential-free suite measurement before the issuer runs the frozen host acceptance.
No caller-provided `passed` field substitutes for that execution.

The existing private holder owns `.runtime/ap11/check-issuer/`. Candidate and
reviewer profiles must be measured unable to read or write that directory outside
their one acceptance workspace. Owner file permissions supplement the sandbox;
they do not claim separation from arbitrary hostile code already running as the
owner. No broad host-compromise guarantee is added.

## Adoption and request

Only after separate exact-byte review, the existing holder may freeze the reviewed
import closure in a private read-only code location and issue `authority.json`:

```json
{
  "schema": "nortropic-issuer-authority/1",
  "app_id": 0,
  "installation_id": 0,
  "adopted_code_root": "ABSOLUTE_FROZEN_CODE_ROOT",
  "code_sha256": {"ALL_FILES_FROM_runtime.check_issuer.CODE": "ACTUAL_SHA256"},
  "adoption_review_sha256": "ACTUAL_SHA256_OF_adoption-review.json"
}
```

Zeros and placeholders are intentionally invalid. The real App and installation
must be read back from GitHub. `adoption-review.json` must contain actual distinct
`reviewer_run`/`implementation_run`, `verdict: approved`, no blocker and the same
complete code map. Preserve original independent review and its evidence. The
code does not manufacture an adoption record. A candidate-local invocation has
no authority until this separately reviewed holder transition has occurred.

Before adopting a credential, also adopt the new construction wrapper: the old
private wrapper executed a candidate suite without the native sandbox. Merely
installing an App key while continuing that old caller is not qualified.

The construction bootstrap is the existing holder's separately reviewed transition,
not a candidate override of the main pin. Freeze every file in `CODE` under
`.runtime/ap11/check-issuer/adopted/EXACT_40_HEX_SOURCE_COMMIT/`, preserving the
original review, source commit/tree, file hashes and prior holder attestation.
`CODE` includes construction registration and the dynamic development/snapshot
import closure. The reviewed adoption record must name this exact code root and
the actual distinct review/implementation runs. Neither wrapper nor issuer creates
an adoption record. Run this private wrapper with `NR_HOST_ROOT` set to the real
host, first `NAME COUNT --dry-run`, then the same invocation without `--dry-run`.
`construction_import_root` permits the non-integrated location only after the
existing private authority authenticates its exact bytes and separate review, and
only at the fixed adopted directory. An arbitrary candidate copy, including a
candidate dry run, is refused. The primary path retains the existing integrated-main
checks. All preserved-host checks, exact candidate/review/suite gates, latest-preview
comparison, App-bound protection and merge reconciliation remain in both paths.

Before placing any App key, measure the final one-commit candidates' complete suites
and Runtime preserved-host checks. A same-tree squash must preserve original commits,
reviews and the exact tree comparison; the holder binds the new exact subject only
after inspecting that evidence. This changes commit ancestry, not reviewed code bytes.
The implementation's bootstrap fixture is synthetic and credential-free: it proves
the copied wrapper reaches a real dry run, while candidate-local invocation, changed
closure, self-review, failed host checks and absent previews refuse. It does not adopt
the real host or qualify a live App.

The attempted whole-suite sandbox run is preserved as a failed qualification:
623 tests ran with 1 failure and 75 errors because historical host-fixture tests
need the live preserved state, process inspection and host temporary directories.
Do not grant those tests the App key to make the run green. The credential-bearing
wrapper instead requires `suite.json` plus its raw `suite.log` in the sealed task
directory, with `request.json.suite_sha256` binding the record. Its schema is
`nortropic-measured-suite/1`; fields are exact `candidate`, `tree`, canonical
`command` (`python -B -m unittest discover -s scripts|tools -p test_*.py -v`),
`log_sha256`, measured `returncode`, `test_count`, and
`credential_free_execution: true`. The last field is a holder attestation about
the measured execution boundary, not proof created by naming a field. The holder
must inspect and preserve the real runner evidence before sealing it. A candidate
cannot choose or write the sealed record. Changed candidate/tree or log bytes
refuse; there is no fallback to unsafe execution or an asserted success.

For this initial candidate, the full suite can be measured before any App key
exists on this machine, then frozen after independent review. A subsequent changed
candidate requires a new complete measurement in a credential-free environment;
the code does not provision such an environment or copy real credentials into it.
That operating prerequisite must be resolved before claiming unattended future
host-fixture qualification. The current native acceptance does run each time.

For each accepted task the holder seals `requests/ID/request.json`, `review.json`
and `probe.py` plus `acceptance.json` as owner files (0400/0600), outside candidate access.
The request contains `schema: nortropic-issuer-request/1`, exact `task`, `subject`
and normalized independent `review`, SHA256 of the actual `review.json` and
`probe.py` bytes (`probe_program_sha256`) and `acceptance.json` bytes
(`acceptance_contract_sha256`), and UTC `accepted_at`/`expires_at` (at most 24 hours apart).
The task's existing acceptance digest remains bound too. `probe.py` is a separately
reviewed observation adapter: it may import candidate code only inside the native
sandbox and emits actual domain output as JSON. It cannot decide acceptance.
Its first argument is the immutable source directory, and stdin carries one case's
actual input. The host's fixed evaluator parses stdout as strict JSON and compares
it with the private expected data. stderr is recorded separately. Process exit 0
alone, an arbitrary `true` or a candidate-supplied success object cannot substitute
for the exact expected domain behavior. No candidate code enters the host evaluator.

`acceptance.json` has this bounded form (up to 32 cases, each up to 120 seconds):

```json
{"schema":"nortropic-behavior-acceptance/1","cases":[
  {"id":"add-positive","input":{"add":3},"expected":{"value":5},"timeout_seconds":10},
  {"id":"add-negative","input":{"add":-7},"expected":{"value":-5},"timeout_seconds":10}
]}
```

This small numeric example is a test fixture, not acceptance for a real task. The
holder must freeze observations relevant to the accepted task and separately review
the adapter and expectation. Expected data stays outside the entire candidate-readable
workspace, argv, stdin and environment. The candidate receives only actual input and
the adapter. An import-time `os._exit(0)` cannot stop the host comparison and fails
because the required behavior is missing. Semantic coverage still depends on relevant
frozen acceptance plus independent review; there is no mathematical guarantee against
a deliberately test-adapted implementation. A generic success flag is not a qualifying
acceptance contract, even if its JSON shape would parse.
A task/acceptance change requires the holder to inspect the actual new source and
seal a new request. Acceptance and review are not inferred from keywords.

The issuer checks target, exact base/current remote main, one candidate commit,
allowed paths, complete independent review, request freshness, immutable blobs,
and the host comparison of actual isolated behavior. Failure writes private observations but
never authenticates the App or creates green checks. It rereads authority/request
and main after acceptance. Credentials are read only after its process group has
ended. Native descendants remain subject to the no-network/filesystem boundary.
The primary repository and its real Git worktrees are accepted only when their
resolved Git common directory equals the fixed host mapping and origin matches.
An unrelated clone with the same origin is refused.

The four explicit issuer targets are Runtime, Office, Digitala and Kundstart. This
does not widen Runtime's ordinary task/Publisher target mapping: that remains
Runtime/Office. Digitala has a fixed adopted-host command:

```sh
NR_HOST_ROOT='/Users/elinhaggstrom/nortropic-repos/Nortropic Runtime' \
  '/Users/elinhaggstrom/nortropic-repos/Nortropic Runtime/.runtime/temporal-venv/bin/python' \
  -I -B ADOPTED_CODE_ROOT/scripts/publish_digitala.py --task ACCEPTED_TASK_ID
```

The code-root placeholder must be the independently adopted, hash-pinned holder
copy, never the candidate checkout. This command accepts only a task identifier;
the existing holder must already have sealed its request, exact independent review,
behavior adapter/contract and actual Digitala suite measurement (`discover -s verktyg`,
with or without `-v`). The accepted task includes a positive `expected_test_count`;
the measured suite/log count must equal that independent expectation. Request
directory and task ID must match. `reviewer_run` is a plain public label (lowercase
letters, digits and hyphens); raw private review paths remain only in host evidence.
It cannot create an authority or request. The candidate must
be exactly one commit on the accepted current main in the fixed primary Digitala
object database (real worktrees share it). No title/body/review/success provided by
the candidate is trusted. Before any remote mutation, the command verifies the
sealed suite, parses `steg/steg.json` and checks the exact complete profession pin
set against Git blob hashes, without executing `pinna.py`. It then uses the shared
protected Publisher path to push, create/reconcile the PR, run the native behavior
issuer, verify both App-bound checks and expected head, squash-merge and read back
the exact integrated tree. The receipt remains in the private issuer observations.

Do not run Digitala's old `verktyg/publicera.py` after placing the App key: that
candidate-controlled program reruns its suite and pin script on the host. The
adopted command replaces that caller at the holder boundary; no new general Runtime
task target or self-grant is introduced. Its end-to-end regression uses real Git
bytes and behavior subprocesses but fake GitHub responses; real server qualification
remains required. Kundstart additionally has the verified private-plan blocker.

## App and server configuration

`config/check-issuer-app-manifest.json` defines an owner-private App with **Checks:
write** and **Metadata: read** only; no events, OAuth-user flow, content writes,
administration writes or extra accounts. Install only on the named repositories
being qualified. The credential belongs in the host's private `app.pem`; it never
enters a repository, environment, model input, argv, output or CI secret exposed
to candidate workflows. JWT signing uses the existing OpenSSL; an installation
token is narrowed to one repository and Checks write for each invocation.

This is a manifest payload for registration, not an automatically completed
manifest handshake. Registration requires GitHub's owner browser flow and a
protected callback/code conversion, or equivalent manual owner registration.
The browser inventory was empty, but root verified that native Chrome control
can reach the existing signed-in GitHub session. Existing API reads show Jonkebronk
is an active Nortropic org-admin and repository admin; extra membership or a manual
owner workaround is not required. Codex can prepare the concrete form. The UI
policy requires confirmation immediately before materially new App access is
created. App registration/install and key provisioning remain real unperformed
actions. No new credential may be provisioned before adoption review.

After qualification, the existing repository-admin credential can bind both
mandatory check contexts to the actual positive App ID, with strict current-base
checks and all existing protections preserved. Digitala currently lacks required
checks. Runtime/Office currently have `app_id:null`. Kundstart is private under
Nortropic's free plan: server protection returns HTTP 403 requiring a paid plan
or visibility change; neither is authorized here. Do not lower protections.

The Publisher verifies GitHub's App identity, exact head, completed/success,
unambiguous complete readback and `external_id`, whose opaque digest binds the
task, entire subject and independent review. The integration receipt retains
check-run IDs. Prior equal checks are reconciled after acceptance runs again;
wrong or ambiguous results stop instead of blindly posting duplicates. An API
response lost after a side effect is diagnosed through readback on the next
explicit invocation. No automatic retries or self-authored PAT statuses exist.

GitHub primary documentation:
[check runs](https://docs.github.com/en/rest/checks/runs),
[App manifests](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest).

## Qualification boundary

Targeted regressions use real Git objects and an actual acceptance subprocess,
with an explicitly fake App transport. They cover positive issuance, wrong App,
wrong candidate/task/acceptance/review, missing acceptance, actual failure,
expired requests, changed main, symlink/public authority and replayed bindings.
They also exercise ordinary `Publisher.issue_checks` through a real integration
worktree, reject an unrelated clone, and reject candidate import-time exit 0,
arbitrary success output and incorrect domain behavior before App authentication.
The real native-boundary probe uses a synthetic canary; it proves denied source
writes, denied external reads/writes/network and permitted scratch output. Neither
proves that GitHub accepts this App or rejects forged checks on a real protected
branch. Those live positive/negative checks remain required after installation.
