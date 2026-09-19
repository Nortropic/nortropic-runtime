# Host publication boundary — implementation and local tests

D016 selected old publication test ideas, not old code/authority or historical PASS.
New runtime/integration.py requires whole-task completion, frozen task+acceptance
identity, exact candidate, completed successful tests, approved independent review
without blockers, and authorized target before remote mutation. An incomplete
Codex→Claude→Codex task cannot publish after its first phase passes.

Real local Git tests show scope rejection, immutable commit selection despite
changed checkout bytes, and exact merged-tree/base verification. Counted remote
fixtures show missing/failed/interrupted/stale/wrong-scope evidence rejects before
push/API mutation, post-push changed base/head prevents merge, and a lost merge
response (injected after the simulated server mutation) is reconciled without
another publication.6 tests passed, including
multiple negative cases in rename-regression.log (initial5-test log retained). These are simulations at the remote
boundary, not evidence of an actual automatic Runtime merge.

Actual read-only GitHub protection lookup passed the publisher's prerequisites;
raw protection-readback.json retained. Previous live negative/legitimate GitHub
proofs remain in evidence/integration and PR2/3/4. New publication implementation
has NOT yet performed a live merge; connect it to a second accepted task next.

Trust boundary: the workflow/controller must construct these receipts from its
own actual runs outside candidate write access. require_gate does not authenticate
arbitrary caller-created dictionaries. Candidate cannot be the caller holding
publication credentials. The next connected delivery must demonstrate that wiring,
independent review invocation, exact-source binding and receipt preservation.
Current API limits target to this project, ordinary push, one commit on accepted
base and protected squash integration. No deletion/submodule publication support.

Separate review found a real rename-scope bypass in the initial candidate8976fef:
Git --name-only reported only the allowed destination while deleting an unallowed
source. Corrected to --no-renames plus NUL-separated paths, with a real local Git
reproducer/regression. No publication was attempted from the rejected revision.
Also refined lost-response test to actually raise after simulated merge mutation,
then reconcile without a new remote mutation. This remains fault injection, not
a measured network outage.
