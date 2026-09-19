# Nortropic Runtime

Build a business-neutral runner for accepted development tasks. Follow the mandate
in `docs/UPPDRAG-NORTROPIC-RUNTIME.md`; resume from `docs/plan.md` and read relevant
entries in `docs/decisions.md`. README provides the human entry point.

Work only in this project and explicitly isolated test targets. No production
changes, new paid API usage, subscriptions, or expanded external permissions.
Keep acceptance inputs and publication authority outside candidate write access.
Use separate review before integration. Preserve evidence and work on the configured
origin continuously. Do not treat backup branches as approved integrations.

Operator support tests: `python3 -m unittest discover -s scripts -p "test_*.py" -v`.
Repository checks: `git status --short --branch`, `git diff --check`. Runtime v0.1
is not yet delivered; run the live experiment only from the current plan.
Fresh receivers first read and inspect without writes and verify old writers have
stopped. The living plan owns next actions and run state; do not duplicate it here.

Instruction-loading probe identifier: `NR-CONTINUITY-7392`.
