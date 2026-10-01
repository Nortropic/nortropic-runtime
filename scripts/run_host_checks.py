"""Mandatory preserved-host checks with a permanent attempt before any test import.

The private ledger keeps failures and interrupted attempts even if a receipt is
lost. A diagnostic cannot qualify publication. The output is exclusive and the
publisher binds the receipt to the recorded attempt and exact source bytes.

usage: NR_HOST_ROOT=<preserved host> python -B scripts/run_host_checks.py OUTPUT
       [--diagnostik-av FAILED_RUN]
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE = 'scripts.hostcheck_preserved_state'
BOUND = ('scripts/hostcheck_preserved_state.py', 'scripts/test_final_evidence.py')


def git(*arguments):
    return subprocess.run(['git', '--no-replace-objects', *arguments], capture_output=True, text=True, check=True).stdout.strip()


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
        self.current = None
        self.started = None

    def startTest(self, test):
        super().startTest(test)
        self.current = {'name': test.id(), 'file': None, 'seconds': None, 'status': 'unknown'}
        self.cases.append(self.current)
        self.started = time.monotonic()

    def status(self, test, value):
        if self.current is None or self.current['name'] != test.id():
            self.cases.append({'name': test.id(), 'file': None, 'seconds': None, 'status': value})
        else:
            self.current['status'] = value

    def addSuccess(self, test):
        super().addSuccess(test)
        self.status(test, 'success')

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.status(test, 'failure')

    def addError(self, test, error):
        super().addError(test, error)
        self.status(test, 'error')

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.status(test, 'skipped')

    def addExpectedFailure(self, test, error):
        super().addExpectedFailure(test, error)
        self.status(test, 'failure')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.status(test, 'failure')

    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        if error is not None:
            self.status(test, 'failure')

    def stopTest(self, test):
        if self.current is not None:
            self.current['seconds'] = time.monotonic() - self.started
        super().stopTest(test)
        self.current = None


def main(destination, diagnostic_of=None):
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    if not os.environ.get('NR_HOST_ROOT'):
        raise SystemExit('REFUSED: NR_HOST_ROOT must name the checkout that holds the preserved application')
    from runtime.failure_ledger import Ledger, digest, host_binding
    from runtime.measurement_observer import private_output
    book = Ledger()
    candidate = git('-C', str(root), 'rev-parse', 'HEAD')
    if diagnostic_of is None:
        book.require_publishable(candidate)
    scope = Path(os.environ['NR_HOST_ROOT']).resolve() / '.runtime/ap11/application'
    head = json.loads((scope / 'head.json').read_text()) if (scope / 'head.json').is_file() else None
    receipt = {
        'candidate': candidate, 'module': MODULE,
        'clean_tree': git('-C', str(root), 'status', '--porcelain') == '',
        'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in BOUND},
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'host_root': os.environ['NR_HOST_ROOT'], 'scope': str(scope), 'journal_head': head,
    }
    # A bad destination fails before any preserved-host test can run.
    with private_output(Path(destination).absolute()) as output:
        identifier = book.begin(candidate, 'diagnostic' if diagnostic_of else 'host',
                                host_binding(receipt), diagnostic_of=diagnostic_of)
        stream = io.StringIO()
        captured = []
        def result_factory(*args, **kwargs):
            result = TimedResult(*args, **kwargs)
            captured.append(result)
            return result
        runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=result_factory)
        try:
            result = runner.run(unittest.defaultTestLoader.loadTestsFromName(MODULE))
            complete = (result.testsRun > 0 and len(result.cases) == result.testsRun
                        and all(c['seconds'] is not None and c['status'] != 'unknown' for c in result.cases))
            successful = result.wasSuccessful() and not result.skipped and complete
            end = book.finish(identifier, result.cases, 0 if successful else 1, complete=complete)
        except BaseException:
            book.finish(identifier, captured[0].cases if captured else [], 1, complete=False)
            raise
        imported = {name: str(Path(module.__file__).resolve()) for name, module in sorted(sys.modules.items())
                    if (name in ('runtime', 'scripts') or name.startswith(('runtime.', 'scripts.')))
                    and getattr(module, '__file__', None)}
        receipt.update(observed_at=datetime.now(timezone.utc).isoformat(), imported=imported,
                       run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                       skipped=len(result.skipped), successful=end['passed'], cases=end['cases'],
                       ledger_run=identifier, ledger_finish_sha256=digest(end),
                       verbatim=[line for line in stream.getvalue().splitlines() if line.strip()])
        try:
            output.write((json.dumps(receipt, indent=1) + '\n').encode()); output.flush(); os.fsync(output.fileno())
        except BaseException:
            lost = book.begin(candidate, 'host', digest({'lost_receipt_for': identifier}))
            book.finish(lost, [], 1, complete=False)
            raise
    print(json.dumps({k: receipt[k] for k in ('candidate', 'run', 'failures', 'errors', 'skipped', 'successful', 'ledger_run')}, indent=1))
    return 0 if receipt['successful'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination')
    parser.add_argument('--diagnostik-av')
    args = parser.parse_args()
    raise SystemExit(main(args.destination, args.diagnostik_av))
