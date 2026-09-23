"""Run the mandatory host checks and write a receipt the publication can actually gate on.

Independent review found the hole this closes: the host checks are deliberately outside the pattern the
publisher discovers, so a green publication said nothing about whether they had ever run. The claim that a
clean suite does not replace them was prose, mechanised nowhere, and the receipt beside it carried no hash of
the module it claimed to have exercised and named a revision that was neither the candidate nor the base.

The receipt this writes is bound four ways: to the commit the publisher measures, to the bytes of the module
and of the file its base classes come from, to where the interpreter actually imported the exercised code
from, and to the preserved scope's own journal head. publish_construction refuses a runtime publication whose
receipt does not match the candidate it is about to publish, or that ran against any scope but its own host's.

usage:  NR_HOST_ROOT=<checkout holding the preserved application> \\
        <runtime venv python> -B scripts/run_host_checks.py <output path>
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE = 'scripts.hostcheck_preserved_state'
BOUND = ('scripts/hostcheck_preserved_state.py', 'scripts/test_final_evidence.py')


def git(*arguments):
    return subprocess.run(['git', *arguments], capture_output=True, text=True, check=True).stdout.strip()


def main(destination):
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    if not os.environ.get('NR_HOST_ROOT'):
        raise SystemExit('REFUSED: NR_HOST_ROOT must name the checkout that holds the preserved application')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName(MODULE))
    from runtime.release import ROOT
    scope = ROOT / '.runtime/ap11/application'
    head = json.loads((scope / 'head.json').read_text()) if (scope / 'head.json').is_file() else None
    # Where the exercised code was actually loaded from. The commit and the bytes say what SHOULD have run;
    # this says what the interpreter DID import, so a run that picked up another checkout's runtime or
    # scripts cannot pass as this candidate's.
    imported = {name: str(Path(module.__file__).resolve()) for name, module in sorted(sys.modules.items())
                if (name in ('runtime', 'scripts') or name.startswith(('runtime.', 'scripts.')))
                and getattr(module, '__file__', None)}
    receipt = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'module': MODULE,
        # The commit the publisher measures. A receipt for any other commit is not about this candidate.
        'candidate': git('-C', str(root), 'rev-parse', 'HEAD'),
        'clean_tree': git('-C', str(root), 'status', '--porcelain') == '',
        # The bytes actually exercised: the module, and the file its base classes come from.
        'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in BOUND},
        'imported': imported,
        # Which preserved state it ran against, by that scope's own recorded head.
        'host_root': os.environ['NR_HOST_ROOT'],
        'scope': str(scope),
        'journal_head': head,
        'run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'successful': result.wasSuccessful() and not result.skipped and result.testsRun > 0,
        'verbatim': [line for line in stream.getvalue().splitlines() if line.strip()],
    }
    Path(destination).write_text(json.dumps(receipt, indent=1) + '\n')
    print(json.dumps({k: receipt[k] for k in
                      ('candidate', 'run', 'failures', 'errors', 'skipped', 'successful')}, indent=1))
    return 0 if receipt['successful'] else 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: run_host_checks.py <output path>')
    raise SystemExit(main(sys.argv[1]))
