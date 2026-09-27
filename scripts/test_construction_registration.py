"""Host registration refuses candidate claims and preserves immutable acceptance."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from runtime.construction_registration import register, resolve_profile


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.host = Path(self.tmp.name).resolve()
        self.source = self.host / 'owner-source.txt'; self.source.write_text('Synthetic accepted scoped fixture, no real authority')
        self.hash = sha256(self.source.read_bytes()).hexdigest()
        self.accepted = self.host / '.runtime/ap11/accepted/new-task.json'
        self.accepted.parent.mkdir(parents=True)
        self.record = {'schema': 'construction-acceptance/1', 'id': 'new-task',
            'source': str(self.source), 'source_sha256': self.hash, 'targets': ['office'],
            'accepted': True, 'basis': 'Synthetic test of host record, not a content keyword grant', 'holder': 'fixture'}
        self.accepted.write_text(json.dumps(self.record))

    def issue(self, **changes):
        args = dict(identifier='new-task', target='office', source=self.source,
                    expected_sha256=self.hash, acceptance_record=self.accepted, host=self.host)
        args.update(changes); return register(**args)

    def test_new_name_resolves_same_fixed_target_and_duplicate_refuses(self):
        self.issue(); profile = resolve_profile('new-task', self.host)
        self.assertEqual(profile['target'], 'Nortropic/nortropic-projektkontor')
        self.assertEqual(profile['mandate_sha256'], self.hash)
        with self.assertRaises(FileExistsError): self.issue()

    def test_unknown_target_and_unaccepted_or_candidate_record_refused(self):
        for target in ('evil/repo', 'runtime'):
            with self.assertRaises(ValueError): self.issue(target=target)
        copied = self.host / 'candidate-acceptance.json'; copied.write_bytes(self.accepted.read_bytes())
        with self.assertRaises(ValueError): self.issue(acceptance_record=copied)
        self.record['accepted'] = False; self.accepted.write_text(json.dumps(self.record))
        with self.assertRaises(ValueError): self.issue()

    def test_source_or_acceptance_changed_after_registration_refuses(self):
        self.issue(); original = self.source.read_bytes(); self.source.write_text('a matching phrase is not authority')
        with self.assertRaises(ValueError): resolve_profile('new-task', self.host)
        self.source.write_bytes(original); self.accepted.write_text('{}')
        with self.assertRaises(ValueError): resolve_profile('new-task', self.host)

    def test_no_name_traversal_unsealed_or_unknown_registration(self):
        with self.assertRaises(ValueError): self.issue(identifier='../new-task')
        with self.assertRaises(ValueError): resolve_profile('unknown', self.host)
        self.issue(); (self.host / '.runtime/ap11/registrations/new-task.json').chmod(0o600)
        with self.assertRaises(ValueError): resolve_profile('new-task', self.host)


if __name__ == '__main__': unittest.main()
