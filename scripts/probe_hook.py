#!/usr/bin/env python3
"""Host-side fixture lifecycle hooks; no candidate code is executed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INPUT = 'name,value\nalpha,7\nbeta,-2\ngamma,5\n'
EXPECTED = {'count': 3, 'sum': 10}
INSTRUCTIONS = (
    'This isolated fixture accepts only the task in the Symphony prompt.\n'
    'Create result.json only; do not change input.csv or these instructions.\n'
    'No network, publication, credentials or unrelated project work.\n')


def verify(workspace):
    reasons = []
    for name, expected in (('input.csv', INPUT), ('AGENTS.md', INSTRUCTIONS)):
        path = workspace / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected.encode():
            reasons.append(name + ' missing, changed or linked')
    try:
        result = json.loads((workspace / 'result.json').read_text())
        if result != EXPECTED:
            reasons.append('incorrect result')
    except (OSError, ValueError):
        reasons.append('missing or invalid result')
    for item in workspace.iterdir():
        if item.is_symlink() or item.name not in {'AGENTS.md', 'input.csv', 'result.json'}:
            reasons.append('unexpected path: ' + item.name)
    return {'passed': not reasons, 'reasons': reasons, 'expected': EXPECTED}


def main():
    workspace = Path.cwd().resolve()
    if workspace.parent != (ROOT / '.runtime/workspaces').resolve():
        raise RuntimeError('Outside fixture workspace')
    stage = sys.argv[1]
    if stage == 'create':
        (workspace / 'input.csv').write_text(INPUT)
        (workspace / 'AGENTS.md').write_text(INSTRUCTIONS)
    elif stage == 'preserve':
        destination = ROOT / 'evidence/motor-probe' / workspace.name
        destination.mkdir(parents=True, exist_ok=True)
        result = verify(workspace)
        artifacts = destination / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        hashes = {}
        for name in ('AGENTS.md', 'input.csv', 'result.json'):
            source = workspace / name
            if source.is_file() and not source.is_symlink():
                shutil.copyfile(source, artifacts / name)
                hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        result['sha256'] = hashes
        (destination / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
        contract = json.loads((ROOT / 'config/motor-probe.json').read_text())
        if workspace.name != 'GH-' + str(contract['issue_number']):
            raise RuntimeError('Fixture issue identity mismatch')
        # First preserve, then remove only this fixture's dispatch label.
        response = subprocess.run(
            ['gh', 'api', '--method', 'DELETE', 'repos/Nortropic/nortropic-runtime/issues/'
             + str(contract['issue_number']) + '/labels/runtime%3Aprobe-b1'],
            capture_output=True, text=True, timeout=20)
        (destination / 'tracker-transition.json').write_text(json.dumps({
            'exit_code': response.returncode, 'stdout': response.stdout,
            'stderr': response.stderr, 'action': 'remove dispatch label after preservation'
        }, indent=2) + '\n')
        response.check_returncode()
        print(json.dumps(result))
    else:
        raise ValueError(stage)


if __name__ == '__main__':
    main()
