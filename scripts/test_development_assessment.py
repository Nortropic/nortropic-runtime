"""A second whole-goal assessment must be an owner decision, not a re-run right.

The engine's duplicate-start refusal is what stops a rejected application being quietly re-run until it passes.
These drive the real binding and the real preconditions, with no engine and no model, and check that every way
of arriving at a second run WITHOUT a separately reviewed decision is refused.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime import development_assessment as assessment


ID = 'office-ap11-assessment-2'


def sha(content):
    return hashlib.sha256(content).hexdigest()


class BindingTests(unittest.TestCase):
    def build(self, directory, decision=b'Owner decision: assess the same commitment once more.\n',
              review=None, entry=None):
        context = Path(directory) / 'development-context'
        context.mkdir(parents=True, exist_ok=True)
        if review is None:
            review = {'verdict': 'approved', 'blocking_findings': [], 'assesses': ID,
                      'after': assessment.APPLICATION, 'previous_outcome': 'whole_goal_not_approved',
                      'decision_sha256': sha(decision)}
        body = json.dumps(review).encode()
        (context / 'assessment-2.md').write_bytes(decision)
        (context / 'assessment-2-review.json').write_bytes(body)
        if entry is None:
            entry = {'id': ID, 'after': assessment.APPLICATION,
                     'previous_outcome': 'whole_goal_not_approved',
                     'decision': 'assessment-2.md', 'decision_sha256': sha(decision),
                     'review': 'assessment-2-review.json', 'review_sha256': sha(body)}
        return {'directory': directory, 'development': {'assessments': [entry]}}

    def test_without_a_bound_decision_the_identity_is_the_original_application(self):
        """The default is that there is no second run. Nothing about a rejected verdict changes it."""
        for development in ({}, {'assessments': None}):
            with self.subTest(development=development):
                config = {'directory': '/nowhere', 'development': development}
                self.assertEqual(assessment.identity(config), 'office-ap11')
                self.assertEqual(assessment.identities(config), ('office-ap11',))
                self.assertEqual(assessment.assessments(config), ())

    def test_a_reviewed_decision_binds_exactly_one_further_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.build(directory)
            self.assertEqual(assessment.identity(config), ID)
            self.assertEqual(assessment.identities(config), ('office-ap11', ID))

    def test_the_earlier_identity_is_kept_so_its_evidence_stays_readable(self):
        """The run being examined must not be replaced by the run examining it."""
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(assessment.identities(self.build(directory))[0], 'office-ap11')

    def test_a_changed_decision_or_review_is_refused(self):
        for target in ('assessment-2.md', 'assessment-2-review.json'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                config = self.build(directory)
                path = Path(directory) / 'development-context' / target
                path.write_bytes(path.read_bytes() + b' ')
                with self.assertRaises(ValueError) as caught:
                    assessment.assessments(config)
                self.assertIn('changed', str(caught.exception))

    def test_a_review_that_did_not_approve_is_refused(self):
        for review in ({'verdict': 'rejected', 'blocking_findings': []},
                       {'verdict': 'approved', 'blocking_findings': ['unresolved']},
                       {'verdict': 'inconclusive', 'blocking_findings': []}):
            with self.subTest(review=review['verdict']), tempfile.TemporaryDirectory() as directory:
                decision = b'Owner decision: assess the same commitment once more.\n'
                full = {'assesses': ID, 'after': assessment.APPLICATION,
                        'previous_outcome': 'whole_goal_not_approved',
                        'decision_sha256': sha(decision), **review}
                with self.assertRaises(ValueError):
                    assessment.assessments(self.build(directory, decision=decision, review=full))

    def test_a_review_of_a_different_decision_or_a_different_assessment_is_refused(self):
        """Otherwise one approval could be moved onto another decision."""
        decision = b'Owner decision: assess the same commitment once more.\n'
        base = {'verdict': 'approved', 'blocking_findings': [], 'assesses': ID,
                'after': assessment.APPLICATION, 'previous_outcome': 'whole_goal_not_approved',
                'decision_sha256': sha(decision)}
        for key, value in (('assesses', 'office-ap11'), ('after', 'something-else'),
                           ('decision_sha256', sha(b'other')),
                           ('previous_outcome', 'whole_goal_approved')):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    assessment.assessments(self.build(directory, decision=decision,
                                                      review={**base, key: value}))

    def test_an_identity_outside_the_known_set_is_refused_even_when_its_review_agrees(self):
        """Isolates the whitelist. Everything else about this binding is internally consistent - the review
        approves exactly this identity and this decision - so the only thing that can refuse it is that the
        identity is not one the code knows. Without that, a decision could mint run identities at will."""
        decision = b'Owner decision: assess the same commitment once more.\n'
        chosen = 'office-ap11-assessment-9'
        review = {'verdict': 'approved', 'blocking_findings': [], 'assesses': chosen,
                  'after': assessment.APPLICATION, 'previous_outcome': 'whole_goal_not_approved',
                  'decision_sha256': sha(decision)}
        body = json.dumps(review).encode()
        with tempfile.TemporaryDirectory() as directory:
            entry = {'id': chosen, 'after': assessment.APPLICATION,
                     'previous_outcome': 'whole_goal_not_approved',
                     'decision': 'assessment-2.md', 'decision_sha256': sha(decision),
                     'review': 'assessment-2-review.json', 'review_sha256': sha(body)}
            config = self.build(directory, decision=decision, review=review, entry=entry)
            with self.assertRaises(ValueError) as caught:
                assessment.assessments(config)
            self.assertIn('Exact reviewed assessment binding required', str(caught.exception))

    def test_a_decision_reached_through_a_subdirectory_is_refused_on_its_name(self):
        """Isolates the basename check. The file really exists and its hash really matches, so nothing else
        in the binding objects; only the refusal to follow a path does."""
        decision = b'Owner decision: assess the same commitment once more.\n'
        with tempfile.TemporaryDirectory() as directory:
            config = self.build(directory, decision=decision)
            nested = Path(directory) / 'development-context' / 'sub'
            nested.mkdir()
            (nested / 'assessment-2.md').write_bytes(decision)
            config['development']['assessments'][0]['decision'] = 'sub/assessment-2.md'
            with self.assertRaises(ValueError) as caught:
                assessment.assessments(config)
            self.assertIn('changed', str(caught.exception))

    def test_an_entry_that_is_not_the_exact_expected_shape_is_refused(self):
        decision = b'Owner decision: assess the same commitment once more.\n'
        review = json.dumps({'verdict': 'approved', 'blocking_findings': [], 'assesses': ID,
                             'after': assessment.APPLICATION,
                             'previous_outcome': 'whole_goal_not_approved',
                             'decision_sha256': sha(decision)}).encode()
        good = {'id': ID, 'after': assessment.APPLICATION, 'previous_outcome': 'whole_goal_not_approved',
                'decision': 'assessment-2.md', 'decision_sha256': sha(decision),
                'review': 'assessment-2-review.json', 'review_sha256': sha(review)}
        variants = {
            'an identity of its own choosing': {**good, 'id': 'office-ap11-assessment-9'},
            'following a run it did not follow': {**good, 'after': 'office-ap11-assessment-2'},
            'an outcome that is not a refusal': {**good, 'previous_outcome': 'whole_goal_approved'},
            'a decision reached by path': {**good, 'decision': '../goal.md'},
            'a missing field': {k: v for k, v in good.items() if k != 'review_sha256'},
            'an extra field': {**good, 'budget': 96},
            'an empty value': {**good, 'decision': ''},
        }
        for label, entry in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    assessment.assessments(self.build(directory, decision=decision, entry=entry))

    def test_the_list_itself_cannot_grant_an_open_ended_series(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.build(directory)
            entry = config['development']['assessments'][0]
            for bound in ([], [entry, entry], {}, 'assessment-2', [entry, dict(entry, id='x')]):
                with self.subTest(bound=str(bound)[:40]):
                    with self.assertRaises(ValueError):
                        assessment.assessments({**config, 'development': {'assessments': bound}})


class PreconditionTests(unittest.TestCase):
    """What a further assessment may follow, read from the preserved scope."""

    def scope(self, directory, calls=(('step-36', 'final-review'),), result=None, final=False):
        root = Path(directory)
        (root / 'calls').mkdir(parents=True, exist_ok=True)
        for nonce, role in calls:
            stage = root / 'calls' / nonce
            stage.mkdir(parents=True, exist_ok=True)
            if result is not None:
                stage.joinpath('result.json').write_text(json.dumps(result))
        if final:
            root.joinpath('final.json').write_text(json.dumps({'approved': True}))
        return SimpleNamespace(directory=root,
                               inspect=lambda: {'calls': [{'nonce': n, 'role': r} for n, r in calls]})

    def run_check(self, scope, approved=False):
        policy = SimpleNamespace(review=lambda answer: approved)
        with patch.object(assessment.host, 'policy', return_value=policy):
            return assessment.preserved_refusal(scope, {'directory': '/nowhere'})

    def test_an_actual_recorded_refusal_is_what_it_follows(self):
        with tempfile.TemporaryDirectory() as directory:
            answer = {'verdict': 'inconclusive', 'blocking_findings': ['unreadable evidence']}
            scope = self.scope(directory, result={'answer': answer})
            nonce, result = self.run_check(scope)
            self.assertEqual(nonce, 'step-36')
            self.assertEqual(result['answer'], answer)

    def test_an_approved_review_cannot_be_re_assessed(self):
        """A second look at an approval would be an attempt to overturn it, which is a different thing."""
        with tempfile.TemporaryDirectory() as directory:
            scope = self.scope(directory, result={'answer': {'verdict': 'approved'}})
            with self.assertRaises(ValueError) as caught:
                self.run_check(scope, approved=True)
            self.assertIn('nothing to re-assess', str(caught.exception))

    def test_a_closed_approved_application_cannot_be_re_assessed(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = self.scope(directory, result={'answer': {'verdict': 'inconclusive'}}, final=True)
            with self.assertRaises(ValueError) as caught:
                self.run_check(scope)
            self.assertIn('already closed as approved', str(caught.exception))

    def test_an_application_with_no_whole_goal_review_cannot_be_re_assessed(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = self.scope(directory, calls=(('step-5', 'implementation'),), result={'answer': {}})
            with self.assertRaises(ValueError) as caught:
                self.run_check(scope)
            self.assertIn('actual whole-goal review', str(caught.exception))

    def test_a_review_whose_result_was_not_preserved_cannot_be_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = self.scope(directory, result=None)
            with self.assertRaises(ValueError) as caught:
                self.run_check(scope)
            self.assertIn('no preserved result', str(caught.exception))

    def test_the_latest_review_is_the_one_it_follows(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = self.scope(directory, calls=(('step-36', 'final-review'), ('step-40', 'final-review')),
                               result={'answer': {'verdict': 'inconclusive'}})
            self.assertEqual(self.run_check(scope)[0], 'step-40')


class ControlWiringTests(unittest.TestCase):
    """The identity comes from the configuration, and the duplicate-start protection is never lifted."""

    def test_the_start_still_refuses_a_duplicate_for_whatever_identity_it_uses(self):
        import ast
        import inspect as inspect_module
        from runtime import development_control
        source = inspect_module.getsource(development_control.operate)
        starts = [n for n in ast.walk(ast.parse(source.lstrip()))
                  if isinstance(n, ast.Call) and getattr(n.func, 'attr', None) == 'start_workflow']
        self.assertEqual(len(starts), 2, 'the build start and the direct assessment, and nothing else')
        by_workflow = {}
        for node in starts:
            keywords = {k.arg: ast.unparse(k.value) for k in node.keywords}
            self.assertEqual(keywords['id_reuse_policy'], 'WorkflowIDReusePolicy.REJECT_DUPLICATE',
                             'the duplicate-start refusal is lifted for neither')
            by_workflow[ast.unparse(node.args[0])] = keywords['id']
        self.assertEqual(by_workflow.get('FiniteDevelopment.run'), 'NAME',
                         'the BUILD sequence is pinned to the original application identity, so binding an '
                         'assessment can never give A/B preparation a second identity to run under')
        self.assertEqual(by_workflow.get('FiniteAssessment.run'), 'current',
                         'only the direct assessment uses the resolved, separately reviewed identity')

    def test_the_identity_is_resolved_from_the_configuration_not_chosen_in_control(self):
        import ast
        import inspect as inspect_module
        from runtime import development_control
        tree = ast.parse(inspect_module.getsource(development_control.operate).lstrip())
        assigned = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], 'id', None) == 'current']
        self.assertEqual(len(assigned), 1)
        self.assertEqual(ast.unparse(assigned[0].value), 'assessment.identity(config)')

    def test_control_keeps_the_original_application_as_its_name(self):
        from runtime import development_control
        self.assertEqual(development_control.NAME, 'office-ap11')
        self.assertEqual(development_control.NAME, assessment.APPLICATION)


if __name__ == '__main__':
    unittest.main()
