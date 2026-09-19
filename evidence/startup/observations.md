# Establishment observations — 2026-09-19

Commands executed by the chain driver; summaries below are observations, not raw
terminal exports. Structured server outputs are retained beside this file.

- `pwd`, `ls -la`, `git status`: requested project directory initially empty, no repo.
- Entire supplied mandate read, then copied byte-for-byte into docs.
- `git init -b main`; first commit `f2863dfad202b00297dfe477ebe58b21a6da92ad`.
- `gh repo create Nortropic/nortropic-runtime --private --source . --remote origin --push`
  succeeded; `gh repo view` returned PRIVATE and `git ls-remote origin refs/heads/main`
  returned the same commit. See `remote.json` for a second server observation.
- `gh auth status` outside sandbox: authenticated Jonkebronk, repo scope.
- `codex login status`: ChatGPT. `claude auth status` outside sandbox: claude.ai / Max.
- Git 2.55.0; gh 2.97.0; codex-cli 0.147.0; Claude 2.1.257; Darwin arm64.
- No API-key/provider environment override present (names inspected, no secrets logged).
- Global Codex AGENTS empty, no override; no ancestor AGENTS/CLAUDE files found.
  Claude managed policy was read and remains unchanged; it contains deny rules and
  DISABLE_AUTOUPDATER=1. No global instruction/hook/security settings changed.
- `gh api repos/Nortropic/nortropic-runtime/branches/main/protection`: HTTP 403,
  message `Upgrade to GitHub Pro or make this repository public to enable this feature.`
  Neither a paid upgrade nor public visibility is authorized.
- Official Symphony binary release ID 389513981 names source
  be10a1b79df723d6d7612b5651c8522704dafb2e. Downloaded arm64 package SHA256:
  96cea8e769bd5225c2b5a26abca3dd3368bd769d5c045917f4cc078d1f86dc40,
  matching the published checksum. `symphony-release.json` records server metadata.

## Separate review and continuity check

Separate agent process `/root/startup_review` inspected f2863df without writes.
Verdict: no blockers for the founding documents; not a step-A or v0.1 approval.
It located mandate, boundaries and next step from the repository. Advisory findings:
update completed remote creation in plan, identify active chain driver, preserve raw
evidence. It did not independently check live remote, auth or process termination.
This demonstrates contextual navigation, not Claude execution or a full takeover.

## First model experiment contract

Read-only instruction loading: fresh Codex and Claude sessions at root, then docs.
Prompt asks for the probe identifier without providing its value. Expected:
NR-CONTINUITY-7392 and correct plan path. Tool set for Claude is Read only;
Codex sandbox is read-only, approvals reject. No publication or source changes.
Per process: 240-second hard wall limit, zero automatic retries; process exit or
structured output is observable activity, final matching answer is progress.
Timeout is an inconclusive run, not a quota failure. Known quota/auth failure means
stop that provider until explicit capacity evidence or provider reset time; no probes
more often than 60 minutes absent changed evidence. Limits are technical safeguards,
not an owner budget or project deadline. Inspect first usage before further calls.
