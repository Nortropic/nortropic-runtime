"""A second whole-goal assessment of the SAME accepted application, under its own run identity.

The engine refuses a second run of a workflow id that already exists, whatever its outcome, and that refusal is
the protection against a rejected application being quietly re-run until it passes. It is kept. What this module
adds is narrower: a separately reviewed owner decision may bind ONE further assessment, which runs under its own
identity against the same scope, the same frozen commitment and the same ceilings.

What it deliberately does not do: reopen, reset or re-run the application it follows, refund or raise the 48/6
ceilings, remove the duplicate-start protection for any identity including its own, or alter the recorded result
of the review it follows. An assessment may only follow a review that was actually NOT approved - overturning an
approval is not a re-assessment - and the application it follows must really be closed before it starts, which
is what keeps a second writer off the same scope.
"""
from pathlib import Path

from . import development_host as host
from .development_scope import decode, identifier
from .snapshot import read_regular

APPLICATION='office-ap11'
# Further whole-goal assessments exist ONLY as separately reviewed owner decisions bound in the active
# configuration (development.assessments, an ordered list), exactly as further interactive starts do. Each entry
# names the run it follows and how that run really ended. This is not a general re-run right.
ASSESSMENTS=('office-ap11-assessment-2',)
ASSESSMENT_KEYS={'id','after','previous_outcome','decision','decision_sha256','review','review_sha256'}
OUTCOMES=('whole_goal_not_approved',)


def assessments(config):
    """The bound further assessments of the active configuration, in order, each verified against its own
    decision and separate review, or an empty tuple."""
    bound=(config.get('development') or {}).get('assessments')
    if bound is None:return ()
    if not isinstance(bound,list) or not bound or len(bound)>len(ASSESSMENTS):
        raise ValueError('Exact reviewed assessment list required')
    directory=Path(config['directory'])/'development-context';previous=APPLICATION
    for index,entry in enumerate(bound):
        if (not isinstance(entry,dict) or set(entry)!=ASSESSMENT_KEYS or entry['id']!=ASSESSMENTS[index]
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
    if host.policy(config).review(result['answer']):
        raise ValueError('The previous whole-goal review was approved; there is nothing to re-assess')
    return nonce,result
