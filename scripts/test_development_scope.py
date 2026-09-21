"""Isolated launch-boundary proofs; no model, network or active scope access."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from runtime.development_scope import Scope, ScopeClosed, initialize


def contract():
    return {'schema': 1, 'id': 'office-ap11',
            'target': 'Nortropic/nortropic-projektkontor',
            'authority_sha256': 'a'*64, 'acceptance_sha256': 'b'*64,
            'runtime_revision': 'c'*40, 'office_revision': 'd'*40,
            'work': {'reconciliation': ['tools/reconciliation.py'],
                     'handoff': ['tools/handoff.py']},
            'model_calls': 48, 'implementation_attempts': 6}


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve() / 'scope'
        self.bound = initialize(self.path, contract())
        self.scope = Scope(self.path, self.bound)

    def tearDown(self):
        self.tmp.cleanup()

    def bind(self, task='first'):
        self.scope.bind_task('reconciliation', task, 'e'*64,
                             ['tools/reconciliation.py'], 'f'*64)

    def test_all_roles_share_48_calls_and_restart_never_refunds(self):
        self.bind()
        for n in range(48):
            role = ['driver', 'preparation-review', 'diagnosis', 'final-review'][n % 4]
            self.scope.reserve('goal', role, 'call-'+str(n))
        reloaded = Scope(self.path, self.bound)
        with self.assertRaises(ScopeClosed):
            reloaded.reserve('goal', 'driver', 'renamed-next-call')
        self.assertEqual(reloaded.inspect()['control'], 'exhausted')
        with self.assertRaises(ScopeClosed):
            reloaded.control('active', 'must not raise accepted ceiling')
        self.assertEqual(len(reloaded.inspect()['calls']), 48)
        self.assertEqual(reloaded.inspect()['started'], [])  # reservations != starts
        with self.assertRaises(FileExistsError):
            initialize(self.path, contract())

    def test_renamed_tasks_share_six_implementation_attempts(self):
        for n in range(6):
            name = 'renamed-'+str(n)
            self.bind(name)
            self.scope.reserve('reconciliation', 'implementation', 'impl-'+str(n), name, 'e'*64)
        self.bind('renamed-seventh')
        reloaded = Scope(self.path, self.bound)
        with self.assertRaises(ScopeClosed):
            reloaded.reserve('reconciliation', 'implementation', 'impl-7', 'renamed-seventh', 'e'*64)
        self.assertEqual(reloaded.inspect()['implementations']['reconciliation'], 6)
        with self.assertRaises(ScopeClosed):
            reloaded.bind_task('new-work-name', 'evade', 'e'*64,
                               ['tools/reconciliation.py'], 'f'*64)

    def test_concurrent_launches_cannot_cross_global_limit(self):
        for n in range(44):
            self.scope.reserve('goal', 'driver', 'before-'+str(n))
        def launch(n):
            try:
                Scope(self.path, self.bound).reserve('goal', 'driver', 'race-'+str(n))
                return True
            except ScopeClosed:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(launch, range(8))), 4)
        self.assertEqual(len(self.scope.inspect()['calls']), 48)

    def test_paused_child_can_finish_but_new_work_cannot_start(self):
        self.bind()
        self.scope.reserve('reconciliation', 'implementation', 'impl', 'first', 'e'*64)
        self.scope.launch('impl', lambda: 'fake-process')
        self.scope.control('paused', 'operator pause')
        for role, work in [('driver', 'goal'), ('diagnosis', 'goal'), ('implementation', 'reconciliation')]:
            with self.assertRaises(ScopeClosed):
                self.scope.reserve(work, role, 'paused-'+role, 'first', 'e'*64)
        self.scope.reserve('reconciliation', 'review', 'review', 'first', 'e'*64)
        self.scope.permit_publication('reconciliation', 'first', 'e'*64)
        self.assertEqual(Scope(self.path, self.bound).inspect()['control'], 'paused')
        self.scope.control('active', 'explicit authorized resume')
        self.scope.reserve('goal', 'driver', 'resumed')

    def test_stop_blocks_calls_publication_but_retains_racing_remote_receipt(self):
        self.bind()
        self.scope.control('stopped', 'operator stop')
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('goal', 'driver', 'later')
        with self.assertRaises(ScopeClosed):
            self.scope.permit_publication('reconciliation', 'first', 'e'*64)
        receipt = {'integration': 'actual-remote-observation'}
        self.scope.record_integration('reconciliation', 'first', 'e'*64, receipt)
        self.scope.record_integration('reconciliation', 'first', 'e'*64, receipt)
        self.assertEqual(len(self.scope.inspect()['integrated']), 1)
        with self.assertRaises(ScopeClosed):
            self.scope.control('active', 'rename does not undo stop')

    def test_revocation_and_quota_survive_restart(self):
        self.scope.control('quota', 'actual access unavailable')
        with self.assertRaises(ScopeClosed):
            Scope(self.path, self.bound).reserve('goal', 'driver', 'after-restart')
        self.scope.control('active', 'access restored by explicit operator action')
        self.scope.control('revoked', 'owner revoked authority')
        with self.assertRaises(ScopeClosed):
            Scope(self.path, self.bound).control('active', 'cannot self-authorize')

    def test_integrated_work_cannot_be_renamed_or_republished(self):
        self.bind()
        self.scope.record_integration('reconciliation', 'first', 'e'*64, {'merge': 'actual'})
        with self.assertRaises(ScopeClosed):
            self.bind('same-work-new-name')
        with self.assertRaises(ScopeClosed):
            self.scope.permit_publication('reconciliation', 'first', 'e'*64)
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('reconciliation', 'implementation', 'another', 'first', 'e'*64)

    def test_replayed_reservation_and_started_marker_are_not_new_launch(self):
        self.scope.reserve('goal', 'driver', 'one')
        self.scope.launch('one', lambda: 'fake-process')
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('goal', 'driver', 'one')
        with self.assertRaises(ScopeClosed):
            self.scope.launch('one', lambda: self.fail('Duplicate launch'))
        self.assertEqual(self.scope.inspect()['started'], ['one'])

    def test_stop_between_reservation_and_launch_prevents_callback(self):
        self.scope.reserve('goal', 'driver', 'reserved')
        self.scope.control('stopped', 'stop won race before actual Popen')
        with self.assertRaises(ScopeClosed):
            self.scope.launch('reserved', lambda: self.fail('Stopped process started'))
        self.assertEqual(self.scope.inspect()['started'], [])
        self.assertEqual(len(self.scope.inspect()['calls']), 1)

    def test_reserved_but_unstarted_implementation_cannot_authorize_review(self):
        self.bind()
        self.scope.reserve('reconciliation', 'implementation', 'unstarted', 'first', 'e'*64)
        self.scope.control('paused', 'pause before process launch')
        with self.assertRaises(ScopeClosed):
            self.scope.launch('unstarted', lambda: self.fail('Paused process started'))
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('reconciliation', 'review', 'review', 'first', 'e'*64)

    def test_failed_host_launch_does_not_refund_or_fabricate_start(self):
        self.scope.reserve('goal', 'driver', 'failed')
        def fail():
            raise OSError('Synthetic Popen failure')
        with self.assertRaises(OSError):
            self.scope.launch('failed', fail)
        self.assertEqual(self.scope.inspect()['started'], [])
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('goal', 'driver', 'failed')
        with self.assertRaises(ScopeClosed):
            self.scope.launch('failed', lambda: self.fail('Failed launch replayed'))

    def test_incomplete_tampered_or_missing_history_fails_closed(self):
        self.scope.reserve('goal', 'driver', 'before')
        journal = self.path / 'journal.jsonl'
        saved = journal.read_bytes()
        for broken in (saved[:-1], saved.replace(b'before', b'after'), b'{}\n'):
            journal.write_bytes(broken)
            with self.assertRaises((ScopeClosed, ValueError)):
                self.scope.reserve('goal', 'driver', 'after')
        journal.write_bytes(saved)
        journal.unlink()
        with self.assertRaises((ScopeClosed, OSError)):
            self.scope.reserve('goal', 'driver', 'lost-history')

    def test_complete_tail_removal_or_empty_journal_cannot_refund_or_unstop(self):
        self.scope.reserve('goal', 'driver', 'before')
        self.scope.control('stopped', 'persistent operator stop')
        journal = self.path/'journal.jsonl'
        saved = journal.read_bytes()
        for broken in (b'\n'.join(saved.splitlines()[:-1])+b'\n', b''):
            journal.write_bytes(broken)
            with self.assertRaises(ScopeClosed):
                Scope(self.path, self.bound).reserve('goal', 'driver', 'rollback')
        journal.write_bytes(saved)
        self.assertEqual(self.scope.inspect()['control'], 'stopped')

    def test_write_ahead_witness_without_append_is_unavailable_not_refunded(self):
        head = self.path/'head.json'
        head.write_text(json.dumps({'sequence': 1, 'sha256': 'a'*64}))
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('goal', 'driver', 'after-crash')
        self.assertEqual((self.path/'journal.jsonl').read_bytes(), b'')

    def test_contract_cannot_raise_budget_or_move_work_paths(self):
        p = self.path / 'contract.json'
        c = json.loads(p.read_text())
        c['model_calls'] = 49
        p.write_text(json.dumps(c))
        with self.assertRaises(ScopeClosed):
            self.scope.reserve('goal', 'driver', 'tamper')
        for bad in ['tools/../active.py', 'tools/kontor.py', 'tools/assignment_preparation.py']:
            c = contract();c['work']['reconciliation'] = [bad]
            with self.assertRaises(ScopeClosed):
                initialize(self.path.parent/'new', c)

    def test_symlink_journal_does_not_append_outside_scope(self):
        outside = self.path.parent/'untouched'
        outside.write_text('private original')
        (self.path/'journal.jsonl').unlink()
        (self.path/'journal.jsonl').symlink_to(outside)
        with self.assertRaises((ScopeClosed, ValueError, OSError)):
            self.scope.reserve('goal', 'driver', 'outside')
        self.assertEqual(outside.read_text(), 'private original')


if __name__ == '__main__':
    unittest.main()
