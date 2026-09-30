"""D041: the Codex home configuration is bound without the owner's two top-level keys that every Runtime Codex run sets
itself; everything else in it stays bound, and a release staged before D041 is still checked against the whole file."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from runtime import release, profile, web_critique, web_visitor
from scripts.probe_bridge import worker_command

OWNER = '''model = "gpt-6-astra"
model_reasoning_effort = "ultra"
notify = [
    "/Applications/X.app/Contents/MacOS/X",
    "turn-ended",
]
extra = [
  [1, 2],
]
service_tier = "priority"

[desktop]
keepRemoteControlAwakeWhilePluggedIn = true

[profiles.snabb]
model = "gpt-5.5"
model_reasoning_effort = "low"
'''


class Home(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='d041-')
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        (self.home / '.codex').mkdir()
        patcher = mock.patch.dict(os.environ, {'HOME': str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = self.home / '.codex/config.toml'

    def digest(self, text):
        self.config.write_text(text)
        return release.codex_config_digest(self.config)


class OwnersChoice(Home):
    def test_the_two_top_level_keys_do_not_count(self):
        base = self.digest(OWNER)
        for text in (OWNER.replace('"ultra"', '"max"'), OWNER.replace('model = "gpt-6-astra"', 'model = "gpt-6.1-sol"'),
                     OWNER.replace('model = "gpt-6-astra"\n', '').replace('model_reasoning_effort = "ultra"\n', ''),
                     OWNER.replace('model = "gpt-6-astra"', 'model="gpt-6-astra"')):
            with self.subTest(text=text[:60]):
                self.assertEqual(self.digest(text), base)

    def test_every_other_change_counts(self):
        base = self.digest(OWNER)
        for text in (OWNER.replace('"priority"', '"flex"'),
                     OWNER.replace('"turn-ended",', '"turn-ended",\n    "extra",'),
                     OWNER.replace('model = "gpt-5.5"', 'model = "gpt-6-astra"'),          # a profile's own model
                     OWNER.replace('model_reasoning_effort = "low"', 'model_reasoning_effort = "high"'),
                     OWNER.replace('service_tier', 'model_reasoning_summary = "auto"\nservice_tier'),
                     OWNER.replace('model = "gpt-6-astra"', 'model = "gpt-6-astra" # kommentar'),
                     OWNER.replace('model = "gpt-6-astra"', "model = 'gpt-6-astra'"),
                     OWNER.replace('model = "gpt-6-astra"', 'model_provider = "annan"'),
                     '# ny rad\n' + OWNER):
            with self.subTest(text=text[:80]):
                self.assertNotEqual(self.digest(text), base)

    def test_a_key_inside_an_array_or_after_the_first_table_is_bound(self):
        inside = 'notify = [\n  "a",\nmodel = "x"\n]\n'
        self.assertNotEqual(self.digest(inside), self.digest(inside.replace('"x"', '"y"')))
        after = '[x]\nmodel = "a"\n'
        self.assertNotEqual(self.digest(after), self.digest(after.replace('"a"', '"b"')))

    def test_a_file_the_reading_cannot_be_sure_of_is_bound_whole(self):
        for text in ('notes = """\nmodel = "x"\n"""\nmodel = "a"\n', 'model = "a"\nnotes = \'\'\'rad\'\'\'\n'):
            with self.subTest(text=text):
                self.assertEqual(self.digest(text), hashlib.sha256(text.encode()).hexdigest())
                self.assertNotEqual(self.digest(text), self.digest(text.replace('model = "a"', 'model = "b"')))
        self.config.write_bytes(b'model = "a"\n\xff\n')
        self.assertEqual(release.codex_config_digest(self.config), hashlib.sha256(b'model = "a"\n\xff\n').hexdigest())


class GuardValues(Home):
    def test_the_home_configuration_is_bound_in_the_new_form_and_everything_else_as_before(self):
        self.config.write_text(OWNER)
        guards = release.instruction_guards()
        value = guards[str(self.config)]
        self.assertEqual(value, release.WITHOUT_OWN_CHOICE + release.codex_config_digest(self.config))
        self.assertEqual(release.guard_value(self.config, whole=True), hashlib.sha256(OWNER.encode()).hexdigest())
        agents = self.home / '.codex/AGENTS.md'
        agents.write_text('regler')
        self.assertEqual(release.instruction_guards()[str(agents)], hashlib.sha256(b'regler').hexdigest())
        self.config.unlink()
        self.assertIsNone(release.instruction_guards()[str(self.config)])
        self.config.symlink_to(agents)
        self.assertEqual(release.instruction_guards()[str(self.config)], 'unsafe')

    def test_a_new_release_ignores_the_owners_choice_and_nothing_else(self):
        self.config.write_text(OWNER)
        bound = release.instruction_guards()
        self.config.write_text(OWNER.replace('"ultra"', '"max"'))
        self.assertEqual(release.guard_differences(bound), {})
        self.config.write_text(OWNER.replace('"priority"', '"flex"'))
        self.assertEqual(list(release.guard_differences(bound)), [str(self.config)])

    def test_a_release_staged_before_d041_is_still_checked_whole(self):
        self.config.write_text(OWNER)
        old = dict(release.instruction_guards(), **{str(self.config): hashlib.sha256(OWNER.encode()).hexdigest()})
        self.assertEqual(release.guard_differences(old), {})
        self.config.write_text(OWNER.replace('"ultra"', '"max"'))
        difference = release.guard_differences(old)[str(self.config)]
        self.assertEqual(difference['expected'], hashlib.sha256(OWNER.encode()).hexdigest())
        self.assertEqual(difference['actual'], hashlib.sha256(OWNER.replace('"ultra"', '"max"').encode()).hexdigest())

    def test_an_absent_or_unsafe_binding_still_counts_an_appearing_file(self):
        bound = release.instruction_guards()
        self.assertIsNone(bound[str(self.config)])
        self.config.write_text(OWNER)
        self.assertIn(str(self.config), release.guard_differences(bound))

    def test_installed_reports_only_real_drift(self):
        """inspect_installation reads the guards through guard_differences, in the release's own form."""
        self.config.write_text(OWNER)
        with mock.patch.object(release, 'guard_differences', wraps=release.guard_differences) as spy:
            with tempfile.TemporaryDirectory() as root:
                root = Path(root).resolve()
                releases = root / '.runtime/ap10/releases/r'
                releases.mkdir(parents=True)
                with mock.patch.object(release, 'ROOT', root), mock.patch.object(release, 'ACTIVE', root / '.runtime/ap10/active.json'):
                    bound = release.instruction_guards()
                    config = {'host_root': str(root), 'office_root': str(root.parent / 'nortropic-projektkontor'),
                              'database': str(root / '.runtime/runtime.sqlite'), 'files': {}, 'instruction_guards': bound}
                    (releases / 'config.json').write_text(json.dumps(config))
                    digest = hashlib.sha256((releases / 'config.json').read_bytes()).hexdigest()
                    (root / '.runtime/ap10/active.json').write_text(json.dumps({'config': str(releases / 'config.json'), 'sha256': digest}))
                    self.config.write_text(OWNER.replace('"ultra"', '"max"'))
                    self.assertEqual(release.inspect_installation()['guard_differences'], {})
                    self.config.write_text(OWNER.replace('"priority"', '"flex"'))
                    with self.assertRaises(ValueError):
                        release.installed()
        self.assertTrue(spy.called)


class RuntimeSetsBothKeys(unittest.TestCase):
    """The premise of D041: every Runtime command that runs a Codex model sets both keys itself."""

    def both(self, argv):
        values = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '-c']
        return any(v.startswith('model=') for v in values) and any(v.startswith('model_reasoning_effort=') for v in values)

    def test_the_bridge_and_every_profile_that_runs_a_model(self):
        with tempfile.TemporaryDirectory() as workspace:
            workspace = Path(workspace)
            commands = {'worker default': worker_command(), 'worker chosen': worker_command('gpt-6-sol', 'ultra'),
                        'profile': profile.command(workspace, writable=False),
                        'profile chosen': profile.command(workspace, writable=False, model='gpt-6-sol', effort='low'),
                        'critique': web_critique.codex_command(workspace, 'gpt-6-astra', workspace / 's.json', workspace / 'l.txt', []),
                        'visitor': web_visitor.codex_command(workspace, 'gpt-6-astra')}
            for name, argv in commands.items():
                with self.subTest(name=name):
                    self.assertTrue(self.both(argv), argv)


if __name__ == '__main__':
    unittest.main()
