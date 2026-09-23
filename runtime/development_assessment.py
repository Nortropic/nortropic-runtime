"""Further whole-goal assessments of the SAME accepted application, each under its own run identity.

The engine refuses a second run of a workflow id that already exists, whatever its outcome, and that refusal is
the protection against a rejected application being quietly re-run until it passes. It is kept. What this module
adds is narrower: a separately reviewed decision may bind a further assessment, which runs under its own identity
against the same scope, the same frozen commitment and the same ceilings.

The identities are not chosen by a decision. The n-th bound entry IS office-ap11-assessment-(n+1), follows the
entry before it, and exists only as a separately reviewed decision in the active configuration. A new entry needs
no code change, and a decision still cannot mint a name of its own.

What it deliberately does not do: reopen, reset or re-run the application it follows, refund or raise the 48/6
ceilings, remove the duplicate-start protection for any identity including its own, or alter the recorded result
of the review it follows. An assessment may only follow a review that was actually NOT approved - overturning an
approval is not a re-assessment -, the run it follows must really be closed before it starts, which is what keeps
a second writer off the same scope, and the evidence must have changed since the review it follows: the same
package offered again until some reviewer approves it is exactly what is refused.
"""
from pathlib import Path

from . import development_host as host
from .development_scope import decode, identifier
from .snapshot import read_regular

APPLICATION='office-ap11'
# Further whole-goal assessments exist ONLY as separately reviewed decisions bound in the active configuration
# (development.assessments, an ordered list), exactly as further interactive starts do. Each entry names the run it
# follows and how that run really ended. This is not a general re-run right.
ASSESSMENT_KEYS={'id','after','previous_outcome','decision','decision_sha256','review','review_sha256'}
OUTCOMES=('whole_goal_not_approved',)


def assessment_id(index):
    """The only identity the entry at this position of the ordered list may have: the first further assessment is
    the second assessment of the commitment, so position 0 is office-ap11-assessment-2."""
    return '%s-assessment-%d' % (APPLICATION, index + 2)


def assessments(config):
    """The bound further assessments of the active configuration, in order, each verified against its own
    decision and separate review, or an empty tuple."""
    bound=(config.get('development') or {}).get('assessments')
    if bound is None:return ()
    if not isinstance(bound,list) or not bound:
        raise ValueError('Exact reviewed assessment list required')
    directory=Path(config['directory'])/'development-context';previous=APPLICATION
    for index,entry in enumerate(bound):
        if (not isinstance(entry,dict) or set(entry)!=ASSESSMENT_KEYS or entry['id']!=assessment_id(index)
                or entry['after']!=previous or entry['previous_outcome'] not in OUTCOMES
                or not all(isinstance(entry[key],str) and entry[key] for key in ASSESSMENT_KEYS)):
            raise ValueError('Exact reviewed assessment binding required')
        for name,expected in ((entry['decision'],entry['decision_sha256']),(entry['review'],entry['review_sha256'])):
            if Path(name).name!=name or host.sha(read_regular(directory,name))!=expected:
                raise ValueError('Assessment decision or review changed')
        review=decode(read_regular(directory,entry['review']))
        if (not isinstance(review,dict) or review.get('verdict')!='approved'
                or review.get('blocking_findings')!=[] or review.get('assesses')!=entry['id']
                or review.get('after')!=previous
                or review.get('previous_outcome')!=entry['previous_outcome']
                or review.get('decision_sha256')!=entry['decision_sha256']):
            raise ValueError('Assessment is not separately approved')
        previous=entry['id']
    return tuple(bound)


def identities(config):
    """Every run identity this one commitment has had, oldest first. The evidence of the examined work lives
    under the earlier ones, so they are read, never replaced."""
    return (APPLICATION,*(entry['id'] for entry in assessments(config)))


def identity(config):
    """The identity a new start would use: the last bound assessment, or the original application."""
    return identities(config)[-1]


