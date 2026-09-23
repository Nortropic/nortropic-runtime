"""Checks that read the REAL preserved state, on the host that has it.

Deliberately NOT named test_*.py, so the published suite discovers none of them. A skip inside that suite
would be indistinguishable from a check that quietly stopped running, and the publication requires a green
run with no skips for exactly that reason. These run separately against the primary checkout, and their
result is recorded as its own receipt with the code revision, the import path and the host basis.

Run:  NR_HOST_ROOT=<primary checkout> <runtime venv python> -B scripts/run_host_checks.py <receipt path>
"""
import json
import unittest
from pathlib import Path

from runtime.development_workflow import FiniteAssessment, FiniteDevelopment
from scripts.test_final_evidence import IsolatedProofDeliveryTests, TriggerRecordTests


def required_scope():
    """The preserved application, or a FAILURE - never a skip.

    Independent review of the move found the hole: the checks kept the skipTest guards they had when they
    lived in the published suite, so this module could report success with every check skipped, on any
    checkout. That is the same indistinguishability the move was made to remove, and it would have removed
    the checks from the only run anyone reads. Here, absence of the preserved state is a failing result.
    """
    from runtime.release import ROOT
    directory = ROOT / '.runtime/ap11/application'
    # Exactly what these checks READ, and nothing beside it. An earlier version also demanded
    # .runtime/ap10/active.json, which no check here reads and which the published suite treats as
    # optional, so a host holding the whole preserved application failed all six for an unrelated reason.
    required = {'the scope calls': (directory / 'calls', 'dir'),
                'the scope journal': (directory / 'journal.jsonl', 'file'),
                'the qualification index': (directory / 'qualification' / 'index.json', 'file'),
                'the preserved proof run': (directory / 'qualification' / 'G8-ISOLATED-PROOF-RUN.json', 'file')}
    missing = [f'{what}: {path}' for what, (path, kind) in sorted(required.items())
               if not (path.is_dir() if kind == 'dir' else path.is_file())]
    if missing:
        raise AssertionError(
            'these checks must run against the preserved application; set NR_HOST_ROOT to the checkout that '
            'holds it. Missing or of the wrong kind: ' + repr(missing))
    # Paths existing is not the same as the preserved application being there. Independent review put it
    # plainly twice: a stale copy or a hand-made skeleton with the right four paths satisfied the guard, and
    # a chain walk written HERE proves only internal linkage, because it cannot recompute the host's own
    # per-entry digest without guessing its serialisation. So the host's own verification is used.
    from runtime import release
    from runtime.development_scope import Scope
    # The commitment this scope must BE, from the ACTIVE release as the host itself reads it - outside the
    # directory under test. Independent review named the hole twice. An anchor computed from the contract.json
    # inside that directory is self-referential: a stale or wholesale copy carries its own consistent contract
    # and journal. Reading the pointer here was the same hole one level up: a copy of the whole root carries its
    # own pointer too, and nothing checked the configuration it names. installed() is the host's own reading of
    # the accepted binding: the configuration must be the one the pointer hashes, lie among the releases, and
    # name THIS root as the canonical host - which a copy's configuration does not, because it names the root it
    # was copied from.
    try:
        config = release.installed()
    except ValueError as error:
        raise AssertionError('the ACTIVE release binding does not verify on this host: ' + str(error))
    if config is None:
        raise AssertionError('no ACTIVE release on this host, so the scope cannot be tied to the commitment '
                             'it must be; set NR_HOST_ROOT to the checkout that holds both')
    expected = (config.get('development') or {}).get('contract_sha256')
    if not expected:
        raise AssertionError('the ACTIVE release binds no development contract to check this scope against')
    # inspect() reads the scope under its own lock, fail-closed, with the code the application itself runs:
    # the contract must digest to exactly this commitment, every journal entry must carry the next sequence,
    # link to its predecessor and match its recomputed digest, and head.json must name the last one. An
    # incomplete, tampered or truncated history is refused there.
    state = Scope(directory, expected).inspect()
    if not state.get('calls'):
        raise AssertionError('the preserved application records no counted calls; this is not the scope '
                             'these checks are about')
    return directory


