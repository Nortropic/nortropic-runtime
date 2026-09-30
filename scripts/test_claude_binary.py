"""The qualified Claude CLI comes from the host's own copy, never from whatever PATH resolves to.

On 2026-09-23 the owner's global install updated itself from the qualified 2.1.257 to 2.1.280. Because
qualified_binary() resolved `claude` on PATH, that one update stopped every Runtime Claude role and turned
the published suite red. The host now keeps the qualified bytes beside its pinned Codex and Temporal
binaries; the hash check and its messages are the ones D019 established.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import claude_profile, release


class HostCopyTests(unittest.TestCase):

    def host(self, root, content=b'the qualified bytes\n'):
        binary = root / '.runtime/bin' / ('claude-' + claude_profile.VERSION)
        binary.parent.mkdir(parents=True)
        binary.write_bytes(content)
        binary.chmod(0o755)
        return binary, hashlib.sha256(content).hexdigest()

    def test_the_host_copy_is_used_and_a_different_claude_on_path_is_not(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            binary, pinned = self.host(Path(root))
            other = Path(elsewhere) / 'claude'
            other.write_bytes(b'whatever the owner updated to\n')
            other.chmod(0o755)
            with patch.object(release, 'ROOT', Path(root)), patch.object(claude_profile, 'BINARY_SHA256', pinned), \
                    patch.dict(os.environ, {'PATH': elsewhere + os.pathsep + os.environ.get('PATH', '')}):
                self.assertEqual(claude_profile.qualified_binary(), str(binary))

    def test_changed_bytes_at_the_host_copy_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            _binary, pinned = self.host(Path(root))
            with patch.object(release, 'ROOT', Path(root)), \
                    patch.object(claude_profile, 'BINARY_SHA256', hashlib.sha256(b'other bytes').hexdigest()):
                with self.assertRaisesRegex(ValueError, 'binary changed; qualify the new version'):
                    claude_profile.qualified_binary()

    def test_a_missing_host_copy_is_refused_rather_than_falling_back_to_path(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            other = Path(elsewhere) / 'claude'
            other.write_bytes(b'the qualified bytes\n')
            other.chmod(0o755)
            with patch.object(release, 'ROOT', Path(root)), \
                    patch.object(claude_profile, 'BINARY_SHA256', hashlib.sha256(b'the qualified bytes\n').hexdigest()), \
                    patch.dict(os.environ, {'PATH': elsewhere + os.pathsep + os.environ.get('PATH', '')}):
                with self.assertRaisesRegex(ValueError, 'Qualified Claude CLI is unavailable'):
                    claude_profile.qualified_binary()

    def test_a_symlink_at_the_host_copy_is_refused(self):
        """A link could point at the very global install the copy exists to be independent of."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / 'claude'
            target.write_bytes(b'the qualified bytes\n')
            link = Path(root) / '.runtime/bin' / ('claude-' + claude_profile.VERSION)
            link.parent.mkdir(parents=True)
            link.symlink_to(target)
            with patch.object(release, 'ROOT', Path(root)), \
                    patch.object(claude_profile, 'BINARY_SHA256', hashlib.sha256(b'the qualified bytes\n').hexdigest()):
                with self.assertRaisesRegex(ValueError, 'Qualified Claude CLI is unavailable'):
                    claude_profile.qualified_binary()



class PinnedVersionEvidenceTests(unittest.TestCase):
    """D046: what was measured with the pinned bytes, read back from the version's own evidence directory."""

    def inits(self):
        base = Path(claude_profile.EVIDENCE)
        found = {}
        for log in sorted((base / 'qualification').glob('*/stdout.log')):
            rows = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
            found['qualification/' + log.parent.name] = next(r for r in rows if r.get('type') == 'system' and r.get('subtype') == 'init')
        for name in ('review-terminal-shape.json', 'model-binding-init-shape.json'):
            found[name] = json.loads((base / name).read_text())['init']
        return found

    def test_every_measured_start_is_the_pinned_version_without_any_plugin(self):
        inits = self.inits()
        self.assertEqual(sorted(inits), ['model-binding-init-shape.json', 'qualification/boundary', 'qualification/boundary-direct',
                                         'qualification/explicit-root', 'qualification/explicit-subdir', 'review-terminal-shape.json'])
        for name, init in inits.items():
            with self.subTest(name=name):
                self.assertEqual(init['claude_code_version'], claude_profile.VERSION)
                self.assertEqual(init['plugins'], [])
                self.assertEqual(init['mcp_servers'], [])
                self.assertEqual(init['apiKeySource'], 'none')

    def test_the_profile_turns_off_the_built_in_plugins_the_pinned_version_starts(self):
        """Measured before the profile turned them off: every start listed the two built-ins (fynd-inbyggda-plugins)."""
        self.assertEqual(claude_profile.SETTINGS['enabledPlugins'], claude_profile.PLUGINS_OFF)
        self.assertEqual({k for k, v in claude_profile.PLUGINS_OFF.items() if v is False}, set(claude_profile.PLUGINS_OFF))
        finding = Path(claude_profile.EVIDENCE) / 'fynd-inbyggda-plugins/qualification'
        started = set()
        for log in finding.glob('*/stdout.log'):
            rows = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
            init = next(r for r in rows if r.get('type') == 'system' and r.get('subtype') == 'init')
            started |= {plugin['source'] for plugin in init['plugins']}
        self.assertTrue(started)
        self.assertLessEqual(started, set(claude_profile.PLUGINS_OFF))

    def test_the_qualification_record_names_the_pinned_bytes(self):
        record = json.loads((Path(claude_profile.EVIDENCE) / 'qualification/verification.json').read_text())
        self.assertTrue(record['passed'])
        self.assertEqual((record['version'], record['binary_sha256']), (claude_profile.VERSION, claude_profile.BINARY_SHA256))
        self.assertEqual(sorted(record['runs']), ['boundary', 'boundary-direct', 'explicit-root', 'explicit-subdir'])


if __name__ == '__main__':
    unittest.main()
