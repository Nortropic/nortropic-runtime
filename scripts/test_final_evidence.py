"""The whole-goal review must actually receive the history its criteria rest on.

Measured on the live application 2026-09-22: the final-review call was refused before any model ran, because
NATIVE_HISTORY.json was delivered whole at 1324577 bytes while read_regular accepts 262144. Marking an oversized
history unavailable would be correct error handling and a useless review basis, so the history is delivered
SPLIT: ordered, hash-bound parts with an index, none of them a summary.

These tests use the REAL delivery and read checks - prepare_call's bundle bound and read_regular's per-file
bound - rather than asserting against the constants, because the first version passed a constant check and was
refused by the receiver. No model runs here.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.development_final import history_parts, HISTORY_PART_BYTES, BUNDLE_BYTES
from runtime.snapshot import read_regular


def event(number, payload=''):
    """The shape MessageToDict produces for a history event, with a payload to drive the size.

    Every event gets its OWN time. Review caught the first version giving them all one timestamp, which made
    the index's first/last time assertions compare a constant with itself: a swap of the two survived the whole
    suite. The same hole had already been found once in the id fields, so it is closed here in the data.
    """
    return {'eventId': str(number), 'eventTime': '2026-09-22T21:%02d:%02dZ' % (number // 60 % 60, number % 60),
            'eventType': 'ActivityTaskCompleted', 'attributes': {'result': payload}}


def history(counts):
    return {name: [event(i, 'x' * size) for i in range(1, n + 1)] for name, (n, size) in counts.items()}


ROOM = BUNDLE_BYTES - 256 * 1024          # what a realistic bundle leaves for the history


class SplitTests(unittest.TestCase):
    def test_every_delivered_part_is_within_the_readers_own_per_file_bound(self):
        """The bound that actually refused the live call, applied to every part.

        The events are deliberately SMALL. With large ones a part closes far below the bound, so the
        assertion would pass for any part size up to the reader's limit and would not notice the
        wrapper overhead at all - review measured that exact hole with 2000-byte events.
        """
        files = history_parts(history({'office-ap11': (4000, 60), 'child': (300, 60)}), ROOM)
        self.assertGreater(len(files), 2, 'the history really was split')
        for name, body in files.items():
            with self.subTest(name=name):
                self.assertLessEqual(len(body), 262144, 'read_regular refuses anything larger')

    def test_the_part_bound_leaves_room_for_the_wrapper_the_host_adds(self):
        """A part is its events PLUS a wrapper; the constant has to account for it, not just approach it."""
        files = history_parts(history({'office-ap11': (4000, 60)}), ROOM)
        parts = [v for k, v in files.items() if k != 'NATIVE_HISTORY_INDEX.json']
        self.assertGreater(max(len(p) for p in parts), HISTORY_PART_BYTES * 0.9,
                           'a full part really does approach the size bound, so the margin is load-bearing')
        self.assertLessEqual(max(len(p) for p in parts), 262144)

    def test_the_parts_carry_every_event_in_order_with_nothing_dropped(self):
        source = history({'office-ap11': (300, 2000)})
        files = history_parts(source, ROOM)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        entry = index['workflows']['office-ap11']
        self.assertTrue(entry['complete'])
        self.assertEqual(entry['gaps'], [])
        self.assertEqual(entry['delivered_events'], entry['events'])
        seen = []
        for part in entry['parts']:
            seen.extend(json.loads(files[part['file']]))
        self.assertEqual(seen, source['office-ap11'], 'byte-identical events, in the original order')

    def test_the_index_binds_each_part_by_hash_and_names_the_complete_original(self):
        import hashlib
        source = history({'office-ap11': (200, 2000)})
        files = history_parts(source, ROOM)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        entry = index['workflows']['office-ap11']
        self.assertEqual(entry['complete_sha256'],
                         hashlib.sha256(json.dumps(source['office-ap11']).encode()).hexdigest(),
                         'the hash ties the parts back to the original that stays private')
        for part in entry['parts']:
            self.assertEqual(part['sha256'], hashlib.sha256(files[part['file']]).hexdigest())
        self.assertEqual([p['part'] for p in entry['parts']], list(range(1, len(entry['parts']) + 1)))

    def test_a_part_is_a_slice_and_never_a_summary(self):
        files = history_parts(history({'office-ap11': (200, 2000)}), ROOM)
        body = files['NATIVE_HISTORY_office-ap11_1.json'].decode()
        part = json.loads(body)
        self.assertTrue(all(set(e) == {'eventId', 'eventTime', 'eventType', 'attributes'} for e in part),
                        'whole events, not reduced ones')
        # The shape the reviewer's reader depends on: one whole event per line, so offset and limit can slice
        # it. The first delivery passed the host's byte check as a single line and could not be opened at all.
        lines = body.splitlines()
        self.assertEqual((lines[0], lines[-1]), ('[', ']'))
        self.assertEqual(len(lines), len(part) + 2, 'exactly one event per line between the brackets')
        self.assertEqual(json.loads(lines[1].rstrip(',')), part[0], 'line 2 is event 1, verbatim')

    def test_an_event_too_large_for_any_part_is_an_explicit_gap_not_a_shortened_event(self):
        source = history({'office-ap11': (5, 1000)})
        source['office-ap11'].insert(2, event(99, 'x' * (HISTORY_PART_BYTES + 10)))
        files = history_parts(source, ROOM)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        entry = index['workflows']['office-ap11']
        self.assertEqual([g['event_id'] for g in entry['gaps']], ['99'])
        self.assertFalse(entry['gaps'][0]['delivered'])
        self.assertFalse(entry['complete'])
        self.assertIn('warning', entry)
        delivered = [e for p in entry['parts'] for e in json.loads(files[p['file']])]
        self.assertNotIn('99', [e['eventId'] for e in delivered], 'not delivered')
        self.assertTrue(all(len(json.dumps(e).encode()) <= HISTORY_PART_BYTES for e in delivered),
                        'and nothing was shortened to make it fit')

    def test_a_shortfall_of_room_is_a_named_review_gap_not_a_quiet_omission(self):
        source = history({'office-ap11': (400, 2000)})
        files = history_parts(source, 300 * 1024)               # deliberately too little
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        entry = index['workflows']['office-ap11']
        self.assertFalse(index['complete'])
        self.assertFalse(entry['complete'])
        self.assertTrue(entry['gaps'], 'the shortfall is stated')
        self.assertIn('REVIEW GAP', entry['gaps'][0]['reason'])
        self.assertIn('event_id', json.dumps(entry['gaps'][0]), 'and it names which events are missing')
        self.assertIn('warning', entry)

    def test_a_shortfall_costs_the_oldest_events_and_keeps_the_most_recent(self):
        """The criteria that rest on this material concern the most recent stretch."""
        source = history({'office-ap11': (400, 2000)})
        files = history_parts(source, 300 * 1024 + 32 * 1024)
        entry = json.loads(files['NATIVE_HISTORY_INDEX.json'])['workflows']['office-ap11']
        delivered = [int(e['eventId']) for p in entry['parts'] for e in json.loads(files[p['file']])]
        self.assertIn(400, delivered, 'the last event is delivered')
        self.assertNotIn(1, delivered, 'the earliest are the ones given up')

    def test_a_shortfall_shortens_every_workflow_rather_than_starving_one(self):
        """Review found the opposite: relying on the order the histories happen to have made the LAST
        workflow best served and the parent - whose waits and absent signals the criteria rest on - worst."""
        source = history({'office-ap11': (400, 2000), 'child': (400, 2000)})
        files = history_parts(source, 700 * 1024 + 32 * 1024)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        self.assertFalse(index['complete'])
        for name, entry in index['workflows'].items():
            with self.subTest(name=name):
                self.assertTrue(entry['parts'], 'no workflow is starved outright')
                self.assertTrue(entry['gaps'], 'and each gave up its own oldest')
                last = json.loads(files[entry['parts'][-1]['file']])[-1]
                self.assertEqual(last['eventId'], '400', 'every workflow keeps its most recent events')

    def test_a_large_child_does_not_push_the_parent_out_of_the_room(self):
        """The defect review found: with the order the histories happen to have, a big child took every byte
        and the parent - the workflow the criteria actually rest on - was served last and got nothing.

        Named for what the code guarantees, not more: recency-first priority. A workflow whose newest part
        alone is bigger than the room left still gets nothing, and that stays an explicit gap.
        """
        source = history({'office-ap11': (300, 2000), 'child': (900, 2000)})
        files = history_parts(source, 700 * 1024 + 32 * 1024)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        parent = index['workflows']['office-ap11']
        self.assertGreater(parent['delivered_events'], 0, 'the parent is served, not starved')
        last = json.loads(files[parent['parts'][-1]['file']])[-1]
        self.assertEqual(last['eventId'], '300', 'and it keeps its most recent events')
        share = parent['delivered_events'] / parent['events']
        child = index['workflows']['child']
        self.assertGreaterEqual(share, child['delivered_events'] / child['events'],
                                'the parent is never the worse served of the two')

    def test_the_index_ranges_match_what_the_parts_actually_contain(self):
        """Review: swapping first and last event id in the index survived the whole suite. With the index
        as the reader's only navigation aid, a silent error there would go unnoticed."""
        files = history_parts(history({'office-ap11': (300, 2000), 'child': (40, 1500)}), ROOM)
        index = json.loads(files['NATIVE_HISTORY_INDEX.json'])
        for name, entry in index['workflows'].items():
            for part in entry['parts']:
                with self.subTest(file=part['file']):
                    events = json.loads(files[part['file']])
                    self.assertEqual(part['first_event_id'], events[0]['eventId'])
                    self.assertEqual(part['last_event_id'], events[-1]['eventId'])
                    self.assertEqual(part['first_event_time'], events[0]['eventTime'])
                    self.assertEqual(part['last_event_time'], events[-1]['eventTime'])
                    self.assertEqual(part['events'], len(events))

    def test_the_index_carries_times_because_the_criteria_are_stated_in_time(self):
        files = history_parts(history({'office-ap11': (300, 2000)}), ROOM)
        for part in json.loads(files['NATIVE_HISTORY_INDEX.json'])['workflows']['office-ap11']['parts']:
            self.assertTrue(part['first_event_time'] and part['last_event_time'],
                            'a reader can find the part covering an interval without opening each one')

    def test_an_index_larger_than_its_allowance_is_still_delivered_if_a_reader_can_open_it(self):
        """Review: refusing at the allowance rather than at the reader's bound turned a large history into a
        hard failure of the whole preparation, for an index the receiver would have accepted.

        The band between the two bounds needs about 40000 events to reach naturally. Shrinking the allowance
        puts a normal index in that band instead, which exercises the same decision without a 30 MB fixture.
        """
        from unittest.mock import patch
        from runtime import development_final
        source = history({'office-ap11': (300, 2000)})
        with patch.object(development_final, 'INDEX_BYTES', 512):
            files = history_parts(source, ROOM)
        index = files['NATIVE_HISTORY_INDEX.json']
        self.assertGreater(len(index), 512, 'the index really is past its allowance')
        self.assertLessEqual(len(index), 262144, 'but well inside what the reader accepts, so it is delivered')
        self.assertTrue(json.loads(index)['complete'])

    def test_the_index_is_itself_within_the_readers_bound(self):
        files = history_parts(history({'office-ap11': (300, 2000)}), ROOM)
        self.assertLessEqual(len(files['NATIVE_HISTORY_INDEX.json']), 262144,
                             'the index is delivered too, so it obeys the same bound as every other file')

    def test_the_index_is_counted_against_the_room_it_was_given(self):
        """Review: the index was added after the room accounting, so the package could exceed its own budget.

        The room is calibrated from the real part size so the parts fill it TIGHTLY. A round number leaves
        a part-sized hole, and then the index fits inside the hole and the assertion passes either way -
        which is exactly how the first version of this test passed while the accounting was still missing.
        """
        source = history({'office-ap11': (600, 2000)})
        loose = history_parts(source, 8 * 1024 * 1024)
        parts_only = sum(len(v) for k, v in loose.items() if k != 'NATIVE_HISTORY_INDEX.json')
        # Exactly one byte more than every part needs. Accounting for the index means one part is given up;
        # not accounting for it means every part fits and the index is then written on top of a full budget.
        room = parts_only + 1
        files = history_parts(source, room)
        self.assertLessEqual(sum(len(v) for v in files.values()), room,
                             'the package, index included, stays inside the room it was given')

    def test_the_whole_bundle_stays_within_the_bound_prepare_call_enforces(self):
        rest = 256 * 1024
        files = history_parts(history({'office-ap11': (700, 2000), 'child': (60, 1500)}), BUNDLE_BYTES - rest)
        self.assertLessEqual(sum(len(v) for v in files.values()) + rest, BUNDLE_BYTES)