class PreservedEvidenceChecks(IsolatedProofDeliveryTests, TriggerRecordTests):
    """Only the checks that need the host. Their siblings run in the published suite."""

    def test_the_run_record_names_the_text_that_was_actually_delivered(self):
        """A recorded PASS of a different file would prove nothing about the delivered one."""
        import hashlib
        import json
        from runtime.release import ROOT
        record = ROOT / '.runtime/ap11/application/qualification/G8-ISOLATED-PROOF-RUN.json'
        required_scope()
        stated = json.loads(record.read_text())['source']
        source = self.proof_source()
        self.assertEqual(stated['sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(stated['bytes'], len(source))
        self.assertEqual(stated['delivered_as'], self.DELIVERED)

    def test_the_qualification_index_binds_every_preserved_record(self):
        """prepare() delivers exactly what the index names, each by hash, so a record added beside the index
        without being bound is not silently delivered - or silently left out."""
        import hashlib
        import json
        from runtime.release import ROOT
        directory = ROOT / '.runtime/ap11/application/qualification'
        required_scope()
        index = json.loads((directory / 'index.json').read_text())
        present = sorted(p.name for p in directory.iterdir()
                         if p.name != 'index.json' and p.name.endswith(('.md', '.json')))
        self.assertEqual(sorted(index['files']), present, 'every preserved record is bound by the index')
        for name, expected in index['files'].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
        for name in ('G8-NEGATIVE-PROOFS.json', 'G8-ISOLATED-PROOF-RUN.json'):
            self.assertIn(name, index['files'], 'the answer to finding 4 is delivered, not just written')

    def test_the_real_preserved_sessions_divide_exactly_as_measured(self):
        """Against this application's own six preserved sessions, not a fixture."""
        from runtime.development_interactive import trigger_record
        from runtime.release import ROOT
        calls = required_scope() / 'calls'
        stages = sorted(d for d in calls.iterdir() if (d / 'session-exit.json').is_file())
        self.assertTrue(stages, 'the preserved interactive sessions are there')
        available = {d.name: trigger_record(d) for d in stages}
        for name, record in available.items():
            with self.subTest(stage=name):
                if record['available']:
                    self.assertEqual(record['operator_bytes_hex'], '0303')
                    self.assertEqual(record['final_completed_turn']['stop_reason'], 'end_turn')
                    self.assertEqual(record['session_id'], record['session_id_in_terminal'])
                else:
                    self.assertTrue(record['reason'].strip(), 'a refusal states its reason')


class PopulatedScopeTests(unittest.TestCase):
    """Against the REAL scope this application filled, not a fixture.

    The owner's requirement: the re-assessment must be able to use an already populated scope without
    reusing old stages, without starting A/B again, and without producing operator records for events that
    did not actually happen. The first two are checked here against the actual stage names on disk; the
    third follows from them, because the spurious host answers came from the collision loop.
    """

    def scope_directory(self):
        from runtime.release import ROOT
        directory = ROOT / '.runtime/ap11/application'
        required_scope()
        return directory

    def test_no_assessment_key_can_land_on_a_stage_this_scope_already_has(self):
        directory = self.scope_directory()
        existing = {p.name for p in (directory / 'calls').iterdir() if p.is_dir()}
        self.assertTrue(existing, 'the scope really is populated')
        # Far beyond what one assessment can spend: its own ceiling is the shared 48.
        for sequence in range(1, 200):
            key = FiniteAssessment.KEY_PREFIX + str(sequence)
            with self.subTest(key=key):
                self.assertNotIn(key, existing)

    def test_an_inherited_namespace_really_does_reach_an_existing_stage(self):
        """Why the prefix exists, stated against the real stages rather than as a hypothetical - and stated
        accurately.

        The independent review predicted the collision at step-2. On THIS scope that is not what would have
        happened: step-2 never became a stage, because the sequence numbers that create one are only those
        whose operation prepares a counted call. The assessment's first counted call would have landed on a
        free key. The hazard is nonetheless real, one activity error away: the error path advances the key by
        one, and this scope does hold stages in the low single digits, so a single host-diagnosis retry walks
        straight into one. A correctness that depends on which sequence numbers happened to materialise is
        not a correctness, which is what the prefix removes.
        """
        directory = self.scope_directory()
        existing = {p.name for p in (directory / 'calls').iterdir() if p.is_dir()}
        inherited = [FiniteDevelopment.KEY_PREFIX + str(n) for n in range(2, 12)]
        collisions = [key for key in inherited if key in existing]
        self.assertTrue(collisions,
                        'an inherited namespace reaches an existing stage within a few advances: ' +
                        repr(sorted(existing)))
        self.assertNotIn(FiniteDevelopment.KEY_PREFIX + '2', existing,
                         'and specifically NOT at step-2, contrary to the prediction')
        self.assertEqual([k for k in inherited if k in existing][0], FiniteDevelopment.KEY_PREFIX + '4',
                         'the first one it would reach is step-4')

    def test_the_assessment_key_is_a_valid_scope_identity(self):
        from runtime.development_scope import identifier
        for sequence in (1, 48):
            key = FiniteAssessment.KEY_PREFIX + str(sequence)
            self.assertEqual(identifier(key), key)
            self.assertLessEqual(len(key), 80)

    def test_the_preserved_run_keeps_its_keys_journal_and_verdict(self):
        """Nothing in the assessment path renames, removes or rewrites what the first run recorded."""
        directory = self.scope_directory()
        self.assertTrue((directory / 'journal.jsonl').is_file(), 'the journal is still there')
        stages = {p.name for p in (directory / 'calls').iterdir() if p.is_dir()}
        self.assertTrue(any(name.startswith(FiniteDevelopment.KEY_PREFIX) for name in stages))
        self.assertFalse(any(name.startswith(FiniteAssessment.KEY_PREFIX) for name in stages),
                         'no assessment stage exists yet: nothing has been run')


if __name__ == '__main__':
    unittest.main()
