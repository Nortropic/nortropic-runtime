---
tracker:
  kind: github
  provider:
    repo: Nortropic/nortropic-runtime
    token: $GITHUB_TOKEN
  active_states: [open]
  terminal_states: [closed]
  required_labels: ["runtime:probe-b1"]
polling:
  interval_ms: 5000
workspace:
  root: "/Users/elinhaggstrom/Nortropic Runtime/.runtime/workspaces"
hooks:
  after_create: python3 "/Users/elinhaggstrom/Nortropic Runtime/scripts/probe_hook.py" create
  after_run: python3 "/Users/elinhaggstrom/Nortropic Runtime/scripts/probe_hook.py" preserve
  timeout_ms: 30000
agent:
  max_concurrent_agents: 1
  max_turns: 1
  max_retry_backoff_ms: 300000
codex:
  command: python3 "/Users/elinhaggstrom/Nortropic Runtime/scripts/probe_bridge.py"
  approval_policy:
    reject:
      sandbox_approval: true
      rules: true
      mcp_elicitations: true
  thread_sandbox: workspace-write
  turn_timeout_ms: 90000
  stall_timeout_ms: 90000
---
You are executing the explicitly accepted isolated fixture {{ issue.identifier }}.
Read input.csv and create only result.json containing the row count and integer
sum of the value column, using keys count and sum. Do not change input.csv or
AGENTS.md. Do not publish, access credentials, use network or do unrelated work.
The host verifies and preserves your result; finish after producing the file.
Task source: {{ issue.title }}
