"""Selected Codex invocation: native filesystem boundary; no publication tools."""
import json
import os
from pathlib import Path

from scripts.probe_bridge import ROOT, worker_command
from .claude_profile import MODEL_NAME
from .release import require_workspace_instructions

# The Codex startup chain's ACTUAL specified model and reasoning effort, as worker_command() builds
# them - not a presumed CLI default. Recorded here so a model choice has a real baseline to start
# from; test_model_binding asserts these against worker_command() itself, so drift on either side
# fails a test instead of silently changing which model runs. A release choice replaces the model
# only (D028); the reasoning effort stays pinned and is not part of the choice.
MODEL = 'gpt-6-astra'
REASONING_EFFORT = 'high'


def selected_model(model=None):
    """The release's explicit Codex model, or the recorded baseline when none is bound.

    The same plain-model-id rule as the Claude profile, applied here before the name can reach an
    argument list, so a padded, flag-like or NUL-bearing name refuses in the caller's preflight.
    """
    chosen = MODEL if model is None else model
    if not isinstance(chosen, str) or not MODEL_NAME.match(chosen):
        raise ValueError('Codex profile needs a plain model name')
    return chosen


def permissions(workspace, writable=True, allowed_paths=None):
    workspace = Path(workspace).resolve()
    # Candidate code is writable; context, Git metadata and host are not.
    filesystem = {':minimal': 'read', '/opt/homebrew': 'read',
                  str(ROOT / 'AGENTS.md'): 'read',
                  str(workspace): 'read', str(workspace / 'tools'): 'write' if writable and allowed_paths is None else 'read',
                  str(workspace / '.scratch'): 'write'}
    if writable and allowed_paths is not None:
        for name in allowed_paths:
            filesystem[str(workspace / name)] = 'write'
    for ancestor in workspace.parents:
        for name in ('AGENTS.md', 'AGENTS.override.md'):
            filesystem[str(ancestor / name)] = 'read'
    table = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in filesystem.items()) + '}'
    return ['-c', 'permissions.nr.filesystem=' + table,
            '-c', 'permissions.nr.network.enabled=false',
            '-c', 'default_permissions="nr"']


def command(workspace, writable=True, allowed_paths=None, model=None):
    chosen = selected_model(model)
    if os.environ.get('NR_CONFIG_SHA256'):
        require_workspace_instructions(workspace)
    shell_env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                 'TMPDIR': str(Path(workspace).resolve() / '.scratch')}
    env_table = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in shell_env.items()) + '}'
    return worker_command(chosen)[:-1] + permissions(workspace, writable=writable, allowed_paths=allowed_paths) + [
        '-c', 'web_search="disabled"',
        '-c', 'shell_environment_policy.inherit="none"',
        '-c', 'shell_environment_policy.set=' + env_table,
        'exec', '--json', '--ephemeral', '-C', str(workspace), '-']


def environment():
    # Auth remains CLI/keychain ChatGPT; no API keys or publishing token inherited.
    return {key: value for key, value in os.environ.items()
            if key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR')}


def sandbox_command(workspace, argv, writable=False, allowed_paths=None):
    return [str(ROOT / '.runtime/bin/codex-0.155.1'), 'sandbox',
            *permissions(workspace, writable=writable, allowed_paths=allowed_paths), '-P', 'nr', '-C', str(workspace), *argv]
