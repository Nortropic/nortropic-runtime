# Heartbeat throttle observations, 2026-09-30

Order OVL-20260930-54c10b P1–P4. Isolated fresh engines only. The private
originals are in the backlog-plan-20260930/54c10b-runtime evidence directory.
Their SHA-256 digests are embedded here. Timestamp samples are copied exactly;
only host paths, process id and full load environment are omitted. These are
observations, not active-release claims.

All three observations used the exact `probe-r1.py` bytes (digest in receipts),
Python3.12.13 and temporalio1.33.0. The current executable probe additionally sets
its activity stop flag before leaving Worker on an observation exception and
waits for a complete load-result JSON write. It has not been used to replace the
retained observations.

The poll target was0.4s. Under load one observed poll gap reached0.645287s;
therefore this is a sampled upper bound on observed heartbeat gaps, not a claim
that every poll met its target. The entire load interval is inside the sampled
interval. No heartbeat timeout occurred. Both60-second unladen runs had maximum
poll gaps below0.5s. The heartbeat throttle cap in both production workers is2s;
activity timeouts and ap10_quiet are unchanged.
