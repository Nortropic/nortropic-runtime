"""Runtime's own pinned copy of the browser tools the web profiles run (D034), in the D023 pattern.

The measurement and visitor profiles drive a local Chrome with puppeteer-core, run axe-core and Lighthouse, and are
therefore only as fixed as the packages they load. Loading them from wherever they happen to be installed would let
another project's install change what the engine measures, so the host keeps exactly the already installed versions
under `.runtime/web-tools/node_modules/`, bound file by file to `config/web-tools.lock.json`. Nothing is downloaded:
the copy is made from an existing npm install whose lock file names the same versions, and it is refused unless every
package tree matches the lock.

usage:
  <python> -B scripts/install_web_tools.py --source <existing node_modules>          copy + verify (no-op if present)
  <python> -B scripts/install_web_tools.py --check                                     verify the host copy only
  <python> -B scripts/install_web_tools.py --source <node_modules> --write-lock        builder only: record the lock
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

ROOTS = ('puppeteer-core', 'axe-core', 'lighthouse', 'chrome-launcher')
CODE_ROOT = Path(__file__).resolve().parents[1]
LOCK = CODE_ROOT / 'config/web-tools.lock.json'


def host_root():
    return Path(os.environ.get('NR_HOST_ROOT', CODE_ROOT)).resolve()


def closure(lock_packages):
    """The package keys npm itself would load for ROOTS, resolved the way Node resolves them."""
    def resolve(owner, name):
        base = owner
        while True:
            candidate = (base + '/node_modules/' + name) if base else ('node_modules/' + name)
            if candidate in lock_packages:
                return candidate
            if not base:
                return None
            # Walk up one node_modules level: 'node_modules/a/node_modules/b' -> 'node_modules/a'.
            cut = base.rfind('/node_modules/')
            base = base[:cut] if cut >= 0 else ''
    seen, stack = set(), [resolve('', name) for name in ROOTS]
    if None in stack:
        raise SystemExit('REFUSED: a root package is missing from the source lock')
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        info = lock_packages[key]
        wanted = dict(info.get('dependencies') or {})
        wanted.update(info.get('optionalDependencies') or {})
        for name, spec in (info.get('peerDependencies') or {}).items():
            if not (info.get('peerDependenciesMeta') or {}).get(name, {}).get('optional'):
                wanted[name] = spec
        for name in sorted(wanted):
            found = resolve(key, name)
            if found is None:
                if name in (info.get('optionalDependencies') or {}):
                    continue
                raise SystemExit('REFUSED: %s needs %s, which the source lock does not hold' % (key, name))
            stack.append(found)
    return sorted(seen)


def package_files(directory):
    """Regular files of one package, its own nested node_modules excluded (those are separate keys)."""
    files = {}
    for current, dirs, names in os.walk(directory):
        # A nested node_modules at any depth holds other packages, which are keys of their own.
        dirs[:] = sorted(d for d in dirs if d != 'node_modules')
        for name in dirs:
            if os.path.islink(Path(current) / name):
                raise SystemExit('REFUSED: symbolic link inside a package: ' + str(Path(current) / name))
        for name in sorted(names):
            path = Path(current) / name
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                raise SystemExit('REFUSED: symbolic link inside a package: ' + str(path))
            if not stat.S_ISREG(mode):
                raise SystemExit('REFUSED: not a regular file inside a package: ' + str(path))
            files[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def tree_sha(files):
    text = ''.join('%s\0%s\n' % (rel, digest) for rel, digest in sorted(files.items()))
    return hashlib.sha256(text.encode()).hexdigest()


def measure(node_modules_parent, keys):
    result = {}
    for key in keys:
        directory = node_modules_parent / key
        if directory.is_symlink() or not directory.is_dir():
            raise SystemExit('REFUSED: package directory missing or a link: ' + key)
        files = package_files(directory)
        result[key] = {'files': len(files), 'tree_sha256': tree_sha(files)}
    return result


def overall(packages):
    return hashlib.sha256(json.dumps({k: v['tree_sha256'] for k, v in sorted(packages.items())},
                                     sort_keys=True).encode()).hexdigest()


def load_lock():
    lock = json.loads(LOCK.read_text())
    if lock.get('format') != 1 or overall(lock['packages']) != lock.get('tree_sha256'):
        raise SystemExit('REFUSED: config/web-tools.lock.json is not a consistent format-1 lock')
    return lock


def check(destination, lock):
    measured = measure(destination.parent, sorted(lock['packages']))
    wrong = sorted(k for k, v in lock['packages'].items()
                   if measured[k]['tree_sha256'] != v['tree_sha256'] or measured[k]['files'] != v['files'])
    if wrong:
        raise SystemExit('REFUSED: packages differ from the lock: ' + ', '.join(wrong[:10]))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--write-lock', action='store_true')
    args = parser.parse_args()
    destination = host_root() / '.runtime/web-tools/node_modules'
    if args.check:
        check(destination, load_lock())
        print(json.dumps({'checked': str(destination), 'tree_sha256': load_lock()['tree_sha256']}))
        return
    if not args.source:
        raise SystemExit('REFUSED: --source <existing node_modules> is required')
    source = Path(args.source).resolve()
    source_lock = json.loads((source.parent / 'package-lock.json').read_text())
    keys = closure(source_lock['packages'])
    if args.write_lock:
        packages = measure(source.parent, keys)
        for key in keys:
            info = source_lock['packages'][key]
            packages[key].update(version=info.get('version'), integrity=info.get('integrity'))
        lock = {'format': 1, 'roots': list(ROOTS),
                'note': 'Copied byte for byte from an existing npm install; nothing is downloaded. Each package '
                        'tree hash covers its regular files, its own nested node_modules excluded.',
                'packages': packages, 'tree_sha256': overall(packages)}
        LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + '\n')
        print(json.dumps({'written': str(LOCK), 'packages': len(keys), 'tree_sha256': lock['tree_sha256']}))
        return
    lock = load_lock()
    if sorted(lock['packages']) != keys:
        raise SystemExit('REFUSED: the source resolves another package set than the lock')
    check(source, lock)
    if destination.exists():
        check(destination, lock)
        print(json.dumps({'present': str(destination), 'tree_sha256': lock['tree_sha256']}))
        return
    staging = destination.parent / ('.staging-%d' % os.getpid())
    staging.mkdir(parents=True)
    for key in keys:
        for rel in package_files(source.parent / key):
            target = staging / key / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.parent / key / rel, target)
    check(staging / 'node_modules', lock)
    os.rename(staging / 'node_modules', destination)
    staging.rmdir()
    check(destination, lock)
    print(json.dumps({'installed': str(destination), 'packages': len(keys), 'tree_sha256': lock['tree_sha256']}))


if __name__ == '__main__':
    main()