def preserved_refusal(scope,config):
    """The recorded ending a further assessment may follow, read from the preserved scope rather than assumed.

    Deliberately NOT keyed on the current control value: the operator must resume the scope before starting
    anything, so requiring 'paused' here would only be satisfiable before the resume and would say nothing
    about what the previous review actually decided.
    """
    if (scope.directory/'final.json').is_file():
        raise ValueError('The application was already closed as approved; there is nothing to re-assess')
    reviews=[call for call in scope.inspect()['calls'] if call.get('role')=='final-review']
    if not reviews:
        raise ValueError('A further assessment follows only an actual whole-goal review')
    nonce=reviews[-1]['nonce']
    stage=scope.directory/'calls'/identifier(nonce)
    if not (stage/'result.json').is_file():
        raise ValueError('The whole-goal review it follows has no preserved result')
    result=decode(read_regular(stage,'result.json'))
    # An approval that closed nothing may be followed: the review continued an interrupted review of its own run, so
    # it is part of the event a G6 examination has to judge, and close() withheld the closure for a separate one.
    if host.policy(config).review(result['answer']) and not continues_an_interruption(scope,nonce):
        raise ValueError('The previous whole-goal review was approved; there is nothing to re-assess')
    return nonce,result


def continues_an_interruption(scope,nonce):
    """True when another whole-goal review of the SAME run was started and never completed.

    Such a review is the continued half of an interruption in its own run. It is a fresh session with no part in the
    interrupted call, but it is part of the event: it cannot be the independent examination of that event, so an
    approval it gives must not close the commitment by itself (close() withholds it) and a separate assessment may
    follow it. Read from the preserved stages, never assumed.
    """
    prefix='step-' if nonce.startswith('step-') else nonce.rsplit('-step-',1)[0]+'-step-'
    for call in scope.inspect()['calls']:
        other=call.get('nonce')
        if call.get('role')!='final-review' or other==nonce or not str(other).startswith(prefix):
            continue
        if other.startswith('step-')!=nonce.startswith('step-'):
            continue
        stage=scope.directory/'calls'/identifier(other)
        if not (stage/'result.json').is_file() or decode(read_regular(stage,'result.json')).get('completed') is not True:
            return True
    return False


# Where the host records that an assessment identity was started. The engine's duplicate refusal forgets a closed
# execution one day after it closed, and after that the same id would start again as if it had never run. The
# scope is the one record that outlives retention, so the refusal that must outlive it is kept there.
STARTS='assessment-starts'


def unused_identity(scope,identity):
    """Refuse an assessment identity this scope has already seen run, whatever the engine still remembers.

    Seen means either the host's own start record, or any counted reservation in this identity's key namespace:
    the second covers a run started before start records existed, as office-ap11-assessment-2 was.
    """
    from .development_workflow import key_prefix
    if identity==APPLICATION:
        raise ValueError('The original application is never started as an assessment')
    prefix=key_prefix(identifier(identity))
    if ((scope.directory/STARTS/(identity+'.json')).exists()
            or any(call['nonce'].startswith(prefix) for call in scope.inspect()['calls'])):
        raise ValueError('This assessment identity has already run in this scope and is never started again: '+identity)


def record_start(scope,identity,observed):
    """Written by the host only AFTER the engine accepted the start, append only, never rewritten."""
    from .private_stage import write
    directory=scope.directory/STARTS
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError('Assessment start record directory is not a directory')
    directory.mkdir(mode=0o700,exist_ok=True)
    write(directory/(identifier(identity)+'.json'),{'identity':identity,'observed_at':observed,
        'source':'host operator action assess, recorded after the engine accepted the start'})


def changed_evidence(scope,nonce):
    """The selected whole-goal evidence must differ from what the review it follows was actually given.

    Compared on the bytes of the qualification index delivered into that review's own workspace, which binds every
    selected record by hash, against the index the next preparation would read. An identical index is the same
    package offered again, and a further assessment exists for completed evidence, not for another draw.
    """
    delivered=scope.directory/'calls'/identifier(nonce)/'workspace'/'qualification'
    current=scope.directory/'qualification'
    if not (current/'index.json').is_file():
        raise ValueError('No selected whole-goal evidence to assess')
    if (delivered/'index.json').is_file() and read_regular(delivered,'index.json')==read_regular(current,'index.json'):
        raise ValueError('The selected evidence is the package the previous review already had; complete it first')
    return host.sha(read_regular(current,'index.json'))
