"""Host registration of accepted construction work, without a candidate-name list.

The existing publication holder owns this registry outside candidate write access.
Registration records the holder's semantic acceptance check against an authentic
source; a matching string/hash alone is explicitly NOT an authorization decision.
This module grants no publication: exact candidate, tests, separate review and
server protection remain the publication wrapper/Publisher's existing gates.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from .release import ROOT

TARGETS = {
    'office': {'target': 'Nortropic/nortropic-projektkontor', 'where': 'office', 'discover': 'tools'},
    'runtime': {'target': 'Nortropic/nortropic-runtime', 'where': 'runtime', 'discover': 'scripts'},
}


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Registration input must be a regular host file')
    return path


def digest(path):
    return sha256(regular(path).read_bytes()).hexdigest()


def name(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', value):
        raise ValueError('Plain construction id required')
    return value


def registry(host=ROOT):
    return Path(host) / '.runtime/ap11/registrations'


def register(identifier, target, source, expected_sha256, acceptance_record, host=ROOT):
    """Called by the trusted holder after inspecting the owner's actual source.

    The acceptance record is an existing reviewed host decision with explicit
    scope. It must live outside all candidate worktrees. Never infer acceptance
    from content keywords or let candidate prose create this record.
    """
    identifier = name(identifier)
    if target not in TARGETS or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Unknown publication target or source binding')
    home = registry(host); source = regular(source); accepted_path = regular(acceptance_record)
    # Only the private publication holder may issue a registration. Candidate
    # profiles cannot write this host area, measured by the boundary probes.
    authority_home = Path(host) / '.runtime/ap11/accepted'
    if accepted_path.parent != authority_home:
        raise ValueError('Acceptance must be issued in the existing private host authority area')
    accepted = json.loads(accepted_path.read_text())
    required = {'schema', 'id', 'source', 'source_sha256', 'targets', 'accepted', 'basis', 'holder'}
    if (set(accepted) != required or accepted['schema'] != 'construction-acceptance/1'
            or accepted['id'] != identifier or accepted['source'] != str(source)
            or accepted['source_sha256'] != expected_sha256 or accepted['accepted'] is not True
            or not isinstance(accepted['targets'], list) or target not in accepted['targets']
            or any(t not in TARGETS for t in accepted['targets'])
            or not all(isinstance(accepted[x], str) and accepted[x].strip() for x in ('basis', 'holder'))):
        raise ValueError('Accepted mandate does not bind this registration and target')
    if digest(source) != expected_sha256:
        raise ValueError('Owner source changed or does not match acceptance')
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(p.is_symlink() for p in (home, *home.parents)):
        raise ValueError('Unsafe host registry')
    value = {'schema': 'construction-registration/1', 'id': identifier, 'target': target,
             'source': str(source), 'source_sha256': expected_sha256,
             'acceptance_record': str(accepted_path), 'acceptance_sha256': digest(accepted_path),
             'registered_at': datetime.now(timezone.utc).isoformat()}
    path = home / (identifier + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return value


def resolve_profile(identifier, host=ROOT):
    path = regular(registry(host) / (name(identifier) + '.json'))
    if stat.S_IMODE(path.stat().st_mode) != 0o400:
        raise ValueError('Registration is not sealed read-only')
    value = json.loads(path.read_text())
    if (value.get('schema') != 'construction-registration/1' or value.get('id') != identifier
            or value.get('target') not in TARGETS
            or digest(value['source']) != value['source_sha256']
            or digest(value['acceptance_record']) != value['acceptance_sha256']):
        raise ValueError('Registration or accepted source differs')
    accepted_path = regular(value['acceptance_record'])
    if accepted_path.parent != Path(host) / '.runtime/ap11/accepted':
        raise ValueError('Acceptance outside host authority area')
    accepted = json.loads(accepted_path.read_text())
    if (accepted.get('accepted') is not True or accepted.get('id') != identifier
            or value['target'] not in accepted.get('targets', [])
            or accepted.get('source') != value['source']
            or accepted.get('source_sha256') != value['source_sha256']):
        raise ValueError('Registration is not backed by this accepted task')
    return {**TARGETS[value['target']], 'mandate_sha256': value['source_sha256'],
            'registration_sha256': digest(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id'); parser.add_argument('--target', choices=TARGETS, required=True)
    parser.add_argument('--source', type=Path, required=True); parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--acceptance-record', type=Path, required=True)
    args = parser.parse_args()
    result = register(args.id, args.target, args.source, args.source_sha256, args.acceptance_record)
    print(json.dumps({'registered': result['id'], 'target': result['target'],
                      'meaning': 'Host registration only; publication gates still required'}))


if __name__ == '__main__': main()
