# Claude qualification — actual calls, 2026-09-19

Access restored using existing claude.ai/firstParty Max. Version2.1.257,
model claude-fable-5-1, binary SHA256 in verification.json and runtime profile.
No API-key override, billing fallback, settings changes or purchase.

| Probe | Measured outcome | Seconds |
|---|---|---:|
| access-root | Subscription call works; finds plan from files; automatic loading NOT proven | 33.756 |
| automatic-root | Normal tools-disabled @ import contains marker/plan | 6.486 |
| automatic-subdir | FAIL: parent AGENTS import not loaded | 4.652 |
| boundary | Allowed write succeeds; context/unaccepted writes and outside/symlink reads denied | 30.994 |
| explicit-root | Restricted native instruction-file loader, no tools: marker/plan PASS | 4.470 |
| explicit-subdir | Same file loader from tools/, no tools: marker/plan PASS | 5.786 |
| boundary-direct | Three actual Write calls blocked; no host changes | 20.316 |

Every call had a fixed60–120s limit, zero automatic retries and recorded process
group cleanup. Each directory contains full command, timestamps, stdout/stderr,
terminal result, session identity and usage. verification.json binds stdout hashes,
actual tool requests/results and canary content hashes. It was produced by
`python3 -m scripts.verify_claude_qualification`, without another model call.

Important distinction: the new outside file Write hit the native working-directory
boundary; existing outside/symlink Write hit a read-first error. Their preceding
Read attempts in boundary were denied on resolved paths. No claim that the later
write gate itself was reached for those existing files. Bash, network tools,
Agent and MCP tools were absent. The SDK init's built-in agent-name catalogue is
not an exposed Agent tool. Hostile host code is outside this profile's claim.

Native append-system-prompt-file is the selected instruction path (D019). The
initial boundary permissions are unchanged; its later direct-write probe adds
that instruction loader. Profile resolves and checks the qualified binary before
launch, guarding against a later global CLI update. No real report candidate has
yet been changed by Claude. Executor transition is the next separate delivery.

CLI usage and total_cost_usd are retained per run; the latter is a list-price
metric, not a subscription invoice. No monetary spend was measured. Root and
subdirectory instruction tests prove context availability, not universal compliance.