class RealReaderTests(unittest.TestCase):
    """Not the constants - the receiver's own function, on files written the way the host writes them."""

    def test_the_actual_read_check_accepts_every_delivered_part(self):
        import tempfile
        from pathlib import Path
        files = history_parts(history({'office-ap11': (500, 2000)}), ROOM)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in files.items():
                (root / name).write_bytes(body)
            for name in files:
                with self.subTest(name=name):
                    self.assertEqual(read_regular(root, name), files[name],
                                     'the same call that refused the live delivery accepts this one')

    def test_the_old_unsplit_shape_is_what_the_reader_refuses(self):
        """Names the defect this corrects, so a regression cannot pass quietly."""
        import tempfile
        from pathlib import Path
        whole = json.dumps(history({'office-ap11': (700, 2000)})).encode()
        self.assertGreater(len(whole), 262144)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'NATIVE_HISTORY.json').write_bytes(whole)
            with self.assertRaises(ValueError):
                read_regular(root, 'NATIVE_HISTORY.json')

class DeliveryBoundTests(unittest.TestCase):
    """The owner raised ONE role's delivery bound. These check it stayed one role's.

    Owner decision of 2026-09-23: final-review gets 3 MiB because the measured whole-goal material is
    2111037 bytes; every other role keeps 2 MiB; the per-file bound is untouched; and the bound follows the
    HOST's role choice, never anything the model or the package could influence.
    """

    def test_only_the_whole_goal_review_was_raised(self):
        from runtime.development_host import CONTEXT_BYTES
        self.assertEqual(CONTEXT_BYTES['final-review'], 3145728)
        self.assertEqual(CONTEXT_BYTES[None], 2097152)
        self.assertEqual(set(CONTEXT_BYTES), {None, 'final-review'},
                         'exactly one role is named; every other role falls to the default')

    def test_every_other_role_still_falls_to_the_default(self):
        from runtime.development_model import ROLES
        from runtime.development_host import CONTEXT_BYTES
        for role in ROLES:
            if role == 'final-review':
                continue
            with self.subTest(role=role):
                self.assertEqual(CONTEXT_BYTES.get(role, CONTEXT_BYTES[None]), 2097152)

    def test_the_bound_follows_the_hosts_role_and_nothing_in_the_package(self):
        """A package cannot argue itself a larger frame: the only input to the choice is the role the host
        passes, and every host call site passes a literal."""
        import ast
        import inspect as inspect_module
        from runtime import development_host, development_final, development_activity, development_interactive
        source = inspect_module.getsource(development_host.prepare_call)
        lookups = [n for n in ast.walk(ast.parse(source.lstrip()))
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get'
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == 'CONTEXT_BYTES']
        self.assertEqual(len(lookups), 1, 'the bound is chosen in exactly one place')
        self.assertIsInstance(lookups[0].args[0], ast.Name, 'keyed by the role parameter, not by any content')
        self.assertEqual(lookups[0].args[0].id, 'role')
        for module in (development_final, development_activity, development_interactive, development_host):
            for node in ast.walk(ast.parse(inspect_module.getsource(module))):
                if (isinstance(node, ast.Call) and getattr(node.func, 'attr', getattr(node.func, 'id', None))
                        == 'prepare_call' and len(node.args) > 2):
                    with self.subTest(module=module.__name__):
                        self.assertIsInstance(node.args[2], ast.Constant,
                                              'every caller names its role literally, so no value can travel in')

    def run_prepare_call(self, role, payload_bytes, bounds):
        """The REAL prepare_call, with only the scope and the Office policy substituted."""
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from runtime import development_host
        with tempfile.TemporaryDirectory() as directory:
            scope = SimpleNamespace(directory=Path(directory), expected='x')
            policy = SimpleNamespace(schema=lambda r, w: {'type': 'object'},
                                     instructions=lambda r, w: 'do the thing')
            with patch.object(development_host, 'active_scope', return_value=(scope, {})), \
                 patch.object(development_host, 'policy', return_value=policy), \
                 patch.object(development_host, 'CONTEXT_BYTES', bounds):
                return development_host.prepare_call('x', 'probe', role, 'goal', {},
                                                     {'BIG.json': b'x' * payload_bytes})

    def test_going_over_the_bound_is_refused_rather_than_shortened(self):
        """Not a constant check: the real function, with a payload past the frame it was given."""
        for role, size in (('driver', 4096), ('final-review', 8192)):
            with self.subTest(role=role), self.assertRaises(ValueError) as caught:
                self.run_prepare_call(role, size, {None: 2048, 'final-review': 4096})
            self.assertIn('exceeds its bound', str(caught.exception))

    def test_the_same_payload_passes_for_the_raised_role_and_is_refused_for_the_others(self):
        """The difference the owner's decision actually makes, exercised in both directions on one payload."""
        bounds = {None: 2048, 'final-review': 65536}
        self.assertIsNotNone(self.run_prepare_call('final-review', 4096, bounds),
                             'the raised role accepts a payload the default would refuse')
        with self.assertRaises(ValueError) as caught:
            self.run_prepare_call('driver', 4096, bounds)
        self.assertIn('exceeds its bound', str(caught.exception))

    def test_nothing_is_written_when_the_bound_refuses(self):
        """A refusal must not leave a half-delivered call behind."""
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from runtime import development_host
        with tempfile.TemporaryDirectory() as directory:
            scope = SimpleNamespace(directory=Path(directory), expected='x')
            policy = SimpleNamespace(schema=lambda r, w: {'type': 'object'},
                                     instructions=lambda r, w: 'do the thing')
            with patch.object(development_host, 'active_scope', return_value=(scope, {})), \
                 patch.object(development_host, 'policy', return_value=policy), \
                 patch.object(development_host, 'CONTEXT_BYTES', {None: 1024}):
                with self.assertRaises(ValueError):
                    development_host.prepare_call('x', 'probe', 'driver', 'goal', {}, {'BIG.json': b'x' * 4096})
            written = sorted(q.name for q in (Path(directory) / 'calls/probe/workspace').iterdir()
                             if q.is_file())
            self.assertEqual(written, [], 'no source file was written before the bound refused')


