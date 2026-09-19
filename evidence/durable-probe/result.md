# Durable engine compatibility result

Tested code: 9b770d1; Darwin arm64, Python3.12, temporalio1.33.0 and four
hash-pinned wheel dependencies; Temporal CLI1.9.1 embeds server1.32.0.
Command: `.runtime/temporal-venv/bin/python -m experiments.durable_probe.run`.

Measured: workflow reached waiting with executions=1 and one first side effect.
Duplicate start with the same running workflow ID was rejected. Both worker and
server were abruptly killed via SIGKILL. New server using the same SQLite file
and a fresh worker restored waiting/executions=1. First effect was not repeated.
An explicit signal continued the workflow, returning done/executions=2 and one
second effect. Both activities report attempt1. Elapsed3.036s; model calls0.
All four tracked process groups removed; no residual matching workers observed.

Raw result and command/PID timeline: run/result.json; native events: run/history.json;
side effects: run/effects.json; startup logs adjacent. No stub or mock engine.
The SQLite file remains under .runtime/durable-probe/temporal.sqlite, outside temp.

Scope: proves completed-step replay and durable waiting across an actual local
restart for this workflow. It does not prove exactly-once arbitrary side effects,
recovery after an activity effect but before server acknowledgement, single-writer
model interruption, provider swap, trusted acceptance, or GitHub integration.
The development server is confined to local testing; production is out of scope.
