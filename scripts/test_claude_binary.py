"""The qualified Claude CLI comes from the host's own copy, never from whatever PATH resolves to.

On 2026-09-23 the owner's global install updated itself from the qualified 2.1.257 to 2.1.280. Because
qualified_binary() resolved `claude` on PATH, that one update stopped every Runtime Claude role and turned
the published suite red. The host now keeps the qualified bytes beside its pinned Codex and Temporal
binaries; the hash check and its messages are the ones D019 established.
"""
import hashlib
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


if __name__ == '__main__':
    unittest.main()