class IsolatedProofDeliveryTests(unittest.TestCase):
    """The first whole-goal review found G8's ceiling refusals described but not delivered.

    The 49th model process and the seventh implementation attempt are never reached by this application, so
    their refusal has no live evidence in it. The proofs exist in isolation; these check they now travel with
    the package, and that what travels is the release's own text rather than a working copy.
    """

    DELIVERED = 'proofs/test_development_scope.py'
    PROOFS = ('def test_all_roles_share_48_calls_and_restart_never_refunds',
              'def test_renamed_tasks_share_six_implementation_attempts')

    def delivery_node(self):
        """The single statement in prepare() that produces the delivered proofs."""
        import ast
        import inspect as inspect_module
        from runtime import development_final
        for node in ast.walk(ast.parse(inspect_module.getsource(development_final.prepare).lstrip())):
            if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
                    and isinstance(node.targets[0].slice, ast.Constant)
                    and node.targets[0].slice.value == self.DELIVERED):
                return node
        self.fail('prepare() no longer delivers ' + self.DELIVERED)

    def test_the_proofs_are_read_from_the_releases_own_revision(self):
        """Not from the working tree. A working-copy read would let edited text be presented as the text the
        running release was built from."""
        import ast
        node = self.delivery_node()
        self.assertIsInstance(node.value, ast.Call)
        self.assertEqual(getattr(node.value.func, 'id', None), 'git',
                         'delivered through git, so the bytes come from a revision')
        spec = ast.unparse(node.value.args[2])
        self.assertIn("config['runtime_revision']", spec,
                      'bound to the ACTIVE release revision, not a branch, tag or working file')
        self.assertIn('scripts/test_development_scope.py', spec)
        self.assertEqual(ast.unparse(node.value.args[0]), 'repository(RUNTIME)')
        self.assertEqual(ast.unparse(node.value.args[1]), "'show'")

    def proof_source(self):
        """The delivered text, at the revision the host would deliver. Where an active release is visible that
        is its recorded revision; otherwise the revision this checkout is on, which is the same question asked
        of the code under test rather than a weaker one."""
        import json
        from runtime.candidate import git
        from runtime.release import ROOT
        from runtime.targets import RUNTIME, repository
        active = ROOT / '.runtime/ap10/active.json'
        revision = 'HEAD'
        if active.is_file():
            revision = json.loads(
                Path(json.loads(active.read_text())['config']).read_text())['runtime_revision']
        return git(repository(RUNTIME), 'show',
                   revision + ':scripts/test_development_scope.py', raw=True)

    def test_the_delivered_revision_really_contains_both_named_proofs(self):
        """The shape above says WHERE it reads. This says the text found there is the evidence claimed."""
        source = self.proof_source().decode()
        self.assertIn('Isolated launch-boundary proofs', source.splitlines()[0],
                      'the delivered module is the isolated-proof module G8 asks for')
        for proof in self.PROOFS:
            with self.subTest(proof=proof):
                self.assertIn(proof, source)
        self.assertNotIn('active_scope', source, 'an isolated proof does not reach the live scope')

