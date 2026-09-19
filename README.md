# Nortropic Runtime

A local runner for accepted, bounded development tasks using Temporal and existing
Codex/Claude subscriptions. Two useful tasks have completed through external tests,
independent review and protected integration, including a real Codex → Claude → Codex
continuation. Final v0.1 release checks are tracked in [the living plan](docs/plan.md).

Start with the plan, [mandate](docs/UPPDRAG-NORTROPIC-RUNTIME.md) and
[decisions](docs/decisions.md). Shared executor instructions are in `AGENTS.md`.
The [verification record](docs/runtime-v0.1.md) maps requirements to actual evidence
and limits; the [runbook](docs/runbook.md) explains start, inspection and resumption.

Delivered tools:

- [Run report](tools/README.md): summarize actual Codex/Claude JSONL status and usage.
- [Evidence integrity](tools/EVIDENCE_INDEX.md): create and verify file-hash manifests.

Both existing Runtime tasks are completed. Follow the plan before running commands;
do not resubmit them or delete state. New development needs a new accepted task.
