"""Report guard drift without reading out private settings or enabling execution."""
import json
from pathlib import Path
import subprocess
from runtime import codex_pin
from runtime.release import ROOT, inspect_installation


def inspect():
    value = inspect_installation()
    if value is None:
        return {'installed': False}
    versions = {}
    for name, binary in (('codex-' + codex_pin.VERSION, ROOT / codex_pin.BINARY),):
        run = subprocess.run([str(binary), '--version'], capture_output=True,
                             text=True, timeout=10, check=True)
        versions[name] = run.stdout.strip()
    return {'installed': True, 'config_sha256': value['config_sha256'],
            'runtime_revision': value['runtime_revision'], 'office_revision': value['office_revision'],
            'guard_differences': value['guard_differences'], 'bound_files': len(value['files']),
            'versions': versions,
            'execution_available': not value['guard_differences'],
            'meaning': 'Verified release bytes and current guard hashes only; never a guard rebind or activation'}


if __name__ == '__main__': print(json.dumps(inspect(), indent=2))