class TriggerRecordTests(unittest.TestCase):
    """Amendment section 4 wants every Ctrl-C pair justified by a positively observed idle prompt.

    The operator types those bytes, so the host cannot testify to the intent. These check what it CAN do:
    read back its own recording in the order the terminal wrote it, and refuse where that order is absent.
    """

    TURN = 'done 1:24 PM'
    IDLE = '❯'
    ACK = 'Press Ctrl-C again to exit'
    SESSION = 'b552e88d-b66c-4deb-9e8e-87a1ad17438c'

    def stage(self, directory, terminal, operator=b'\x03\x03', rows=None, session=SESSION):
        import json
        stage = Path(directory)
        stage.mkdir(parents=True, exist_ok=True)
        (stage / 'operator-input.raw').write_bytes(operator)
        (stage / 'terminal.raw').write_bytes(terminal.encode())
        if rows is None:
            rows = [{'type': 'assistant', 'sessionId': session, 'timestamp': '2026-09-22T11:24:18.543Z',
                     'version': '2.1.257',
                     'message': {'model': 'claude-fable-5-1', 'stop_reason': 'end_turn'}}]
        (stage / 'native-interactive-session.jsonl').write_text(
            ''.join(json.dumps(r) + '\n' for r in rows))
        (stage / 'session-exit.json').write_text(json.dumps({'provider': {'thread_id': session}}))
        return stage

    def ordered(self, turn=TURN, idle=IDLE, ack=ACK, session=SESSION):
        return 'work\n%s\n%s\n%s\nResume this session with:\nclaude --resume %s\n' % (turn, idle, ack, session)

    def record(self, **kwargs):
        import tempfile
        from runtime.development_interactive import trigger_record
        with tempfile.TemporaryDirectory() as directory:
            return trigger_record(self.stage(Path(directory) / 'stage', **kwargs))

    def test_the_observed_order_is_what_makes_the_record_available(self):
        record = self.record(terminal=self.ordered())
        self.assertTrue(record['available'])
        self.assertEqual(record['pairs'], 1)
        self.assertEqual([o['quote'] for o in record['observed_order']], [self.TURN, self.IDLE, self.ACK])
        offsets = [o['terminal_offset'] for o in record['observed_order']]
        self.assertEqual(offsets, sorted(offsets), 'the stream is append-only, so the order is the evidence')
        # Read every offset BACK against the terminal it claims to index. Sorted-and-non-decreasing passed
        # for the wrong reason once: a regression made the first offset always 0, which satisfies ordering
        # trivially while pointing at the start of the stream instead of the quoted line.
        terminal = self.ordered()
        for entry in record['observed_order']:
            with self.subTest(what=entry['what']):
                at = entry['terminal_offset']
                self.assertEqual(terminal[at:at + len(entry['quote'])], entry['quote'],
                                 'the offset locates the text printed beside it')
        self.assertGreater(record['observed_order'][0]['terminal_offset'], 0,
                           'the first offset is a real position, not the start of the stream')
        self.assertEqual(record['final_completed_turn']['model'], 'claude-fable-5-1')
        self.assertEqual(record['final_completed_turn']['version'], '2.1.257')
        self.assertEqual(record['provider_error_rows'], 0)

    def test_an_idle_prompt_before_the_final_turn_does_not_justify_the_pair(self):
        """The prompt has to come AFTER the turn completed. A prompt from earlier in the session is the
        terminal being idle at some other moment, which justifies nothing."""
        record = self.record(terminal='work\n%s\n%s\n%s\n' % (self.IDLE, self.TURN, self.ACK))
        self.assertFalse(record['available'])
        self.assertIn('No idle prompt', record['reason'])

    def test_a_session_that_never_acknowledged_the_first_ctrl_c_is_refused(self):
        """Without that line the terminal never reported itself idle; the same byte on a busy session is an
        interrupt, which is a different event entirely."""
        record = self.record(terminal='work\n%s\n%s\n' % (self.TURN, self.IDLE))
        self.assertFalse(record['available'])
        self.assertIn('never acknowledged', record['reason'])

    def test_a_pair_with_no_completed_turn_before_it_is_refused(self):
        record = self.record(terminal='work\n%s\n%s\n' % (self.IDLE, self.ACK))
        self.assertFalse(record['available'])
        self.assertIn('No completed turn', record['reason'])

    def test_operator_bytes_that_are_not_whole_pairs_are_refused(self):
        for operator in (b'\x03', b'\x03\x03\x03', b'/exit\r\r', b''):
            with self.subTest(operator=operator):
                record = self.record(terminal=self.ordered(), operator=operator)
                self.assertFalse(record['available'])
                self.assertIn('Ctrl-C pairs', record['reason'])

    def test_a_provider_error_row_refuses_the_record(self):
        rows = [{'type': 'assistant', 'sessionId': self.SESSION, 'timestamp': 't', 'version': '2.1.257',
                 'message': {'model': 'claude-fable-5-1', 'stop_reason': 'end_turn'}},
                {'type': 'error', 'sessionId': self.SESSION}]
        record = self.record(terminal=self.ordered(), rows=rows)
        self.assertFalse(record['available'])
        self.assertIn('provider error row', record['reason'])

    def test_the_pair_must_belong_to_the_session_the_host_recorded(self):
        """Otherwise a pair from one session could justify the closure of another."""
        record = self.record(terminal=self.ordered(session='11111111-2222-3333-4444-555555555555'))
        self.assertFalse(record['available'])
        self.assertIn('not the one the host recorded', record['reason'])

    def test_incomplete_preservation_is_named_rather_than_worked_around(self):
        import tempfile
        from runtime.development_interactive import trigger_record
        for missing in ('terminal.raw', 'native-interactive-session.jsonl', 'operator-input.raw'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                stage = self.stage(Path(directory) / 'stage', terminal=self.ordered())
                (stage / missing).unlink()
                record = trigger_record(stage)
                self.assertFalse(record['available'])
                self.assertIn(missing, record['reason'])

class EveryPairIsVerifiedTests(TriggerRecordTests):
    """Owner precision: the observed COUNT of pairs is not the same as verified content.

    The first version counted pairs from the operator bytes but checked only the first acknowledgement, so a
    two-pair session would have carried a record asserting justification for both. The evidence requirement
    is unchanged - amendment section 4 asks every pair to be justified - so the check was corrected to meet
    it rather than the claim narrowed to match the check.
    """

    def two_pairs(self, second_turn=True, second_idle=True):
        turn, idle, ack = self.TURN, self.IDLE, self.ACK
        text = 'work\n%s\n%s\n%s\n' % (turn, idle, ack)
        text += 'more work\n'
        if second_turn:
            text += '%s\n' % turn
        if second_idle:
            text += '%s\n' % idle
        return text + '%s\nResume this session with:\nclaude --resume %s\n' % (ack, self.SESSION)

    def test_two_pairs_each_with_its_own_justification_are_verified(self):
        record = self.record(terminal=self.two_pairs(), operator=b'\x03\x03\x03\x03')
        self.assertTrue(record['available'])
        self.assertEqual((record['pairs'], record['verified_pairs']), (2, 2))
        self.assertEqual([p['pair'] for p in record['per_pair']], [1, 2])
        for entry in record['per_pair']:
            offsets = entry['offsets']
            self.assertLess(offsets['completed_turn'], offsets['idle_prompt'])
            self.assertLess(offsets['idle_prompt'], offsets['acknowledgement'])

    def test_a_second_pair_without_its_own_completed_turn_is_refused(self):
        """The exact overstatement the owner named: one verified pair must not carry a second."""
        record = self.record(terminal=self.two_pairs(second_turn=False), operator=b'\x03\x03\x03\x03')
        self.assertFalse(record['available'])
        self.assertEqual(record['verified_pairs'], 1, 'what was actually verified is reported as one')
        self.assertEqual(record['pairs'], 2, 'and the observed count is still reported honestly')
        self.assertIn('pair 2', record['reason'])

    def test_a_second_pair_without_its_own_idle_prompt_is_refused(self):
        record = self.record(terminal=self.two_pairs(second_idle=False), operator=b'\x03\x03\x03\x03')
        self.assertFalse(record['available'])
        self.assertIn('idle prompt', record['reason'])
        self.assertIn('pair 2', record['reason'])

    def test_more_recorded_pairs_than_the_terminal_acknowledges_is_refused(self):
        record = self.record(terminal=self.ordered(), operator=b'\x03\x03\x03\x03')
        self.assertFalse(record['available'])
        self.assertEqual((record['pairs'], record['verified_pairs']), (2, 1))
        self.assertIn('must not justify more pairs', record['reason'])

    def test_the_single_pair_case_still_reports_one_verified(self):
        record = self.record(terminal=self.ordered())
        self.assertTrue(record['available'])
        self.assertEqual((record['pairs'], record['verified_pairs']), (1, 1))


class CompanionReadabilityTests(unittest.TestCase):
    """Owner precision: do not add a bound so every helper file has one, but do not leave a path where the
    recipient is handed something it cannot open.

    Measured on this goal's own history, decoding the base64 payload SHRINKS an event - 0.85 to 0.93 of its
    verbatim bytes, largest companion 69399 against the reader's 262144 - so nothing here is bounded for the
    sake of symmetry. An event that is mostly structure rather than base64 would grow under indent instead,
    and a companion the reader cannot open is the same failure the split exists to correct.
    """

    def test_a_companion_that_would_not_open_is_a_named_gap_rather_than_a_file(self):
        """Driven by lowering the reader bound rather than by guessing a fixture big enough to cross it.

        A first version guessed the size and the event never reached the branch at all, which is how a test
        can look like it covers something it never ran.
        """
        from runtime import development_final
        source = history({'office-ap11': (4, 100)})
        source['office-ap11'].insert(1, event(77, 'x' * 30000))
        with patch.object(development_final, 'READ_BOUND', 8000):
            files = development_final.history_parts(source, ROOM)
        entry = json.loads(files['NATIVE_HISTORY_INDEX.json'])['workflows']['office-ap11']
        named = [line for part in entry['parts'] for line in part.get('unreadable_lines', [])
                 if line['event_id'] == '77']
        self.assertEqual(len(named), 1, 'the event is named')
        record = named[0]
        self.assertIsNone(record['readable_copy'], 'no companion was written')
        self.assertGreater(record['readable_copy_bytes'], 8000)
        self.assertIn('none was written', record['note'])
        self.assertEqual([n for n in files if n.startswith('NATIVE_HISTORY_EVENT_')], [],
                         'nothing the reader could not open was delivered')
        delivered = [e for part in entry['parts'] for e in json.loads(files[part['file']])]
        self.assertIn('77', [e['eventId'] for e in delivered], 'the verbatim event is delivered anyway')

    def test_at_the_real_bound_that_same_event_does_get_its_companion(self):
        """So the gap above is the bound doing its work, not the event being undeliverable."""
        from runtime.development_final import READ_BOUND
        source = history({'office-ap11': (4, 100)})
        source['office-ap11'].insert(1, event(77, 'x' * 30000))
        files = history_parts(source, ROOM)
        entry = json.loads(files['NATIVE_HISTORY_INDEX.json'])['workflows']['office-ap11']
        named = [line for part in entry['parts'] for line in part.get('unreadable_lines', [])
                 if line['event_id'] == '77'][0]
        self.assertIsNotNone(named['readable_copy'])
        self.assertLessEqual(len(files[named['readable_copy']]), READ_BOUND)

    def test_every_companion_actually_written_is_within_the_readers_bound(self):
        from runtime.development_final import READ_BOUND
        source = history({'office-ap11': (6, 100)})
        source['office-ap11'].insert(2, event(88, 'x' * 60000))
        files = history_parts(source, ROOM)
        companions = [name for name in files if name.startswith('NATIVE_HISTORY_EVENT_')]
        self.assertTrue(companions, 'this fixture really does produce a companion')
        for name in companions:
            self.assertLessEqual(len(files[name]), READ_BOUND, name)


if __name__ == '__main__':
    unittest.main()
