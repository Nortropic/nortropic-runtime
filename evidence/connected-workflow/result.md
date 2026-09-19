# Connected workflow qualification (support only)

The real local Temporal service executed DevelopmentTask with explicit fixture
activities. `native-fixtures-v2/result.json` records seven outcomes: success,
failed test, rejected/missing/stale/self review, and ambiguous publication.
The last case required an explicit native reconciliation signal, called no extra
implementation or review, and produced one simulated remote mutation across two
publication calls. No model or GitHub write occurred in these fixtures. Original
six-case evidence remains in native-fixtures/.

`replay-v2.json` records successful native replay of both preserved actual report
histories. The old report remains waiting for Claude; no changed completion claim.
Sixteen support tests passed, including real local Git object freeze/parent/hash,
refusal of out-of-scope deletion and symlink source, and malformed/missing/duplicate
or conflicting structured review rejection. Source: scripts/test_connected.py.

The bounded service/submit CLI and actual reviewer/publication activity wiring
still need independent review and a real accepted task. Candidate Git bundle is
preserved before verification so an activity acknowledgement failure does not
lose the unique candidate object. No general exactly-once, detached-process
fencing, Claude support or complete v0.1 claim is made.
