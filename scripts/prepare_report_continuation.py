"""Prepare the same accepted pilot's reviewed continuation after adapter integration."""
import copy
import hashlib
import json
from runtime.candidate import git
from runtime.integration import Publisher, digest
from runtime.profile import ROOT
from runtime.revision import require_revision
from runtime.task import validate


def main():
    original=json.loads((ROOT/'tasks/run-report.json').read_text())
    publisher=Publisher(ROOT);publisher.git('fetch','origin','main')
    base=publisher.git('rev-parse','origin/main');publisher.require_base(base)
    if git(ROOT,'rev-parse','HEAD')!=base or git(ROOT,'status','--porcelain'):
        raise ValueError('Start on clean integrated main before preparing the continuation')
    revised=copy.deepcopy(original);revised['steps'][1].pop('waiting_reason')
    revised.update(base=base,acceptance='acceptance/run_report_complete.py',brief='tasks/run-report-complete.md',
                   acceptance_sha256=hashlib.sha256((ROOT/'acceptance/run_report_complete.py').read_bytes()).hexdigest(),
                   continuation={'previous_task_sha256':digest(original),'expected_attempt':2,
                                 'reason':'Owner restored Claude subscription; native restricted profile qualified in D019. Preserve Codex phase, update stale base and freeze the already accepted full contract before continuation.',
                                 'evidence':'evidence/claude-qualification/verification.json'})
    validate(revised);require_revision(original,revised,1,2)
    with (ROOT/'tasks/run-report-continuation.json').open('x') as output:output.write(json.dumps(revised,indent=2)+'\n')
    print('Prepared tasks/run-report-continuation.json. Preserve and separately review this exact input before --resume --access-restored.')

if __name__=='__main__':main()
