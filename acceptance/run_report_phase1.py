"""Host-owned behavioral assertions. Candidate runs only in a child sandbox."""
import json
from pathlib import Path
import subprocess

from runtime.profile import sandbox_command, environment


def verify(workspace):
    observations = []
    usage = {'input_tokens': 101, 'cached_input_tokens': 53, 'output_tokens': 7}
    done = {'type': 'turn.completed', 'usage': usage}
    cases = [
        ([done], 'completed', usage), ([], 'incomplete', None),
        ([{'type': 'thread.started'}], 'incomplete', None),
        ([{'type': 'turn.failed'}], 'failed', None),
        ([{'type': 'error'}, done], 'failed', usage),
        ([{'type': 'item.completed', 'item': {'status': 'failed'}}, done], 'failed', usage),
        ([done, done], 'invalid', None),
        ([{'type': 'turn.completed'}], 'completed', None),
    ]
    inputs = [([json.dumps(e) for e in events], status, values) for events, status, values in cases]
    inputs += [([line], 'invalid', None) for line in ('[1]', '{', 'null')]
    for lines, status, values in inputs:
        code = ('import json; from tools.run_report import summarize; '
                'print(json.dumps(summarize("codex", ' + repr(lines) + ')))')
        result = subprocess.run(sandbox_command(workspace, ['/opt/homebrew/bin/python3.12', '-B', '-c', code]),
                                env=environment(), text=True, capture_output=True, timeout=10)
        try:
            actual = json.loads(result.stdout)
        except ValueError:
            actual = None
        # Invalid streams need no particular usage representation; status must fail closed.
        passed = (result.returncode == 0 and isinstance(actual, dict) and
                  actual.get('provider') == 'codex' and actual.get('status') == status and
                  (status == 'invalid' or actual.get('usage') == values))
        observations.append({'input': lines, 'expected_status': status, 'passed': passed,
                             'returncode': result.returncode, 'actual': actual, 'stderr': result.stderr})
    path = Path(workspace) / '.scratch/sample.jsonl'
    path.write_text(json.dumps(done) + '\n')
    result = subprocess.run(sandbox_command(workspace, ['/opt/homebrew/bin/python3.12', '-B',
                            'tools/run_report.py', '--provider', 'codex', str(path)]),
                            env=environment(), text=True, capture_output=True, timeout=10)
    try:
        actual = json.loads(result.stdout)
    except ValueError:
        actual = None
    observations.append({'case': 'CLI', 'passed': result.returncode == 0 and actual ==
                         {'provider': 'codex', 'status': 'completed', 'usage': usage},
                         'actual': actual, 'returncode': result.returncode, 'stderr': result.stderr})
    return {'passed': all(x['passed'] for x in observations), 'observations': observations}
