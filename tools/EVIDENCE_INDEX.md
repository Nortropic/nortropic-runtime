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
# Select every regular file under the root instead of listing paths:
python3 tools/evidence_index.py create /path/to/evidence --tree > manifest.json
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

## Indexing a whole tree

`create ROOT --tree` selects every regular file under the root, recursively, and
prints the same manifest structure as an explicit selection: `version` 1 and
`files` sorted lexicographically by path. Hidden (dot-prefixed) names and UTF-8
names are included like any other name. Empty directories contribute nothing, and
an empty tree gives `{"version":1,"files":[]}`. For a root containing `a`,
`logs/.state` and an empty directory `scratch/`, the output is:

```json
{"version":1,"files":[{"path":"a","sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","size":3},{"path":"logs/.state","sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","size":0}]}
```

Tree selection fails closed. A symlink (to a file or to a directory), FIFO, socket,
device or any other nonregular entry anywhere under the root is an error, exit 2,
whose message names the offending relative path, for example
`{"error":"not a regular file: logs/current"}`. Nothing is skipped silently. A tree
that contains such entries is indexed by listing explicit paths, as before:

```sh
python3 tools/evidence_index.py create /path/to/evidence a logs/.state
```

`--tree` is only valid once, directly after `ROOT`, and only for `create`. Giving it
together with explicit paths, more than once, or to `verify` is an invocation error
(exit 2). A file literally named `--tree` is therefore not selectable as an explicit
CLI path; the tree mode lists it like any other regular file, and the importable
functions accept it as a path.

The functions can also be imported from the repository root:

```python
from tools.evidence_index import create, select_tree, verify

manifest = create("/path/to/evidence", ["source.tar", "database.sqlite"])
whole_tree = create("/path/to/evidence", select_tree("/path/to/evidence"))
result = verify("/path/to/evidence", manifest)
```

`create(root, paths)` accepts an iterable of path strings. All functions accept a
string or string-valued path-like root. `create` raises `ValueError` for invalid
input or any unavailable, unsafe or changing selected file. `verify` raises
`ValueError` for a malformed manifest or invalid root; file failures become the
statuses above. Neither function alters the supplied manifest or file contents.

`select_tree(root)` returns the list of relative POSIX paths of every regular file
under the root, sorted exactly as `create` orders its result, so that
`create(root, select_tree(root))` is the manifest of the whole tree. It only lists
and never reads file contents; hashing and change detection stay in `create`. It
raises `ValueError` for an invalid root and for any nonregular entry under it, naming
the entry's relative path. The walk opens each directory relative to its parent's
descriptor without following symlinks, checks every name with a no-follow stat, and
closes every descriptor, also on errors. Names that `create` would refuse, such as a
name containing a backslash, are refused with the same fail-closed error.

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
