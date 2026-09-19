# Evidence index

`evidence_index.py` uses Python's standard library to hash and verify selected
regular files. Run on a POSIX platform supporting descriptor-relative opens,
`O_NOFOLLOW`, `O_DIRECTORY`, and `O_NONBLOCK` (including macOS and Linux).
No dependencies or network access are needed. Both operations only read files
and print JSON; shell redirection, if used, saves the output.

```sh
python3 tools/evidence_index.py create /path/to/evidence source.tar database.sqlite > manifest.json
python3 tools/evidence_index.py verify /path/to/evidence < manifest.json
# An empty selection is valid:
python3 tools/evidence_index.py create /path/to/evidence
```

Create output has exactly this structure, sorted lexicographically by path:

```json
{"version":1,"files":[{"path":"a","sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","size":3}]}
```

This example describes the raw bytes `abc`. Sizes are in bytes and digests are
lowercase SHA256. UTF-8 filenames and binary contents are supported. Selected paths
must be unique, nonempty POSIX relative paths: no empty, `.` or `..` components,
backslashes, NULs, absolute paths or Windows drive prefixes. Root must already
exist as a real directory, not a symlink. Symlinks at any component below root,
directories selected as files, FIFOs and other nonregular files are refused.

Verification accepts exactly one UTF-8 JSON manifest on stdin. Extra/missing keys,
duplicate JSON keys, duplicate paths, invalid digests, negative sizes, and boolean
or noninteger versions/sizes are rejected. The entire manifest is validated before
any selected file is read. Verification inspects all entries and returns sorted
results, for example:

```json
{"ok":false,"files":[{"path":"a","status":"changed"},{"path":"b","status":"missing"}]}
```

| Status | Meaning |
| --- | --- |
| `ok` | Both byte size and SHA256 match. |
| `changed` | Safely read bytes differ, or a change was detected during the read. |
| `missing` | A selected file or an intermediate component does not exist. |
| `unsafe` | Symlink, nonregular file, unreadable path, or another failure to read safely. |

Overall `ok` is true only if every entry is `ok`; an empty manifest succeeds.
Exit 0 means successful creation or matching verification. Exit 1 means a
verification mismatch (including missing/unsafe files). Exit 2 means invalid input,
invalid root, invocation error, or creation failure. Errors print an object such
as `{"error":"nonempty explanation"}` to stdout, without a traceback.

The functions can also be imported from the repository root:

```python
from tools.evidence_index import create, verify

manifest = create("/path/to/evidence", ["source.tar", "database.sqlite"])
result = verify("/path/to/evidence", manifest)
```

`create(root, paths)` accepts an iterable of path strings. Both functions accept a
string or string-valued path-like root. `create` raises `ValueError` for invalid
input or any unavailable, unsafe or changing selected file. `verify` raises
`ValueError` for a malformed manifest or invalid root; file failures become the
statuses above. Neither function alters the supplied manifest or file contents.

Files are opened relative to directory descriptors without following symlinks.
Nonblocking file opens prevent a substituted FIFO from hanging the process.
Identity, mode, size and nanosecond modification/change timestamps are checked
around each read, including a final directory-entry check. Read length is bounded
by the initial size plus one byte to detect growth without chasing an appending
writer. These checks detect ordinary concurrent modifications; they do not provide
an atomic snapshot across files or a guarantee against all hostile storage or
filesystem races. Reads may update access timestamps according to filesystem policy.

This is a local integrity tool, **not authentication or a signature system**.
Anyone able to replace both evidence and its manifest can produce matching values.
Preserve the trusted manifest separately; quiesce writers or use a filesystem
snapshot when a consistent set of evidence is needed.

Run the tests from the repository root with the supplied interpreter. Temporary
fixtures are explicitly kept under `.scratch`; `-B` suppresses bytecode writes:

```sh
/opt/homebrew/bin/python3.12 -B -m unittest discover -s tools -p 'test_evidence_index.py' -v
```
