import json
from pathlib import Path
import tempfile
import unittest

from probe_bridge import restrict_message
from probe_hook import INPUT, verify


class ProbeTest(unittest.TestCase):
    def test_wrong_missing_and_legitimate_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'input.csv').write_text(INPUT)
            self.assertFalse(verify(p)['passed'])
            (p / 'result.json').write_text('{"count":3,"sum":999}')
            self.assertFalse(verify(p)['passed'])
            (p / 'result.json').write_text('{"count":3,"sum":10}')
            self.assertTrue(verify(p)['passed'])
            (p / 'input.csv').write_text('tampered')
            self.assertFalse(verify(p)['passed'])

    def test_host_tracker_tools_and_wide_sandbox_removed(self):
        p = Path('/isolated/fixture')
        message = restrict_message({'method': 'thread/start', 'params': {
            'dynamicTools': [{'name': 'github_api'}], 'sandbox': 'danger-full-access',
            'approvalPolicy': 'never'}}, p)
        self.assertEqual(message['params']['dynamicTools'], [])
        self.assertEqual(message['params']['sandbox'], 'workspace-write')
        message = restrict_message({'method': 'turn/start', 'params': {
            'sandboxPolicy': {'type': 'dangerFullAccess'}}}, p)
        policy = message['params']['sandboxPolicy']
        self.assertEqual(policy['writableRoots'], [str(p)])
        self.assertFalse(policy['networkAccess'])


if __name__ == '__main__':
    unittest.main()
