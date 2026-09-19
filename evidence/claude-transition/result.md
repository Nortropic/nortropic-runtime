# Claude adapter preparation — not yet the real executor transition

Base is PR10 main287eb84; previous qualification receipt is preserved alongside
its evidence. The same DevelopmentTask now has a guarded native access signal,
uses the existing guardian for Claude, and feeds frozen candidates through the
existing host acceptance/review/publication path. No new dependency or API billing.

Measured, without model/remote publication calls:
- replay.json: native replay of actual report20 events, completed evidence23,
  abrupt-worker recovery33; no history reset or activity execution.
- native-fixture/result.json + history.json: same workflow preserves interrupted
  first attempt and source, retries after explicit diagnosis, waits after Codex2,
  refuses wrong-attempt signal, reconstructs on fresh worker, continues Claude3
  and Codex4, then performs one simulated publication. Duplicate access signal
  does not create another attempt. This is explicitly fixture activity output.
- partial-candidate-rejected.json: complete acceptance rejects the unchanged
  preserved first-phase implementation (16/33 observations fail, as expected; all15 existing candidate tests pass).
- targeted-tests.log / support-tests.log / sdk-tests.log: terminal error/ambiguity,
  exact prior-task/scope checks, preserved source/base transition and partial-state
  refusal, existing input/protection/process/socket regression checks.

Host preparation retains the original workspace and verifies all three inherited
source bytes against attempt2. Revised accepted input binds original task digest,
expected attempt2, same allowed files/prompts/limits, current base and full verifier.
Its actual input file is intentionally prepared after adapter integration, so the
publication base will be current. It must be preserved/reviewed before invocation.
Current canonical database and real candidate have not been mutated by this slice.
No real Claude executor continuation or full v0.1 completion is claimed here.

Pre-freeze acceptance correction: initial unittest module invocation could not
resolve the candidate's normal sibling import. Use the documented discovery
command and sandbox-writable TMPDIR, as the established evidence verifier does.
The initial raw failure is preserved in partial-candidate-rejected-initial.json;
the corrected check runs on an isolated byte-identical snapshot and passes all15
candidate tests while still rejecting every unimplemented Claude requirement.
CLI assertions now check status/usage/cost as well as exit code and determinism.
This corrects the harness and closes a coverage gap before real implementation;
no candidate source or accepted outcome changed. Separate delta review required.
