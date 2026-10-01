"""F-107 G2: default, no-model sentinel test of the actual Codex review sandbox.

This establishes the Codex filesystem boundary only. Claude's tool boundary
still needs its provider qualification; a command-shape assertion is not that proof.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from runtime.profile import ROOT, sandbox_command, environment


class ReviewIsolationTests(unittest.TestCase):
    def test_second_reader_cannot_read_first_review_or_write_candidate(self):
        # The source snapshot is read-only; .scratch resolves to test-owned storage.
        with tempfile.TemporaryDirectory(dir=ROOT/'.scratch',prefix='review-isolation-') as directory:
            root=Path(directory).resolve()
            first=root/'first-review';first.mkdir()
            sentinel=first/'decision.json';sentinel.write_text('synthetic-first-reader-verdict')
            workspace=root/'second-review';workspace.mkdir()
            (workspace/'.scratch').mkdir()
            inside=workspace/'candidate.txt';inside.write_text('candidate-input')
            (workspace/'shortcut').symlink_to(sentinel)
            script="""import json
from pathlib import Path
observed=[]
for path in [OUTSIDE,'shortcut']:
 try: Path(path).read_bytes();observed.append(False)
 except PermissionError: observed.append(True)
try: Path('candidate.txt').write_text('changed');observed.append(False)
except PermissionError: observed.append(True)
observed.append(Path('candidate.txt').read_text()=='candidate-input')
Path('.scratch/note').write_text('scratch-only')
observed.append(Path('.scratch/note').read_text()=='scratch-only')
print(json.dumps(observed))
""".replace('OUTSIDE',repr(str(sentinel)))
            result=subprocess.run(sandbox_command(workspace,['/opt/homebrew/bin/python3.12','-I','-B','-c',script]),
                                  cwd=workspace,env=environment(),capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),[True]*5)
            self.assertEqual(sentinel.read_text(),'synthetic-first-reader-verdict')
            self.assertEqual(inside.read_text(),'candidate-input')
