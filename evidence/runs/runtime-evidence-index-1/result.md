# Actual Runtime task completion — evidence integrity CLI

Accepted input/brief/verifier were independently reviewed before implementation
at a968d314; bytes were frozen by Runtime from preserved Git objects. Source
scope is three tools/ files, accepted base5e014099. Runtime invoked Codex using
its qualified isolated profile, froze candidate38ecdaf7f989ab547740e23345c9cfbf8f69513c,
ran25 host cases (including14 candidate tests), invoked a fresh read-only Codex
reviewer, and published through the protected exact-subject boundary.

Reviewer run01a0b971-89fa-7461-87c6-c9798029f8b2 approved with no blockers. It differs
from implementation run01a0b96e-d6e8-7ae2-9ef0-fdf2bec12278. Both terminal results,
usage and cleanup are preserved. Review was actual model inspection and targeted
read-only probes; it did not rerun fixture-writing unit tests. Host acceptance
already executed those tests successfully in the qualified sandbox.

PR7 https://github.com/Nortropic/nortropic-runtime/pull/7 was automatically merged
as0fba283d5c6e19f30c9703eec88e6ea879435c16. Publisher read back merged state and
verified exact tree8597f79921cc38f2e4bb6219537f97a66c686ed5 and accepted parent/base.
Native history records one implementation, one review and one publication call.
The controller returned completed and removed both service groups. Provider groups
were also removed. A normal self-test failed during implementation and the same
bounded turn corrected it; this is retained in raw events, not erased or called
an extra Runtime attempt. Final host acceptance passed.

Actual use: the integrated CLI created real-use-manifest.json for the preserved
native database backup, candidate Git bundle and review receipt. Verification
returned all three ok (real-use-result.json), replacing manual hash calculation.

A fresh native restart/--resume returned the exact same completed state in
observations/572a19813b1148f48f9c4392a80608d5, with one attempt/publication and no
new model launches. The original report task also still returned the exact prior
waiting_access/attempt2 state after this task; observation under
../../accepted-task/observations/cac8d5c56d044ea7a65f20180fee0252.
A planned mid-review history checkpoint reached an already stopped server because
the workflow had completed; no retry or mutation followed that connection refusal.
The full final native history is preserved instead.

Measured provider resources:
- Implementation174.901s: input217881, cached183296, output9431, reasoning797.
- Review34.25s: input54856, cached32384, output1421, reasoning648.
- Cache-write input0 for both. Counts are reported fields, not additive pricing
  quantities. Existing subscription; actual monetary cost is unknown.

Manual coordination: root authored/froze the task and host assertions, arranged
one bounded input review, then issued one submission command. Runtime performed
all phase transitions and integration without candidate edits, manual handoff,
model retries or additional owner decisions. Root preserved/reported evidence,
observed restart and used the result. This is measured benefit for one specific
accepted task, not a general productivity/medical claim.

Limits: the first report task remains incomplete awaiting actual Claude access.
This second accepted task therefore does not yet prove two completed tasks or
Codex→Claude→Codex. General multiphase support and abrupt in-flight writer fencing
remain pending. Runtime v0.1 is not complete.
