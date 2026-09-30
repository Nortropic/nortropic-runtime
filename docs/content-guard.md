# Publication content guard

OVL-20260930-1225ac I1: the publisher and separately adopted issuer scan complete
added or modified regular blobs. A change to the candidate scanner cannot change
the host scanner. A changed symlink, unreadable blob or blob larger than 64 MiB
refuses. Output contains path, line and category, never the matched value.

The optional fixed policy is `~/Library/Application Support/Nortropic/content-guard.json`,
where `~` is the OS account home, never an environment override. It and the literal
file must be private regular files owned by that account, outside every repository,
with no symlink parents. Nothing installs them merely by integrating this source.

Policy format: object with `schema: 1`, optional absolute `literal_file`, optional
`exceptions` list. Each exception has exactly `target` (one of the four qualified Nortropic repositories),
`path` (repository-relative exact
path), `sha256` (complete file bytes), `reason` (nonempty). No globs, broad directory
exceptions or candidate policy input. A changed byte or repository target voids the exception. Reasons
are privately retained; receipts show their hashes. Curated receipts that resemble
raw streams need the same exact-byte host exception; file extension alone is not
an exception. Literal files are UTF-8, one nonempty literal per line, at most 1 MiB.
Configured but missing, empty, invalid or unreadable policy refuses. Without a
literal setting the receipt says `litterallista ej konfigurerad`.

The scanner is pattern-based, not an arbitrary private-data classifier. It does
not decode archives, encrypted content or arbitrary encodings, contact providers,
or test a credential. GitHub scanning and human review remain complementary.
All explicit exceptions require review of their exact content and reason.

I3: publication Git disables replacement objects, hooks and fsmonitor for each command and removes
inherited Git overrides. Effective fetch/push URLs must each be the one accepted
origin. A different explicit pushurl or any insteadOf/pushInsteadOf rule refuses
before push. Ordinary gh login is retained; this is no new login mechanism.

The active issuer still uses its previous separately adopted closure. New source
needs separate exact-byte adoption, including content_guard.py and an updated
launcher closure. Active Runtime code transition changes owner files and needs
Johnny's own block. This document grants neither action.

I2 cleanup cannot use a general deletion capability. The optional private policy
`deletions` list binds each deletion to target repository, exact base commit,
relative path, SHA-256 of the original regular file and nonempty archival reason.
A different target, base, path or byte refuses. Publisher and adopted issuer each
check that host policy; task/candidate fields never authorize deletion. No entry
has been installed by this preparation. The original blob must first be preserved
and checked in a private archive outside all repositories. Historical Git commits
remain; this is cleanup of main, not removal from public Git history.
