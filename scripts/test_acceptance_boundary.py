"""Regression for the review-discovered privileged host write and snapshot mutation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance.run_report_phase1 import verify
from runtime.profile import ROOT, sandbox_command, environment


class AcceptanceBoundaryTest(unittest.TestCase):
    def test_stdin_does_not_follow_candidate_symlink(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime', prefix='acceptance-regression-') as directory:
            root=Path(directory); candidate=root/'candidate'
            (candidate/'tools').mkdir(parents=True); (candidate/'.scratch').mkdir()
            outside=root/'host-canary'; outside.write_text('unchanged')
            (candidate/'.scratch/sample.jsonl').symlink_to(outside)
            # A fixture exercises CLI stdin; it is intentionally not a passing parser.
            (candidate/'tools/run_report.py').write_text('''import json,sys

def summarize(provider, lines):
    return {'provider': provider, 'status': 'incomplete', 'usage': None}

if __name__ == '__main__':
    value=json.loads(sys.stdin.read())
    print(json.dumps({'provider':'codex','status':'completed','usage':value['usage']}))
''')
            result=verify(candidate)
            self.assertFalse(result['passed'])
            self.assertTrue(result['observations'][-1]['passed'])
            self.assertEqual(outside.read_text(),'unchanged')
            r=subprocess.run(sandbox_command(candidate,['/opt/homebrew/bin/python3.12','-c',
                "from pathlib import Path; Path('tools/run_report.py').write_text('changed')"]),
                env=environment(),capture_output=True,text=True,timeout=10)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('PermissionError',r.stderr)
