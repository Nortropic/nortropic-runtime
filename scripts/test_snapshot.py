import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.snapshot import read_regular, snapshot


class SnapshotTest(unittest.TestCase):
    def test_regular_and_symlink_components(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'candidate/tools').mkdir(parents=True)
            (root/'outside').write_text('nonsecret outside sentinel')
            (root/'candidate/tools/code.py').write_text('print(1)\n')
            files=snapshot(root/'candidate',root/'frozen',['tools/code.py'])
            self.assertEqual(read_regular(root/'frozen','tools/code.py'),b'print(1)\n')
            self.assertIn('tools/code.py',files)
            (root/'candidate/tools/link.py').symlink_to(root/'outside')
            with self.assertRaises(OSError): read_regular(root/'candidate','tools/link.py')
            (root/'candidate/escape').symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError): read_regular(root/'candidate','escape/outside')
            with self.assertRaises(ValueError): read_regular(root/'candidate','../outside')
            os.mkfifo(root/'candidate/tools/pipe')
            with self.assertRaises(ValueError): read_regular(root/'candidate','tools/pipe')
