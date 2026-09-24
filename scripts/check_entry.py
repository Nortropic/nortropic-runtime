"""Start check for the Runtime entry (UNDERHALL-INGANGAR-20260924). It warns; it changes nothing.

    python3 -B scripts/check_entry.py              fetch origin and compare
    python3 -B scripts/check_entry.py --no-fetch   compare with the last fetched state

The primary checkout should stand on `main` equal to `origin/main`, with no commits of its own and no changed tracked
files, and no local branch should live only here unless the plan on `origin/main` names it. Each deviation is one line
starting with `WARNING:`; the last line is `ENTRY OK` or `ENTRY: n warnings`. When the entry deviates, read the plan
from `origin/main` (`git show origin/main:docs/plan.md`) and report the deviation. The exit code is always 0. The check
never switches a branch and writes no file, permission or setting; its only write is `git fetch`, which updates
remote-tracking references. It does not read or touch the native instruction inputs the active release binds.
"""
import argparse
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = 'refs/remotes/origin/main'


def git(repo, *args):
    run = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    return run.returncode, run.stdout.strip()


def check(repo=REPO, fetch=True):
    """The entry's warnings as text; an empty list when the entry follows main."""
    warnings = []
    if fetch and git(repo, 'fetch', '--quiet', 'origin')[0]:
        warnings.append('origin could not be fetched; the comparison uses the last fetched state')
    code, main = git(repo, 'rev-parse', '--verify', '--quiet', MAIN)
    if code:
        return warnings + ['origin/main is not present locally; the entry cannot be compared']
    branch = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')[1]
    if branch == 'HEAD':
        warnings.append('the entry is not on a branch but on a detached commit')
    elif branch != 'main':
        warnings.append('the entry is on %s, not on main' % branch)
    if git(repo, 'rev-parse', 'HEAD')[1] != main:
        ahead, behind = git(repo, 'rev-list', '--left-right', '--count', 'HEAD...' + MAIN)[1].split()
        warnings.append('the entry differs from origin/main (%s own commits, %s behind); read the plan with '
                        '`git show origin/main:docs/plan.md`' % (ahead, behind))
    changed = git(repo, 'status', '--porcelain', '--untracked-files=no')[1]
    if changed:
        warnings.append('%d tracked files have uncommitted changes' % len(changed.splitlines()))
    # A branch lives only here when its tip is reachable from no origin ref; the plan on origin/main may name it.
    local_only = set(git(repo, 'rev-list', '--branches', '--not', '--remotes=origin')[1].split())
    plan = git(repo, 'show', MAIN + ':docs/plan.md')[1]
    branches = [line.split() for line in git(repo, 'for-each-ref', 'refs/heads', '--format=%(refname:short) %(objectname)')[1].splitlines()]
    unnamed = sorted(name for name, tip in branches if tip in local_only and name not in plan)
    if unnamed:
        warnings.append('local branches with no copy on origin and no named reason in the plan: ' + ', '.join(unnamed))
    return warnings


def main(argv=None, repo=REPO):
    parser = argparse.ArgumentParser(description='Start check for the Runtime entry; warns, changes nothing.')
    parser.add_argument('--no-fetch', action='store_true', help='compare with the last fetched state')
    warnings = check(repo, fetch=not parser.parse_args(argv).no_fetch)
    for warning in warnings:
        print('WARNING: ' + warning)
    print('ENTRY OK' if not warnings else 'ENTRY: %d warnings' % len(warnings))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
