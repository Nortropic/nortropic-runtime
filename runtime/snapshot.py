"""Read candidate files without symlinks/races; verify the host-owned frozen copy."""
import hashlib
import os
from pathlib import Path
import stat


def read_regular(root, relative, limit=262144):
    parts = Path(relative).parts
    if not parts or any(p in ('..', '.') for p in parts) or Path(relative).is_absolute():
        raise ValueError('Expected a relative file path')
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('Expected a bounded regular source file')
        data = b''
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk: break
            data += chunk
        after = os.fstat(fd)
        if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Source changed while snapshotting')
        return data
    finally:
        for fd in reversed(descriptors): os.close(fd)


def snapshot(workspace, destination, paths):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    files = {}
    for name in paths:
        data = read_regular(workspace, name)
        target = destination / name
        target.parent.mkdir(exist_ok=True, parents=True)
        with target.open('xb') as stream: stream.write(data)
        files[name] = hashlib.sha256(data).hexdigest()
    (destination / '.scratch').mkdir()
    return files
