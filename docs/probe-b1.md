# Accepted isolated engine probe B1

Purpose: determine whether existing Symphony discovers an explicitly accepted
GitHub issue, creates its workspace, invokes subscription-backed Codex, and
preserves a verifiable result through its own lifecycle hook.

Task: read the supplied input.csv (header name,value; alpha=7, beta=-2, gamma=5).
Create only result.json containing the JSON object {"count":3,"sum":10}.
No code installation, credentials, external network, publication or other work.
Do not change input.csv or AGENTS.md. Acceptance is exact parsed JSON equality,
unchanged input, no unexpected artifacts, a preserved artifact hash and protocol
trace showing actual discovery/dispatch and execution. Missing/malformed/wrong
result fails. A successful model final message is insufficient.

Before implementation: host verifier and workflow define these requirements
outside candidate write access. First successful instruction probe cost:
17,016 input tokens (12,160 cached), 28 output, 6.137 seconds. Expected fixture
requires one short model turn; exact consumption is measured afterwards. Paid API
spend is unauthorized. Use ChatGPT auth and no API-key overrides.

Run limits: one active engine (flock), max_concurrent_agents=1, max_turns=1,
180-second app-server bridge cap; upstream silence/stall limit 90 seconds;
240-second experiment plus at most 4 seconds cleanup. Durable one-launch marker
blocks another model attempt. No automatic retry of auth/quota failures. A new
experiment requires a stated changed prerequisite. No broad implementation is
claimed from these experimental scripts.

Coordination baseline without engine: an operator would fetch the issue, choose
and create workspace, launch the agent with the task, collect its result and
move the tracker out of dispatch state. In this probe Symphony should perform
discovery/workspace/launch/hook invocation. Trusted hook verifies and preserves,
then removes the unique dispatch label. Driver supplies configuration, initial
accepted issue, starts/stops the bounded experiment, and assesses the evidence.
Johnny is not asked to relay outputs or trigger these internal transitions.

Controlled negative test: malformed/wrong/missing result must fail the same
host verifier. Full process-interruption recovery belongs to step D; the limiter
regression is only a safeguard, not proof of Runtime recovery.
