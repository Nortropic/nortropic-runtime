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
            seen.extend(json.loads(files[part['file']])['events'])
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
        part = json.loads(files['NATIVE_HISTORY_office-ap11_1.json'])
        self.assertEqual(set(part), {'workflow', 'part', 'of', 'first_event_id', 'last_event_id', 'events'})
        self.assertTrue(all(set(e) == {'eventId', 'eventTime', 'eventType', 'attributes'} for e in part['events']),
                        'whole events, not reduced ones')

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
        delivered = [e for p in entry['parts'] for e in json.loads(files[p['file']])['events']]
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
        delivered = [int(e['eventId']) for p in entry['parts'] for e in json.loads(files[p['file']])['events']]
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
                last = json.loads(files[entry['parts'][-1]['file']])['events'][-1]
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
        last = json.loads(files[parent['parts'][-1]['file']])['events'][-1]
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
                    events = json.loads(files[part['file']])['events']
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


if __name__ == '__main__':
    unittest.main()
