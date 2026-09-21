"""Bind AP11 child effects to the separately activated host contract.

Ordinary development and AP10 private work keep their existing profile. A task
cannot opt itself into another scope or supply a host path. No activation here.
"""
from .development_scope import Scope, ScopeClosed
from .release import ROOT, require_active_code


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
