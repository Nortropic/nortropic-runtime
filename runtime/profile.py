"""Selected Codex invocation: native filesystem boundary; no publication tools."""
import json
import os
from pathlib import Path

from scripts.probe_bridge import ROOT, worker_command


def permissions(workspace, writable=True):
    workspace = Path(workspace).resolve()
    # Candidate code is writable; context, Git metadata and host are not.
    filesystem = {':minimal': 'read', '/opt/homebrew': 'read',
                  str(ROOT / 'AGENTS.md'): 'read',
                  str(workspace): 'read', str(workspace / 'tools'): 'write' if writable else 'read',
                  str(workspace / '.scratch'): 'write'}
    for ancestor in workspace.parents:
        for name in ('AGENTS.md', 'AGENTS.override.md'):
            filesystem[str(ancestor / name)] = 'read'
    table = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in filesystem.items()) + '}'
    return ['-c', 'permissions.nr.filesystem=' + table,
            '-c', 'permissions.nr.network.enabled=false',
            '-c', 'default_permissions="nr"']


def command(workspace):
    return worker_command()[:-1] + permissions(workspace) + [
        '-c', 'web_search="disabled"',
        '-c', 'shell_environment_policy.inherit="none"',
        '-c', 'shell_environment_policy.set={PATH="/usr/bin:/bin:/opt/homebrew/bin"}',
        'exec', '--json', '--ephemeral', '-C', str(workspace), '-']


def environment():
    # Auth remains CLI/keychain ChatGPT; no API keys or publishing token inherited.
    return {key: value for key, value in os.environ.items()
            if key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR')}


def sandbox_command(workspace, argv, writable=False):
    return [str(ROOT / '.runtime/bin/codex-0.155.1'), 'sandbox',
            *permissions(workspace, writable=writable), '-P', 'nr', '-C', str(workspace), *argv]
