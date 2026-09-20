"""Host-owned allowlist. No task-selected filesystem path or remote URL."""
from .profile import ROOT

RUNTIME = 'Nortropic/nortropic-runtime'
OFFICE = 'Nortropic/nortropic-projektkontor'
TARGETS = (RUNTIME, OFFICE)


def repository(target):
    if target == RUNTIME:
        return ROOT
    if target == OFFICE:
        return ROOT.parent / 'nortropic-projektkontor'
    raise ValueError('Target is outside the authorized projects')


def origin(target):
    if target not in TARGETS:
        raise ValueError('Target is outside the authorized projects')
    return 'https://github.com/' + target + '.git'
