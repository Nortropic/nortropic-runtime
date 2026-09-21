"""A separately reviewed amendment of the frozen goal reaches every role that receives the goal.

Bound by the release configuration, never by the contract (the scope and its consumed calls are
keyed to the contract hash). Synthetic texts; explicitly NOT application evidence.
"""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import development_host as host


def digest(content):
    return hashlib.sha256(content).hexdigest()


class GoalAmendmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.release = Path(self.temp.name).resolve()/'release'
        self.context = self.release/'development-context'; self.context.mkdir(parents=True)
        self.goal = b'G4: No other engine, DB or model.\n'; self.amendment = b'R1 replaces exactly those words.\n'
        (self.context/'goal.md').write_bytes(self.goal); (self.context/'amendment-a.md').write_bytes(self.amendment)
        self.contract = {'acceptance_sha256': digest(self.goal), 'authority_sha256': 'a'*64}
        self.record = {'reviewer': 'separate context, same model family', 'verdict': 'approved',
                       'sha256': digest(self.amendment), 'amends_sha256': digest(self.goal)}
        self.write_record(self.record)

    def tearDown(self):
        self.temp.cleanup()

    def write_record(self, record):
        (self.context/'amendment-a-review.json').write_text(json.dumps(record))

    def config(self, **changes):
        item = {'file': 'amendment-a.md', 'sha256': digest(self.amendment), 'review': 'amendment-a-review.json',
                'review_sha256': digest((self.context/'amendment-a-review.json').read_bytes()), **changes}
        return {'directory': str(self.release), 'development': {'id': 'office-ap11', 'amendments': [item]}}

    def test_absent_is_none_and_a_bound_reviewed_amendment_is_delivered_with_its_record(self):
        self.assertEqual(host.goal_amendments({'directory': str(self.release), 'development': {'id': 'office-ap11'}}, self.contract), {})
        self.assertEqual(host.goal_amendments({'directory': str(self.release)}, self.contract), {})
        files = host.goal_amendments(self.config(), self.contract)
        self.assertEqual(files, {'GOAL_AMENDMENT_1.md': self.amendment,
                                 'GOAL_AMENDMENT_1_REVIEW.json': (self.context/'amendment-a-review.json').read_bytes()})
        self.assertEqual(host.amendment_notice(files), [{'path': 'GOAL_AMENDMENT_1.md', 'sha256': digest(self.amendment), 'amends': 'goal.md',
            'review_record': 'GOAL_AMENDMENT_1_REVIEW.json',
            'meaning': 'Separately reviewed amendment of the frozen goal; read it together with goal.md'}])
        self.assertEqual(host.amendment_notice({}), [])

    def test_changed_bytes_are_refused(self):
        bound = self.config()
        (self.context/'amendment-a.md').write_bytes(self.amendment + b'and one more permission\n')
        with self.assertRaisesRegex(ValueError, 'Bound goal amendment changed'): host.goal_amendments(bound, self.contract)
        (self.context/'amendment-a.md').write_bytes(self.amendment)
        self.write_record({**self.record, 'limitations': 'edited after binding'})
        with self.assertRaisesRegex(ValueError, 'Bound goal amendment changed'): host.goal_amendments(bound, self.contract)

    def test_only_a_record_approving_exactly_these_bytes_for_exactly_this_goal_gives_effect(self):
        for name, change in (('not approved', {'verdict': 'approved_with_required_changes'}), ('other bytes', {'sha256': digest(b'revision 1')}),
                             ('other goal', {'amends_sha256': digest(b'another goal')}), ('unnamed reviewer', {'reviewer': '  '}),
                             ('no reviewer', {'reviewer': None})):
            self.write_record({**self.record, **change})
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'no review record approving exactly these bytes'):
                host.goal_amendments(self.config(), self.contract)
        self.write_record(['approved'])
        with self.assertRaisesRegex(ValueError, 'no review record'): host.goal_amendments(self.config(), self.contract)
        self.write_record(self.record)
        with self.assertRaisesRegex(ValueError, 'no review record'):      # the contract's goal, not the file beside it, is what is amended
            host.goal_amendments(self.config(), {**self.contract, 'acceptance_sha256': digest(b'v2')})

    def test_malformed_or_escaping_selections_are_refused(self):
        good = self.config()['development']['amendments'][0]
        (self.release/'outside.md').write_bytes(self.amendment)
        cases = ({**good, 'file': '../outside.md'}, {**good, 'file': 'amendment-a.txt'}, {**good, 'review': 'amendment-a-review.md'},
                 {**good, 'review': '../development-context/amendment-a-review.json'}, {**good, 'note': 'extra'},
                 {k: v for k, v in good.items() if k != 'review_sha256'}, {**good, 'file': None}, 'amendment-a.md')
        for item in cases:
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, 'Invalid bound goal amendments'):
                host.goal_amendments({'directory': str(self.release), 'development': {'amendments': [item]}}, self.contract)
        for selection in ({'a': good}, 'amendment-a.md', [good]*5):
            with self.subTest(selection=type(selection)), self.assertRaisesRegex(ValueError, 'Invalid bound goal amendments'):
                host.goal_amendments({'directory': str(self.release), 'development': {'amendments': selection}}, self.contract)

    def real_base_context(self, config):
        """Runs the REAL base_context; only its repository, policy and non-release reads are substituted."""
        work = {'reconciliation': ['tools/development_result.py']}; real = host.read_regular
        contract = {'work': work, 'authority_sha256': digest(b'authority'), 'acceptance_sha256': digest(self.goal)}
        (self.context/'authority.md').write_bytes(b'authority')
        (self.release/'office/acceptance').mkdir(parents=True, exist_ok=True)
        for name in ('office/AGENTS.md', 'office/acceptance/recipe.py'): (self.release/name).write_bytes(b'x')
        def read(root, name, limit=None):
            return json.dumps(contract).encode() if name == 'contract.json' else real(root, name)
        scope = SimpleNamespace(inspect=lambda: {'control': 'active', 'tasks': {}, 'integrated': {}}, directory=Path('/scope'))
        with patch.object(host, 'policy', return_value=SimpleNamespace(WORK=work, RECIPES={'reconciliation': 'acceptance/recipe.py'})), \
             patch.object(host, 'repository', return_value=Path('/office')), patch.object(host, 'read_regular', side_effect=read), \
             patch.object(host, 'git', side_effect=lambda repo, *args, raw=False: b'source' if raw else 'b'*40):
            return host.base_context(scope, {**config, 'office_revision': 'b'*40, 'runtime_revision': 'c'*40}, 'reconciliation', 'step-1')

    def test_the_real_driver_context_carries_the_amendment_and_is_unchanged_without_one(self):
        context, files = self.real_base_context(self.config())
        self.assertEqual(files['GOAL_AMENDMENT_1.md'], self.amendment); self.assertIn('GOAL_AMENDMENT_1_REVIEW.json', files)
        self.assertEqual(context['goal_amendments'][0]['sha256'], digest(self.amendment))
        self.assertEqual({s['id'] for s in context['sources']}, {'authority', 'goal', 'observation'})     # the Office policy's exact source set
        plain, without = self.real_base_context({'directory': str(self.release), 'development': {'id': 'office-ap11'}})
        self.assertNotIn('goal_amendments', plain); self.assertFalse([n for n in without if n.startswith('GOAL_AMENDMENT')])
        self.assertEqual(set(files) - set(without), {'GOAL_AMENDMENT_1.md', 'GOAL_AMENDMENT_1_REVIEW.json'})
        with self.assertRaisesRegex(ValueError, 'Bound goal amendment changed'):
            self.real_base_context(self.config(sha256=digest(b'other')))

    def test_the_real_diagnosis_call_carries_the_amendment(self):
        (self.context/'authority.md').write_bytes(b'authority'); (self.release/'office').mkdir(exist_ok=True)
        (self.release/'office/AGENTS.md').write_bytes(b'x'); tasks = self.release/'tasks'; tasks.mkdir()
        for name in ('brief.md', 'acceptance.py'): (tasks/name).write_bytes(b'x')
        scope_dir = self.release/'scope'; scope_dir.mkdir(); (scope_dir/'contract.json').write_text(json.dumps(self.contract))
        scope = SimpleNamespace(directory=scope_dir, inspect=lambda: {'tasks': {'t': {'task_sha256': 's', 'work': 'reconciliation'}}})
        delivered = {}
        def call(expected, nonce, role, work, context, files): delivered.update(files); return {'nonce': nonce}
        with patch.object(host, 'active_scope', return_value=(scope, self.config())), patch.object(host, 'load', return_value={'allowed_paths': []}), \
             patch.object(host, 'task_directory', return_value=tasks), patch.object(host, 'prepare_call', side_effect=call):
            host.diagnosis_call('x', 't', {'phase': 'waiting_diagnosis', 'results': []}, 'step-7')
        self.assertEqual(delivered['GOAL_AMENDMENT_1.md'], self.amendment); self.assertIn('GOAL_AMENDMENT_1_REVIEW.json', delivered)
        self.assertEqual(delivered['goal.md'], self.goal)


if __name__ == '__main__':
    unittest.main()
