"""A failed schema attempt can recover only as two bounded, separately checked text calls."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from runtime import critique_format as form, web_critique as critique, web_common as common
from runtime.claude_profile import VERSION, MODEL


class FormatRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.schema = form.object_schema({
            'verdict': {'type': 'string', 'enum': ['approved', 'rejected']},
            'summary': {'type': 'string', 'maxLength': 60},
            'blocking_findings': {'type': 'array', 'maxItems': 30, 'items': {'type': 'string', 'maxLength': 800}},
            'risk': {'type': 'string', 'maxLength': 100},
            'binding': form.object_schema({'candidate': {'type': 'string', 'enum': ['fixed-candidate']}}),
            'seen_files': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string', 'enum': ['VYER/a.png']}}})
        self.original = {'verdict': 'rejected', 'summary': 'A long explanation of the unchanged scope and uncertainties. ' * 2,
                         'blocking_findings': ['A real blocker'], 'risk': 'Unverified by real users',
                         'binding': {'candidate': 'fixed-candidate'}, 'seen_files': ['VYER/a.png']}
        self.events = [
            {'type': 'system', 'subtype': 'init', 'session_id': 'source-session', 'claude_code_version': VERSION,
             'model': MODEL, 'tools': ['Read', 'StructuredOutput'], 'mcp_servers': [], 'plugins': [],
             'slash_commands': [], 'apiKeySource': 'none'},
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'id': 'read1', 'name': 'Read', 'input': {'file_path': '/original/VYER/a.png'}}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'read1',
                                                       'content': [{'type': 'image', 'source': {'type': 'base64', 'data': 'x'}}]}]}},
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'StructuredOutput',
                                                          'id': 'output1', 'input': self.original}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'output1',
                    'is_error': True, 'content': 'Output does not match required schema: /summary: too long'}]}}]

    def extract(self, events=None, original=None):
        events = copy.deepcopy(self.events if events is None else events)
        if original is not None:
            events[3]['message']['content'][0]['input'] = original
        return form.original_answer(events, MODEL, Path('/original'), ['VYER/a.png'], self.schema, ['summary'])

    def test_full_draft_is_not_a_terminal_but_is_eligible_for_form_recovery(self):
        self.assertIsNone(critique.claude_answer(self.events, MODEL, Path('/original'))[0])
        answer, fields, seen = self.extract()
        self.assertEqual((answer, fields, seen), (self.original, ['summary'], ['VYER/a.png']))

    def test_all_other_bounds_and_structure_are_enforced_before_native_calls(self):
        for change in ({'risk': 'x' * 101}, {'blocking_findings': ['x'] * 31}, {'binding': {'candidate': 'wrong'}},
                       {'seen_files': ['invented.png']}, {'verdict': 'other'}, {'summary': None}):
            original = {**self.original, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.extract(original=original)
        original = copy.deepcopy(self.original)
        del original['risk']
        with self.assertRaises(ValueError):
            self.extract(original=original)

    def test_incomplete_ambiguous_or_unqualified_output_and_missing_images_refuse(self):
        for mutation in ('missing_output', 'duplicate', 'image_error', 'no_image_result', 'no_schema_error', 'wrong_model', 'terminal'):
            events = copy.deepcopy(self.events)
            if mutation == 'missing_output': events.pop(3)
            elif mutation == 'duplicate': events.append(copy.deepcopy(events[3]))
            elif mutation == 'image_error': events[2]['message']['content'][0]['is_error'] = True
            elif mutation == 'no_image_result': events[2]['message']['content'][0]['content'] = 'not an image'
            elif mutation == 'no_schema_error': events[-1]['message']['content'][0]['is_error'] = False
            elif mutation == 'wrong_model': events[0]['model'] = 'unselected-model'
            else: events.append({'type': 'result', 'is_error': True})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.extract(events)

    def test_patch_cannot_change_verdict_blockers_risk_binding_or_evidence(self):
        replacement = {'summary': 'Same scope and uncertainty.'}
        answer = form.apply_patch(self.original, replacement, self.schema, ['summary'])
        self.assertEqual({k: v for k, v in answer.items() if k != 'summary'},
                         {k: v for k, v in self.original.items() if k != 'summary'})
        for name in ('verdict', 'blocking_findings', 'risk', 'binding', 'seen_files'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                form.apply_patch(self.original, {**replacement, name: []}, self.schema, ['summary'])
        with self.assertRaises(ValueError): form.apply_patch(self.original, {'summary': 'x' * 61}, self.schema, ['summary'])

    def source(self):
        source = self.root / 'old'
        workspace = source / 'arbetsyta'
        (workspace / 'VYER').mkdir(parents=True)
        image = workspace / 'VYER/a.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\noriginal image')
        (workspace / 'AGENTS.md').write_text('original reader')
        (workspace / 'FILES.md').write_text(critique.file_listing([{'place': 'VYER/a.png',
            'sha256': common.sha256_file(image), 'bytes': image.stat().st_size, 'what': 'original image'}]))
        question = 'Fixed scope and criteria'
        schema_text = json.dumps(self.schema)
        (source / 'schema.json').write_text(schema_text)
        (source / 'fraga.txt').write_text(critique.PREAMBLE.format(question=question))
        (source / 'start.json').write_text(json.dumps({'cwd': '/original', 'argv': ['qualified']}))
        (source / 'strom.jsonl').write_text('\n'.join(json.dumps(e) for e in self.events) + '\n')
        receipt = {'profile': 'kritik', 'outcome': 'inget_svar',
                   'parameters': {'executor': 'claude', 'model': MODEL, 'label': 'old'},
                   'session': {'end': 'tidsgrans', 'valid_terminal': False, 'seconds': 600, 'usage': None},
                   'question_sha256': common.sha256_bytes(question.encode()),
                   'prompt_sha256': common.sha256_file(source / 'fraga.txt'),
                   'schema_sha256': common.sha256_bytes(schema_text.encode()),
                   'underlag': [{'place': 'VYER/a.png', 'source_sha256': common.sha256_file(image),
                                'copy_sha256': common.sha256_file(image), 'bytes': image.stat().st_size}],
                   'images': {'listed': ['VYER/a.png'], 'delivered_or_opened': ['VYER/a.png'],
                              'complete': True, 'how': 'opened with Read (from the stream)'}}
        common.write_receipt(source, receipt)
        return types.SimpleNamespace(aterhamta=str(source), modell=MODEL, utforare='claude', question=question,
                                     schema_text=schema_text, schema_value=self.schema, formfalt=['summary'],
                                     etikett='new', files=[{'plats': 'VYER/a.png', 'kalla': str(image), 'vad': 'original image'}])

    def test_source_hash_question_schema_and_current_underlag_are_bound(self):
        args = self.source()
        form.verified_source(args.aterhamta, args)
        for attribute, replacement in [('question', 'new scope'), ('schema_text', 'new schema')]:
            changed = copy.copy(args)
            setattr(changed, attribute, replacement)
            with self.subTest(attribute=attribute), self.assertRaises(ValueError): form.verified_source(args.aterhamta, changed)
        changed = copy.deepcopy(args)
        changed.files[0]['vad'] = 'a different declared source meaning'
        with self.assertRaisesRegex(ValueError, 'descriptions'):
            form.verified_source(args.aterhamta, changed)
        (Path(args.aterhamta) / 'strom.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError): form.verified_source(args.aterhamta, args)

    def test_ordinary_runtime_recovery_preserves_source_and_refuses_changed_meaning(self):
        args = self.source()
        source = Path(args.aterhamta)
        before = common.output_map(source, exclude=())
        native_session = {'valid_terminal': True, 'seconds': 1, 'usage': {'tokens': 4}, 'images': 0}
        for preserved in (True, False):
            run = self.root / ('success' if preserved else 'refused')
            run.mkdir()
            answers = [({'summary': 'Same scope and uncertainty.'}, native_session),
                       ({'preserved': preserved, 'lost_or_changed': [] if preserved else ['Lost caveat'], 'reason': 'Checked each claim'}, native_session)]
            with patch('runtime.claude_profile.require_subscription'), patch.object(common, 'new_run_directory', return_value=run), \
                    patch.object(form, 'native_text', side_effect=answers) as native:
                self.assertEqual(form.recover(args), 0 if preserved else 1)
            self.assertEqual(native.call_count, 2)
            self.assertEqual(before, common.output_map(source, exclude=()))
            receipt = json.loads((run / 'KVITTO.json').read_text())
            self.assertFalse(receipt['session']['valid_terminal'])
            self.assertEqual(receipt['format_recovery']['images_reopened'], 0)
            self.assertEqual((run / 'svar.json').exists(), preserved)
            self.assertEqual(json.loads((run / 'original-svar.json').read_text()), self.original)

    def test_explicit_recovery_is_dispatched_by_the_ordinary_profile(self):
        args = self.source()
        with patch.object(critique, 'parse', return_value=args), patch.object(form, 'recover', return_value=7) as recover:
            self.assertEqual(critique.run([]), 7)
            recover.assert_called_once_with(args)

    def test_constraint_inventory_covers_nested_fields_and_invalid_schema_is_cheaply_refused(self):
        self.assertIn('$.blocking_findings[]: {"maxLength": 800}', form.limits(self.schema))
        for bound in (-1, '60', True):
            schema = copy.deepcopy(self.schema)
            schema['properties']['summary']['maxLength'] = bound
            with self.assertRaises(ValueError): critique.check_schema(schema)

    def test_text_disguised_as_image_is_refused_before_a_model_can_start(self):
        source = self.root / 'fake.png'
        source.write_text('not an image')
        with self.assertRaisesRegex(ValueError, 'Image bytes'):
            critique.build_workspace([{'kalla': str(source), 'plats': 'VYER/a.png', 'vad': 'required image'}],
                                     'claude', self.root)


if __name__ == '__main__':
    unittest.main()
