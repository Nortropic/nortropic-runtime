# Separate review record (model assessments, not raw execution)

Reviewer process: /root/startup_review; read-only, no publication, not author.

- f2863df: no blockers for founding documents. Located mandate and next action.
  Not a full takeover or Runtime acceptance; private server/auth not checked by reviewer.
- Protection config initial SHA256 0b00bff0d59b5886ae3c670cca7eb7589bf5e4edaed3d00ec9298c4b0767fb52:
  no blockers for limited activation. app_id=-1 does not authenticate status producer.
  Actual server validation required (later corrected contexts/checks payload conflict).
- 4dec677: BLOCKED limiter. TERM-ignoring child survives leader exit; helper SIGTERM
  not handled. Corrected in 521f2e7; three real-process regressions support correction.
- 521f2e7: BLOCKED B1 verifier. AGENTS.md absent/modified was accepted. Positive test
  itself lacked AGENTS.md. Other B1 restrictions judged proportionate, not proven safe.
- 0c4117d53a74ccac73fe4ff0e187c22c28879b85: targeted finding closed. Host constant,
  bytes/existence/symlink checks and negative tests inspected. B1 may run.
- 3b5c3f4940d00ac6c749ccfc5afd5c6e8d963f54: targeted protocol delta has no blockers.
  Raw attempt1 fails before model; schema supports never. Same sandbox retained;
  attempt history preserved. Attempt2 may run; live outcome still to be assessed.

Review scope remains the bounded establishment/experiment delivery, not v0.1.

- 4cc50b5 result review: BLOCKED summary, not artifact. Observed cua_repl/codex_apps
  ready notifications contradicted intended MCP disabling; no completed MCP calls.
  Reviewer validated files/hashes, dispatch, hook, tracker return, elapsed time and
  token counts. Corrected historical report to show failed restricted-profile check,
  2% initial / 3% final quota, and stale plan statements. Profile now disabled;
  separate no-model fixed-profile inventory is new evidence, not revised history.
