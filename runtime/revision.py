"""Pure validation of a host-authorized access continuation, not a new task."""
from .integration import digest


def require_revision(original, revised, step_index, attempt):
    info=revised.get('continuation',{})
    if (info.get('previous_task_sha256')!=digest(original) or info.get('expected_attempt')!=attempt
            or not isinstance(info.get('reason'),str) or not info['reason'].strip()
            or not isinstance(info.get('evidence'),str) or not info['evidence'].strip()):
        raise ValueError('Continuation must bind the previous task, attempt and changed prerequisite')
    # Updating base and completing the pilot's host verifier is explicit, reviewed
    # operator work. Outcome, file scope, step prompts/order and limits stay fixed.
    mutable={'base','acceptance','acceptance_sha256','brief','continuation','steps'}
    if {k:v for k,v in original.items() if k not in mutable}!={k:v for k,v in revised.items() if k not in mutable}:
        raise ValueError('Continuation may not change accepted task scope or limits')
    old,new=original['steps'],revised['steps']
    if len(old)!=len(new) or not 0<=step_index<len(old):raise ValueError('Invalid continuation step')
    for i,(a,b) in enumerate(zip(old,new)):
        expected=dict(a)
        if i==step_index:expected.pop('waiting_reason',None)
        if b!=expected:raise ValueError('Continuation must preserve provider steps and prompts')
    if old[step_index]['provider']!='claude' or new[step_index].get('waiting_reason'):
        raise ValueError('Only the qualified Claude access transition is enabled')
    return True
