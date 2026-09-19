# Living plan — Runtime v0.1

## Current step A: establish reproducible execution and test compatibility

RESULTAT: The chain can locate this new project and its mandate, then run a pinned
existing engine against an accepted harmless fixture using subscription access.

VARFÖR NU: Proves real tracker/executor compatibility before building adaptations.

METOD: A bounded compatibility experiment; inspect upstream implementation and
install hooks, define observable acceptance before first model invocation.

ARBETSYTA: `/Users/elinhaggstrom/Nortropic Runtime`, new Git history, branch `main`.
Remote (initially private, now public by explicit owner decision D006): `https://github.com/Nortropic/nortropic-runtime`.
Candidate engine: Symphony `be10a1b79df723d6d7612b5651c8522704dafb2e`.

FÖRUTSÄTTNINGAR: Git 2.55.0, gh 2.97.0, Codex 0.147.0, Claude 2.1.257,
Node 22 and system Python available. Elixir/mix/mise absent from PATH.
GitHub account has repo scope; org reports Free plan and repository creation allowed.
ChatGPT and Claude Max login observed; no paid API run authorized.

NÄSTA HANDLING: Obtain separate review of the corrected process limiter and narrow
B1 fixture scripts, then run `python3 scripts/run_motor_probe.py` from repo root.
Accepted source: https://github.com/Nortropic/nortropic-runtime/issues/1.
Acceptance, coordination baseline and limits: docs/probe-b1.md. Inspect actual
protocol/artifacts/tracker transition and negative verifier results before calling
B1 successful. Claude remains WAITING_ACCESS (D005), no repeat calls.

PROV OCH KLART-NÄR: Private remote/identity verified; correct instruction probe from
fresh root/subdirectory sessions; executable engine path and acceptance fixture
identified. Wrong/missing access must be reported as failure, never a pass.

UTFALL: Private origin created, initial revision f2863dfad202b00297dfe477ebe58b21a6da92ad
pushed and independently reviewed (no blockers for founding documents). Pinned
Symphony source and official binary fetched; SHA256 matches. See
[observations](../evidence/startup/observations.md), [remote](../evidence/startup/remote.json),
[release](../evidence/startup/symphony-release.json). First Codex call failed in
4.174 seconds with a CLI-version error; [raw run](../evidence/startup/codex-root/run.json)
and adjacent stdout/stderr are preserved. No successful model usage metrics yet.
Codex 0.155.1 + matching code-mode host installed locally. Root and docs instruction
probes passed (evidence/startup/codex-root-0155 and codex-subdir); root used 17,016
input/12,160 cached/28 output tokens, docs 17,019/12,160/35. Public main protection
is active and a real missing-status/direct push was rejected; see D007 for first
failed activation incident. Process-limiter regressions and fixture positive/
negative checks pass in evidence/startup/operator-tests.log. No live engine yet.

ÅTERUPPTAGNING: Branch work/execution-probe, main currently 4dec677 due to D007.
Root chain driver active; separate reviewer finished first limiter review, fix
awaits delta review. No engine launched or model process active. Download/probe
processes all completed. Verify PIDs and `git status` before starting a fresh writer.
Host dependencies under .runtime are reproducible from exact official revisions;
raw experiment artifacts are under evidence and preserved on the work branch.

## Subsequent deliveries (refine only the next active step)

B. Existing engine automatically discovers accepted fixture, executes Codex,
preserves tested result; measure engine vs agent vs manual actions; negative case.
C. Claude official program interface through same path, including tools and errors.
D. Real Codex → Claude → Codex continuation; persisted attempts, interruption,
single writer, durable capacity wait, no duplicate publication.
E. Exact-candidate tests and separate review; legitimate integration and rejection
of missing/failed/stale evidence, actual server state reconciled after ambiguity.
F. Useful Customer Zero task with executor swap, then another accepted task using
same path. All mandate §1 rows need linked revision/environment/raw evidence.

## Acceptance evidence index

| §1 capability | Status / evidence |
|---|---|
| Autonomous completion | NOT RUN |
| Persistent continuity | Separate read-only review located next action; Claude and full takeover NOT PROVEN |
| Replaceable execution | NOT RUN |
| Interruption/capacity | NOT RUN |
| Controlled integration | NOT RUN |
| Repeatable use / Customer Zero | NOT RUN |
