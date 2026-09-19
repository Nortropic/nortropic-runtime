# Real report task completed through Codex → Claude → Codex

Same native workflow runtime-run-report-1, original accepted task from tasks/run-report.json.
Attempt1 was deliberately interrupted when a host-verifier boundary defect was
found; D014 records its separately reviewed correction. Attempt2 implemented the
Codex phase and waited for the unavailable Claude subscription. Owner later restored
access. D019 qualifies the existing Max route; D020 records an explicitly reviewed
base/full-verifier continuation. Neither outcome, source scope, prompts nor limits
changed. The old workspace and exact source snapshots remain available.

Runtime then invoked actual Claude attempt3 (147.813s), retained its implementation,
passed33 host observations including28 candidate tests, and automatically invoked
actual Codex attempt4 on the same workspace. Codex found/fixed numeric overflow and
decoder-depth CLI crashes, completed in131.891s, and passed33 host observations
including30 candidate tests. No parent edits or prompt relay occurred between them.
All provider groups were removed before the next step.

The frozen final Git candidate is f86a85c27d7cb2567d3c600292f213fa45067b7a on accepted
base531f097c85a42ac5afc86ace6bd8ee7f37fc5b8d. Fresh read-only reviewer
01a0b9ae-eec2-7603-9f1f-c5286fcfde12 approved in26.755s, with no blockers; it also
ran23 parser tests and16 independent read-only CLI checks. This identity differs
from all four implementation sessions. Runtime published once through protected
PR12 https://github.com/Nortropic/nortropic-runtime/pull/12 and read back merge
98b92a72da2671c0a517f674f8b023667c070bcb, exact tree659eb238b4a4425c660d25dae15c2b1f42128615.

continuity-proof.json records actual native activity order and proves all20 old
history events are the exact prefix of the final49. Attempts remain1..4; publication
counter1. The report's fresh restart returned identical completed state without
new model calls/publication; evidence/v0.1/restart-and-state.json covers both tasks.
Canonical SQLite remains .runtime/runtime.sqlite; compressed final backup and hashes
are under evidence/v0.1/. Original pre-transition backup is under access-prestate/.

Real use: real-use/result.json records the delivered CLI on five actual streams.
Claude attempt3 reports completed; historical403 reports failed despite success
subtype; interrupted Codex1 reports incomplete with unknown usage. Codex2/4 report
failed because their raw streams include failed diagnostic/test/permission items,
even though later turn completion and external acceptance passed. This is the
explicit accepted conservative reporting rule, not Runtime task acceptance.
An initial use-check incorrectly expected completed for Codex2; its failed assertion
and corrected interpretation are preserved in real-use/initial-expectation.json.
No candidate or acceptance requirement changed to make this use check pass.

Measured provider resources (reported fields, not additive pricing quantities):

| Invocation | Seconds | Input | Cached input/read | Cache creation/write | Output |
|---|---:|---:|---:|---:|---:|
| Codex1 interrupted | 34.166 | unknown | unknown | unknown | unknown |
| Codex2 implementation | 134.029 | 240607 | 202368 | 0 | 6151 |
| Claude3 continuation | 147.813 | 170 | 41554 | 21068 | 14181 |
| Codex4 completion | 131.891 | 392812 | 352896 | 0 | 5176 |
| Codex independent review | 26.755 | 57205 | 33408 | 0 | 1186 |

Claude reported list-price metric1.1435075USD; this is not a measured charge under
Max. All model work used existing subscriptions, with no API fallback/purchase.
Qualification's7 short calls consumed106.460s; each raw usage object remains under
evidence/claude-qualification/. Chain-driver/interactive reviewer total usage and
actual subscription monetary attribution are unknown.

Manual coordination: root established the route, authored/reviewed acceptance,
corrected the first verifier defect, sent its explicit diagnosis, later qualified
restored access, and submitted one reviewed continuation signal. Runtime handled
Claude→Codex→host tests→fresh review→protected merge without owner prompting or
manual candidate changes. Owner chose visibility/access and closed a competing
interactive session. The useful output replaces manual log-status/usage extraction;
it is not approval of a general project-office product or a medical benefit claim.

Evidence naming note: historical operator PR4 integration receipt occupied the
legacy integration.json filename. Runtime's final task receipt now occupies it;
the old receipt is restored byte-for-byte from preserved Git531f097 as
phase1-integration.json. Neither historical receipt nor source history was lost.
