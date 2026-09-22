"""Create and verify local file integrity manifests without writing files."""

import hashlib
import json
import os
import re
import stat
import sys
from contextlib import contextmanager


class _Changed(ValueError):
    pass


class _Missing(ValueError):
    pass


class _Unsafe(ValueError):
    pass


def _path(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or "\0" in value or re.match(r"^[A-Za-z]:", value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("paths must be nonempty POSIX relative paths without dot components")
    return value


def _paths(values):
    if isinstance(values, (str, bytes, dict)):
        raise ValueError("paths must be an iterable of path strings")
    try:
        result = [_path(value) for value in values]
    except TypeError as exc:
        raise ValueError("paths must be an iterable of path strings") from exc
    if len(set(result)) != len(result):
        raise ValueError("duplicate paths are invalid")
    return sorted(result)


@contextmanager
def _root(root):
    fd = None
    try:
        name = os.fspath(root)
        if not isinstance(name, str) or not name or "\0" in name:
            raise ValueError("root must name an existing real directory")
        # A trailing slash or /. must not hide a symlink from O_NOFOLLOW.
        name = name.rstrip("/") or "/"
        while name.endswith("/."):
            name = name[:-2].rstrip("/") or "/"
        before = os.lstat(name)
        if not stat.S_ISDIR(before.st_mode):
            raise ValueError("root must be a real directory, not a symlink")
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("root changed while opening")
    except (OSError, TypeError, ValueError) as exc:
        if fd is not None:
            os.close(fd)
        raise ValueError(f"invalid root: {exc}") from exc
    try:
        yield fd
    finally:
        os.close(fd)


def _signature(info):
    # atime can change because of our own read; mtime and ctime must not.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _digest(root_fd, path):
    opened = []
    try:
        parent = root_fd
        parts = path.split("/")
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
            opened.append(parent)
        name = parts[-1]
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _Unsafe(f"not a regular file: {path}")
        # O_NONBLOCK also protects against replacement with a FIFO after stat.
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        opened.append(fd)
        start = os.fstat(fd)
        if not stat.S_ISREG(start.st_mode):
            raise _Unsafe(f"not a regular file: {path}")
        if _signature(before) != _signature(start):
            raise _Changed(f"file changed while opening: {path}")
        digest = hashlib.sha256()
        size = 0
        # Bound the read to the initial size plus one, even if a writer appends.
        while size <= start.st_size:
            block = os.read(fd, min(1024 * 1024, start.st_size - size + 1))
            if not block:
                break
            digest.update(block)
            size += len(block)
        end = os.fstat(fd)
        try:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise _Changed(f"file disappeared during read: {path}") from exc
        if (size != start.st_size or _signature(start) != _signature(end)
                or _signature(end) != _signature(current)):
            raise _Changed(f"file changed during read: {path}")
        return {"path": path, "sha256": digest.hexdigest(), "size": size}
    except FileNotFoundError as exc:
        raise _Missing(f"missing path: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise _Unsafe(f"cannot safely read {path}: {exc}") from exc
    finally:
        for fd in reversed(opened):
            os.close(fd)


def create(root, paths):
    """Return a sorted version-1 manifest; invalid or unsafe input raises ValueError."""
    selected = _paths(paths)
    with _root(root) as root_fd:
        return {"version": 1, "files": [_digest(root_fd, path) for path in selected]}


def _tree(dir_fd, prefix, found):
    # Lists one directory through its descriptor; every name is checked with
    # lstat and directories are re-opened with O_NOFOLLOW, so nothing follows a
    # symlink and nothing is resolved to an absolute path.
    path = prefix[:-1] or "."
    try:
        with os.scandir(dir_fd) as entries:
            for entry in entries:
                path = prefix + entry.name
                try:
                    _path(path)
                except ValueError as exc:
                    raise ValueError(f"unsupported name: {path}") from exc
                try:
                    before = os.lstat(entry.name, dir_fd=dir_fd)
                except FileNotFoundError as exc:
                    raise ValueError(f"entry disappeared while listing: {path}") from exc
                if stat.S_ISREG(before.st_mode):
                    found.append(path)
                elif stat.S_ISDIR(before.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=dir_fd)
                    try:
                        after = os.fstat(child)
                        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                            raise ValueError(f"directory changed while opening: {path}")
                        _tree(child, path + "/", found)
                    finally:
                        os.close(child)
                else:
                    raise ValueError(f"not a regular file: {path}")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot safely list {path}: {exc}") from exc


def select_tree(root):
    """Return the sorted relative paths of every regular file under root.

    Any symlink, FIFO, socket, device or other nonregular entry raises ValueError
    naming its relative path. Contents are not read.
    """
    found = []
    with _root(root) as root_fd:
        _tree(root_fd, "", found)
    return sorted(found)


def _manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"version", "files"}:
        raise ValueError("manifest must contain exactly version and files")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("manifest version must be integer 1")
    if not isinstance(manifest["files"], list):
        raise ValueError("manifest files must be a list")
    entries = []
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ValueError("each entry must contain exactly path, sha256 and size")
        path = _path(entry["path"])
        digest, size = entry["sha256"], entry["size"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        if type(size) is not int or size < 0:
            raise ValueError("size must be a nonnegative integer")
        entries.append({"path": path, "sha256": digest, "size": size})
    _paths(entry["path"] for entry in entries)
    return sorted(entries, key=lambda entry: entry["path"])


def verify(root, manifest):
    """Validate all input, then return every file's ok/changed/missing/unsafe status."""
    entries = _manifest(manifest)
    results = []
    with _root(root) as root_fd:
        for entry in entries:
            try:
                actual = _digest(root_fd, entry["path"])
                status = "ok" if actual == entry else "changed"
            except _Changed:
                status = "changed"
            except _Missing:
                status = "missing"
            except _Unsafe:
                status = "unsafe"
            results.append({"path": entry["path"], "status": status})
    return {"ok": all(item["status"] == "ok" for item in results), "files": results}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def main(argv=None):
    """CLI entry point; stdout is one JSON object, including on input errors."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) < 2 or args[0] not in ("create", "verify"):
            raise ValueError("usage: evidence_index.py create ROOT [PATH ...|--tree] | verify ROOT")
        if args[0] == "create":
            if "--tree" in args[2:]:
                if args[2:] != ["--tree"]:
                    raise ValueError("--tree must be given once, after ROOT, without explicit paths")
                result = create(args[1], select_tree(args[1]))
            else:
                result = create(args[1], args[2:])
            code = 0
        else:
            if len(args) != 2:
                raise ValueError("verify takes exactly one ROOT argument")
            manifest = json.loads(sys.stdin.buffer.read().decode("utf-8"),
                                  object_pairs_hook=_unique_object,
                                  parse_constant=_invalid_constant)
            result = verify(args[1], manifest)
            code = 0 if result["ok"] else 1
    except (ValueError, OSError, RecursionError) as exc:
        result = {"error": str(exc) or "invalid input"}
        code = 2
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    sys.exit(main())
