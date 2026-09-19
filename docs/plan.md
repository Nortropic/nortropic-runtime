# Living plan — Runtime v0.1

## Current step A: establish reproducible execution and test compatibility

RESULTAT: The chain can locate this new project and its mandate, then run a pinned
existing engine against an accepted harmless fixture using subscription access.

VARFÖR NU: Proves real tracker/executor compatibility before building adaptations.

METOD: A bounded compatibility experiment; inspect upstream implementation and
install hooks, define observable acceptance before first model invocation.

ARBETSYTA: `/Users/elinhaggstrom/Nortropic Runtime`, new Git history, branch `main`.
Intended private remote: `https://github.com/Nortropic/nortropic-runtime`.
Candidate engine: Symphony `be10a1b79df723d6d7612b5651c8522704dafb2e`.

FÖRUTSÄTTNINGAR: Git 2.55.0, gh 2.97.0, Codex 0.147.0, Claude 2.1.257,
Node 22 and system Python available. Elixir/mix/mise absent from PATH.
GitHub account has repo scope; org reports Free plan and repository creation allowed.
ChatGPT and Claude Max login observed; no paid API run authorized.

NÄSTA HANDLING: Resolve measured Codex CLI incompatibility: 0.147.0 receives HTTP
400 requiring a newer CLI for gpt-6-astra. Install official pinned 0.155.1 locally
under `.runtime/bin` without changing the global CLI, then repeat the root probe
once with this changed prerequisite. Claude root Read-only probe is underway;
inspect its retained result before the subdirectory probe. Run the downloaded
Symphony arm64 binary only after checksum validation and a constrained workflow.
GitHub Team decision is pending with owner; never make the repository public.

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
All runtime acceptance rows remain unproven.

ÅTERUPPTAGNING: Root chain driver active; startup_review agent finished its read-only
review. No Symphony process launched. Old Codex probe exited (code 1); bounded
Claude root probe may still be active—check run.json and PID before any relaunch.
No older project modified. Read AGENTS, mandate, this plan, decisions; inspect Git, remote and
current processes before writes. Evidence will be linked here as produced.

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
