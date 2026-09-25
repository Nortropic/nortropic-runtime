"""Bind AP11 child effects to the separately activated host contract, and derive the frames of one review.

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


# The model's own bound inside the review activity. Measured 2026-09-22: a whole-task review with a structured answer
# was cut off by the host guardian at 182.2 s against this bound, leaving no verdict at all, while the activity envelope
# for a development review is 360 s. The larger bound stays well inside that envelope, so the host keeps time for its own
# work; a task without the finite-goal binding keeps exactly its former 180 s under its own 210 s envelope.
REVIEW_MODEL_SECONDS = 180
DEVELOPMENT_REVIEW_MODEL_SECONDS = 300

# An explicit review budget (office decision RUNTIME-GRANSKNINGSBUDGET-ACCEPT-20260925). Measured 2026-09-25: three
# office reviews were still reading the candidate when the fixed 180 s bound ended them, and complete reviews of the same
# candidates took 391-488 s. An accepted task may carry `review_seconds`, and a review-only continuation may give one;
# absent keeps exactly the former bound. Every frame of one review is derived here from that one value.
REVIEW_BUDGET_SECONDS = (180, 900)
HOST_MARGIN_SECONDS = 15        # the host waits this long beyond any model process's own bound (activities.invoke)
ACTIVITY_MARGIN_SECONDS = 30    # the Temporal activity beyond the model bound: 180 -> 210, as before
WATCH_RUN_SECONDS = 1200        # AP-10's scheduled run is bounded by this execution timeout (obligation.definition)
CAPACITY_POLL_SECONDS = 30      # the native timer between two admission checks (workflow.execute_activity)
OBSERVATION_MARGIN_SECONDS = 60


def review_budget(value):
    if type(value) is not int or not REVIEW_BUDGET_SECONDS[0] <= value <= REVIEW_BUDGET_SECONDS[1]:
        raise ValueError('A review budget is a whole number of seconds within %d..%d' % REVIEW_BUDGET_SECONDS)
    return value


def review_frames(seconds):
    """The model process, the host's wait on it and the Temporal activity of one review, from one value."""
    return {'model': seconds, 'host': seconds + HOST_MARGIN_SECONDS, 'activity': seconds + ACTIVITY_MARGIN_SECONDS}


def review_observation(seconds):
    """How long an operator observes one budgeted review: a possible admission wait, then the review itself.

    Admission refuses while the whole activity plus 60 s would reach the next watch run, and while that run lasts (at
    most its execution timeout); the workflow checks again on a native timer, so up to two timer periods are added.
    """
    activity = review_frames(seconds)['activity']
    admission = activity + 60 + WATCH_RUN_SECONDS + 2 * CAPACITY_POLL_SECONDS
    return admission + activity + OBSERVATION_MARGIN_SECONDS


def model_seconds(task, kind, budget=None):
    if kind != 'review':
        raise ValueError('Only the review model bound is derived here')
    if task.get('development') and (budget is not None or task.get('review_seconds') is not None):
        raise ScopeClosed('The finite development profile keeps its own review bound')
    if budget is not None:
        return review_budget(budget)
    if task.get('review_seconds') is not None:
        return review_budget(task['review_seconds'])
    bound = DEVELOPMENT_REVIEW_MODEL_SECONDS if task.get('development') else REVIEW_MODEL_SECONDS
    return min(bound, task['attempt_seconds'])


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
