"""Delegate only an exact sealed task to the separately adopted host process."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from .release import ROOT
from .integration import GateClosed, check_binding, digest


def issue(task, subject, review):
    identifier = task.get('id')
    candidate = subject.get('candidate')
    if (not isinstance(identifier, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}', identifier)
            or not isinstance(candidate, str) or not re.fullmatch('[0-9a-f]{40}', candidate)):
        raise GateClosed('Invalid host publication identity')
    expected = check_binding(task, subject, review)
    launcher = ROOT / '.runtime/ap11/check-issuer/launch.py'
    try:
        def private(path):
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError('Unsafe host launcher path')
            info = path.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)):
                raise ValueError('Host launcher is not a private owner file')
            return path.read_bytes()
        adoption = json.loads(private(launcher.with_name('launcher-adoption.json')))
        if (adoption.get('schema') != 'nortropic-launcher-adoption/1'
                or adoption.get('launcher_sha256') != hashlib.sha256(private(launcher)).hexdigest()
                or adoption.get('verdict') != 'approved' or adoption.get('blocking_findings') != []
                or not adoption.get('reviewer_run') or not adoption.get('implementation_run')
                or adoption['reviewer_run'] == adoption['implementation_run']):
            raise ValueError('Launcher adoption differs')
        result = subprocess.run([str(ROOT / '.runtime/temporal-venv/bin/python'), '-I', '-B',
                                 str(launcher), 'issue', '--task', identifier,
                                 '--candidate', candidate, '--binding', expected],
                                cwd=ROOT, env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin'},
                                capture_output=True, timeout=4200)
        receipt = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        receipt = None
    if (not isinstance(receipt, dict) or receipt.get('schema') != 'nortropic-issued-checks/1'
            or receipt.get('candidate') != candidate or receipt.get('binding') != expected
            or receipt.get('task_sha256') != digest(task)
            or receipt.get('acceptance_sha256') != task.get('acceptance_sha256')
            or type(receipt.get('app_id')) is not int or receipt['app_id'] <= 0
            or not isinstance(receipt.get('checks'), dict)
            or set(receipt['checks']) != {'runtime/tests', 'runtime/review'}
            or any(not isinstance(check, dict) or type(check.get('id')) is not int or check['id'] <= 0
                   or type(check.get('app_id')) is not int
                   or check.get('app_id') != receipt['app_id'] for check in receipt['checks'].values())):
        raise GateClosed('Host issuer refused or returned another task/candidate binding')
    return receipt
