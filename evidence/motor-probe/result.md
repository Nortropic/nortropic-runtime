# B1 actual result — attempt 2

Tested operator code revision: 3b5c3f4940d00ac6c749ccfc5afd5c6e8d963f54.
Symphony source be10a1b79df723d6d7612b5651c8522704dafb2e, official arm64 binary
SHA256 96cea8e769bd5225c2b5a26abca3dd3368bd769d5c045917f4cc078d1f86dc40.
Codex 0.155.1 with matching official code-mode host; gpt-6-astra; ChatGPT Pro;
Darwin arm64. Workflow and issue acceptance committed before execution.

Measured: upstream engine discovered GH-1, created/reused its isolated workspace,
started app-server, completed one turn, called host after_run hook. Hook checked
exact output, unchanged input/instructions and allowed artifact set; preserved
files and SHA256s; removed the dispatch label. Engine process group was removed.
Live issue readback: OPEN with no dispatch label. It is retained for evidence.

Evidence: engine/run.json (21.04 seconds); engine/logs/log/symphony.log.1;
GH-1/protocol.jsonl (84 protocol records); GH-1/verification.json (passed=true);
GH-1/artifacts/result.json; GH-1/tracker-transition.json (exit_code=0).
Last reported cumulative usage: input 96,010; cached input 88,704; output 364;
reasoning output 0; total 96,374. These are protocol counters, not an inferred
currency charge or entire-project usage. Weekly usage reported 2% initially and 3% in the last event;
too coarse and account-wide to assign the full difference to this run. No API billing enabled.

Model created the JSON file. Engine performed discovery, execution and lifecycle
hook dispatch. Host hook verified, preserved and changed tracker routing. Driver
created acceptance/configuration, started the bounded experiment, fixed one
protocol incompatibility between attempts and assessed logs; launcher stopped
engine after preserved transition. Johnny forwarded no agent output and prompted
none of these transitions. No general autonomy or cognitive-health claim made.

Negative evidence: attempt1 preserved FAIL for missing result after handshake
error; operator test logs cover wrong/missing JSON and changed/missing instructions.
No review result or green launcher exit substitutes for those artifacts.

Limitations: no Claude execution; no restart/failover/duplicate publication proof;
no implementation task or Customer Zero integration; single known benign fixture;
upstream scheduler state is volatile. Sandbox warning for rejected /tmp xcrun
cache write occurred; actual task file was produced successfully. Model did not
receive github_api dynamic tool. Observed profile failure: cua_repl and codex_apps reached ready despite the
intended disabling. No completed MCP calls appear, but removal failed in this
actual run. Artifact PASS and engine coordination stand; restricted-profile
acceptance does NOT. Profile disabled pending a no-model inventory check and
explicitly recorded corrected configuration. No complete adversarial isolation claim.


Follow-up without a model: corrected worker command disables built-in providers
and plugin loading for that invocation. Fresh full MCP inventory is retained in
../startup/worker-profile-inventory-fixed.json: named servers disabled, zero
available tools. This targeted check does not change the historical attempt2
exposure or retroactively make its restricted-profile acceptance pass.
