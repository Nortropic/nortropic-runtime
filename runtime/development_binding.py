"""Bind AP11 child effects to the separately activated host contract.

Ordinary development and AP10 private work keep their existing profile. A task
cannot opt itself into another scope or supply a host path. No activation here.
"""
from .development_scope import Scope, ScopeClosed
from .release import ROOT, require_active_code


def activity_seconds(task, kind):
    """Conservative full slot occupancy, including bounded host subprocesses.

    A Temporal timeout alone does not kill a synchronous activity thread. AP11
    permits two source files and480 model seconds. Candidate Git operations,
    sandbox recipe120s, publication's bounded Git/API calls and cleanup also
    fit in these envelopes. The native workflow uses the same time limit.
    """
    if 'development' not in task:
        return None
    if len(task.get('allowed_paths', [])) != 2 or not 1 <= task.get('attempt_seconds', 0) <= 480:
        raise ScopeClosed('Only the bounded two-file finite child profile is qualified')
    return {'implementation': 1500, 'review': 360, 'publication': 1500}[kind]


def for_task(task):
    selected = task.get('development')
    if selected is None:
        return None
    if (not isinstance(selected, dict) or set(selected) != {'contract_sha256', 'work'}
            or task.get('target') != 'Nortropic/nortropic-projektkontor'):
        raise ScopeClosed('Invalid development scope binding')
    config = require_active_code()
    active = config.get('development')
    if (not isinstance(active, dict) or active.get('id') != 'office-ap11'
            or active.get('contract_sha256') != selected['contract_sha256']):
        raise ScopeClosed('Development responsibility is not explicitly activated')
    return Scope(ROOT / '.runtime/ap11/application', selected['contract_sha256'])


def reserve_task_call(task, role, number):
    scope = for_task(task)
    if scope is None:
        return None
    from .integration import digest
    nonce = 'task-' + digest({'id': task['id'], 'role': role, 'number': number})
    scope.reserve(task['development']['work'], role, nonce, task['id'], digest(task))
    return scope, nonce


def publication_scope(task):
    scope = for_task(task)
    if scope is not None:
        from .integration import digest
        scope.permit_publication(task['development']['work'], task['id'], digest(task))
    return scope
