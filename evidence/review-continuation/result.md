# Review continuation — bounded verification

The v0.1.0 tag and its original evidence are unchanged. This change closes the
permanent waiting_review gap; no new engine, business source or permission grant.

Measured:
- native-v3/result.json: eight native Temporal workflows, actual immutable Git
  candidates, test subprocesses, separate review-verifier subprocesses and gated
  atomic local Git integrations. Rejection repairs the same task; failed repair
  tests and unchanged source stop at diagnosis; missing/nonobject/stale/self/
  inconclusive review resumes review only. Each original history is an exact
  prefix; old results remain, one integration per task. Wrong/stale/duplicate
  signals schedule no extra work. Candidate bundles and source bytes are retained.
- legacy-restart/result.json: read-only backup of original v0.1 fixture DB, same
  previously waiting workflow, service+worker restart, review-only recovery with
  one implementation retained. No mutation of original fixture or canonical DB.
- replay.json: original report wait, final real report (49 events), completed
  evidence task, recovery history, old rejected/missing waits and eight new
  completed histories all replay with no activity/model calls.
- support-tests.txt, sdk-tests.txt, adapter-tests.txt: focused classification,
  existing support checks and adapter numbering/old-receipt preservation pass.

Explicit limits: native-v1/v2/v3 providers are deterministic fixtures, not model
calls. Their review verifier runs in a separate process but is a declared trusted
fixture, not qualification of an arbitrary reviewer sandbox. Integration there
is local Git, not GitHub. The existing actual model/sandbox/publisher qualification
from v0.1 remains the baseline; this slice tests the changed continuation protocol
and numbered real-adapter contract. No claim of unattended diagnosis or arbitrary
business-target support is made. The chain driver still makes explicit technical
recovery decisions from preserved evidence within the accepted mandate.

Preserved previous outcomes:
- source-review-1/rejected.patch + review.md: separate reviewer found nonobject
  evidence could crash recovery; corrected with guarded classification and native
  nonobject proof. This rejected source was never integrated.
- native-v1: seven cases passed before adding the nonobject case.
- native-v2: actual nonobject recovery completed, then the proof harness failed
  because it indexed an intentionally absent query field. Original results and
  harness-failure.json retained; harness uses get now. Runtime was not changed to
  hide this test error. native-v3 is the complete eight-case rerun.

Separate final exact-revision review and protected integration are recorded by the
host after this evidence candidate is committed. Until then this is a tested
candidate, not an approved integration. No release tag is moved.
