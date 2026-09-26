"""Run the web profiles' host checks and write a receipt bound to what actually ran (D034).

The receipt is bound to the commit, to the bytes of every file the checks exercise, to where the interpreter
actually imported the exercised code from, and to the tool identities (Chrome, Node, the pinned tool copy, the
detector engine). A green run of the published suite says nothing about these checks; this receipt does.

usage:  <runtime venv python> -B scripts/run_web_host_checks.py <output path>
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from datetime import datetime, timezone

MODULE = 'scripts.hostcheck_web_profiles'
BOUND = ('scripts/hostcheck_web_profiles.py', 'runtime/web_common.py', 'runtime/web_measure.py',
         'runtime/web_critique.py', 'runtime/web_visitor.py', 'runtime/web_visitor_guard.py', 'runtime/web_boundary.py',
         'runtime/web/measure.mjs', 'runtime/web/holder.mjs', 'runtime/web/handling.cjs', 'runtime/web/grammar.mjs',
         'runtime/web/grammar.json', 'config/web-tools.lock.json')


def git(root, *arguments):
    return subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True, check=True).stdout.strip()


def main(destination):
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    destination = Path(destination).resolve()
    if destination.exists():
        raise SystemExit('REFUSED: the receipt path exists; every run writes a new receipt')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName(MODULE))
    from runtime import web_common as common
    imported = {name: str(Path(module.__file__).resolve()) for name, module in sorted(sys.modules.items())
                if (name in ('runtime', 'scripts') or name.startswith(('runtime.', 'scripts.')))
                and getattr(module, '__file__', None)}
    receipt = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'module': MODULE,
        'candidate': git(root, 'rev-parse', 'HEAD'),
        'clean_tree': git(root, 'status', '--porcelain') == '',
        'source_sha256': {name: common.sha256_file(root / name) for name in BOUND},
        'imported': imported,
        'tools': common.tool_identity(with_impeccable=True),
        'run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
        'log': stream.getvalue(),
    }
    with open(destination, 'x') as out:
        json.dump(receipt, out, indent=1, ensure_ascii=False)
        out.write('\n')
    print(json.dumps({k: receipt[k] for k in ('candidate', 'clean_tree', 'run', 'failures', 'errors', 'skipped',
                                              'successful')}))
    return 0 if receipt['successful'] and not receipt['skipped'] else 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: run_web_host_checks.py <output path>')
    sys.exit(main(sys.argv[1]))
