"""Stage the named AP11 extension while preserving the exact AP10 context.

No activation, process launch, schedule update, journal reset or dependency install.
The operator separately reviews the staged release and controlled transition.
"""
import argparse
import hashlib
import json
from pathlib import Path

from runtime.release import ROOT, installed, sha
from runtime.snapshot import read_regular
from runtime.development_scope import decode, digest, validate_contract
from scripts.install_ap10 import stage


def stage_development(runtime_revision, office_revision, selected):
    prior = installed()
    if prior is None or prior.get('development'):
        raise ValueError('This bounded transition requires the existing AP10-only release')
    selected = Path(selected).absolute()
    allowed = ROOT.parent/'nortropic-projektkontor/evidence/ap11/local'
    if not selected.is_relative_to(allowed) or any(p.is_symlink() for p in (selected,*selected.parents)):
        raise ValueError('Only selected private AP11 Office inputs may be staged')
    if {p.name for p in selected.iterdir()} != {'authority.md','goal.md','contract.json'}:
        raise ValueError('Select only the exact authority, overall acceptance and resource contract')
    inputs = {name:read_regular(selected,name) for name in ('authority.md','goal.md','contract.json')}
    if sum(map(len,inputs.values())) > 262144:
        raise ValueError('Selected goal inputs exceed bounded profile')
    contract = validate_contract(decode(inputs['contract.json']))
    if (contract['runtime_revision'] != runtime_revision or contract['office_revision'] != office_revision
            or contract['authority_sha256'] != hashlib.sha256(inputs['authority.md']).hexdigest()
            or contract['acceptance_sha256'] != hashlib.sha256(inputs['goal.md']).hexdigest()):
        raise ValueError('Goal, authority and selected revisions must match the contract')
    path = stage(runtime_revision,office_revision)
    value = decode(path.read_bytes())
    for name, expected in prior['files'].items():
        if not name.startswith('context/'):
            continue
        content = read_regular(Path(prior['directory']),name)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('AP10 context changed during staging')
        dest = path.parent/name; dest.parent.mkdir(exist_ok=True,mode=0o700)
        dest.write_bytes(content); dest.chmod(0o400); value['files'][name]=expected
    if not any(n.startswith('context/') for n in value['files']):
        raise ValueError('Existing AP10 selected context missing')
    for name, content in inputs.items():
        dest = path.parent/'development-context'/name; dest.parent.mkdir(exist_ok=True,mode=0o700)
        dest.write_bytes(content); dest.chmod(0o400); value['files']['development-context/'+name]=sha(dest)
    value['development']={'id':'office-ap11','contract_sha256':digest(contract),
                          'capacity_trial':'ap11-capacity-watch'}
    path.chmod(0o600); path.write_text(json.dumps(value,indent=2)+'\n'); path.chmod(0o400)
    return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--office',required=True);p.add_argument('--selected',required=True)
    a=p.parse_args();print(stage_development(a.runtime,a.office,a.selected))
