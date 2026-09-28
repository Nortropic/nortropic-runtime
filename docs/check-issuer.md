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
and `acceptance.py` as owner files (0400/0600), outside candidate write access.
The request contains `schema: nortropic-issuer-request/1`, exact `task`, `subject`
and normalized independent `review`, SHA256 of the actual `review.json` and
`acceptance.py` bytes, and UTC `accepted_at`/`expires_at` (at most 24 hours apart).
The task's existing acceptance digest remains bound too; `acceptance.py` is its
separately frozen executable acceptance, not a program supplied by a candidate.
A task/acceptance change requires the holder to inspect the actual new source and
seal a new request. Acceptance and review are not inferred from keywords.

The issuer checks target, exact base/current remote main, one candidate commit,
allowed paths, complete independent review, request freshness, immutable blobs,
and the actual isolated acceptance exit. Failure writes private observations but
never authenticates the App or creates green checks. It rereads authority/request
and main after acceptance. Credentials are read only after its process group has
ended. Native descendants remain subject to the no-network/filesystem boundary.

The four explicit issuer targets are Runtime, Office, Digitala and Kundstart. This
does not widen Runtime's ordinary task/Publisher target mapping: that remains
Runtime/Office. Digitala needs its existing legitimate protected publication
holder to call the same issuer with a sealed task; Kundstart additionally has the
verified private-plan protection blocker.

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
No browser is available to this session. Existing API reads show Jonkebronk is an
active Nortropic org-admin and repository admin, so an additional org membership
is not the blocker. App registration/install and key provisioning remain real
unperformed actions. No new credential may be provisioned before adoption review.

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
The real native-boundary probe uses a synthetic canary; it proves denied source
writes, denied external reads/writes/network and permitted scratch output. Neither
proves that GitHub accepts this App or rejects forged checks on a real protected
branch. Those live positive/negative checks remain required after installation.
