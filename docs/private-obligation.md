# AP10 private named obligation — qualification contract

One existing Temporal service/database and activity queue carry development and
private work. DevelopmentTask retains its tests, independent review and protected
Publisher. PrivateAssessment has no publication activity or candidate path. The
Office owns source selection, applicability, AP05/AP06 use and report meaning.
This increment alone does not authorize claiming operational phase completion.

## Pinned local activation

scripts/install_ap10 stages exact integrated Runtime and Office Git objects,
selected regular private context and hashes. Selecting that release changes no
running process. It refuses a living recorded daemon/engine/worker. Native CLI
instructions/configuration are bound; a changed instruction input makes execution
unavailable rather than silently changing authority. Ordinary source branch
changes cannot change frozen active Python. Private context never goes to Git.

The user LaunchAgent is `~/Library/LaunchAgents/se.nortropic.ap10-runtime.plist`.
It runs the pinned local daemon at login, with RunAtLoad and no KeepAlive restart
storm. It has no timer; Temporal alone schedules. It listens only on existing
loopback ports. A logged-out/asleep/off computer offers no background guarantee.
Active config, process identities, DB and private evidence live in `.runtime/`.

## Native obligation control

Run `python -B -m runtime.obligation ACTION` with the existing Runtime virtualenv
from the Runtime root. It delegates to the active release; it never starts a
service or installs software. Only `office-python-temporal` is supported.

- `install`: create paused; a duplicate refuses without resetting state.
- `daily`: requires paused and no own in-flight work; select 09:00 Europe/Stockholm.
- `test --after-seconds 60`: explicitly labeled one-shot qualification, not days of
  service. Requires paused/no own in-flight work. It remains paused until resume.
- `resume`: explicit unpause. STOPPED requires explicit reconfiguration first.
- `pause`: prevent new starts, preserve state across worker/login return; an
  already active round may finish. Pausing STOPPED keeps its terminal note.
- `stop`: persist STOPPED, cancel only executions reported by this schedule, wait
  for cancellation and verify recorded private group cleanup. An unresolved
  identity/group raises incomplete stop; no claim that failure means clean stop.
  It never stops the shared service or unrelated development tasks.
- `status`: native dated read only; no models, signal, source fetch or publication.

Unregister login start only after own obligation stop and checking unrelated
builds: `launchctl bootout gui/$(id -u)/se.nortropic.ap10-runtime`; preserve the
plist outside LaunchAgents then remove that named plist. This stops shared engine
and worker, so do not use it as the normal obligation pause/stop command. Keep the
canonical DB, frozen releases, task histories and private results. Restore only
through a separately diagnosed operation, never an automatic empty DB/reset.

## Bounds and failure semantics

Daily Schedule has BUFFER_ONE and an explicit 22-hour catchup window. This is
strictly shorter than the minimum 23-hour spacing of Stockholm09 occurrences
at spring DST. At most one past occurrence is eligible on return, not all absent
days; an older missed occurrence is a gap. A return very near the following
planned time may be followed by that new on-time occurrence; BUFFER_ONE can
queue it while the caught-up current assessment finishes.
No backfill command is exposed. Previous and actual observation times remain
separate; missed/paused/sleep periods are gaps, not reconstructed observations.
One activity slot serializes builds and private work. The round execution/run
limit is 1,200 seconds including native queue time. Activity bounds are intake90,
analysis480, review240, report60 seconds plus bounded cleanup; queued stages can
expire. These are per-round limits, not a development-project deadline.

At most one analysis call and one separate reviewer call per native run; activity
and workflow maximum_attempts=1. Exclusive run/stage/budget markers are consumed
before launch; process restart/redelivery cannot refund a call. No same-round
model retry. A missing/incomplete review cannot become a reviewed positive result.
Unchanged completely observed basis can reuse a previously reviewed scoped result
without new model work. Quota/auth/network loss is unavailable; later independent
daily observation may try again, with no quick loop or paid fallback.

Private model receives selected frozen copies and writable scratch only, no
publisher credentials/network/source-code/schema authority. Parent loss and typed
cancellation clean its group; retained launch identities prevent starting another
private invocation while a prior private process remains unresolved. A hard-killed
unidentifiable guardian requires operator diagnosis, never blind restart.

The host captures stdout/stderr through bounded pipes, at most 1MiB per file
(2MiB combined), then stops the provider group on overflow. No process-wide
file-size limit is applied to the native CLI's own state files. The actual exit
code is preserved even when startup fails before a structured provider event.
A periodic
512MiB capacity guard covers rounds, workspaces/scratch and dispatch; a new stage
reserves 64MiB headroom. This is a stop-on-observed-growth safeguard, **not** an
exact filesystem quota: bursts between samples can overshoot it. No historical
files are deleted to hide capacity failures. There is no exact token, subscription
quota or money promise; available provider usage and elapsed time are preserved.

AP08 is a dated picture, not live monitoring/active notification. Later status
must distinguish native scheduling, actual observations, reviewed judgment and
missing evidence. A process start is never a successful monitoring receipt.
AP09's prior decisions/gaps and all previous audit statuses remain unchanged.
