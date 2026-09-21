"""Pinned AP10 code is separate from the one canonical host state directory."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('NR_HOST_ROOT', CODE_ROOT)).resolve()
ACTIVE = ROOT / '.runtime/ap10/active.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def instruction_guards():
    """Bind live native instruction/config inputs; never copy authentication data.

    A changed input causes unavailable execution, never silently new instructions.
    The snapshots remain usable after ordinary source branch changes.
    """
    parents = {ROOT, *ROOT.parents, ROOT/'.runtime', ROOT/'.runtime/tasks',
               ROOT/'.runtime/ap10', ROOT/'.runtime/ap10/rounds'}
    paths = {p/name for p in parents for name in ('AGENTS.md','AGENTS.override.md','.codex/config.toml')}
    home = Path.home()/'.codex'
    paths.update(home/name for name in ('config.toml','AGENTS.md','AGENTS.override.md'))
    # Includes names as well as bytes: a newly added rule must not silently load.
    paths.update((home/'rules').glob('*.rules'))
    # The qualified Claude roles run --restricted, which ignores user, project and
    # local settings; managed settings still apply and are therefore bound here.
    managed = Path('/Library/Application Support/ClaudeCode')
    paths.update(managed/name for name in ('managed-settings.json','managed-mcp.json','CLAUDE.md'))
    return {str(p):sha(p) if p.is_file() and not p.is_symlink() else
            ('unsafe' if p.exists() or p.is_symlink() else None) for p in sorted(paths)}


def require_workspace_instructions(workspace):
    config = require_active_code()
    known = config['instruction_guards']
    workspace = Path(workspace).resolve()
    for parent in workspace.parents:
        for name in ('AGENTS.md','AGENTS.override.md','.codex/config.toml'):
            path = parent/name
            if str(path) not in known and (path.exists() or path.is_symlink()):
                raise ValueError('Unbound intermediate native instruction/configuration: '+str(path))
    # Candidate-local AGENTS is already committed/frozen with its accepted base.
    # A separate nested Codex config is not part of this qualified profile.
    if (workspace/'.codex/config.toml').exists():
        raise ValueError('Unqualified workspace-specific Codex configuration')
    return config


def installed():
    if not ACTIVE.exists():
        return None
    pointer = json.loads(ACTIVE.read_text())
    config = Path(pointer['config'])
    releases = ROOT / '.runtime/ap10/releases'
    if (config.is_symlink() or config.name != 'config.json'
            or config.parent.parent != releases or sha(config) != pointer['sha256']):
        raise ValueError('Invalid pinned service configuration')
    value = json.loads(config.read_text())
    if value['host_root'] != str(ROOT) or value['office_root'] != str(ROOT.parent / 'nortropic-projektkontor'):
        raise ValueError('Pinned canonical state/target mapping differs')
    if value['database'] != str(ROOT / '.runtime/runtime.sqlite'):
        raise ValueError('Only the existing canonical database is permitted')
    if value.get('instruction_guards') != instruction_guards():
        raise ValueError('Native instruction/configuration inputs changed; inspect before a new model call')
    for name, expected in value['files'].items():
        path = config.parent / name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError('Pinned active code changed: ' + name)
    value.update(config_path=str(config), config_sha256=pointer['sha256'], directory=str(config.parent))
    return value


def require_active_code():
    value = installed()
    if (not value or CODE_ROOT != Path(value['directory']) / 'runtime'
            or os.environ.get('NR_CONFIG_SHA256') != value['config_sha256']):
        raise ValueError('Execution requires the exact activated release')
    return value


def revision():
    if os.environ.get('NR_CONFIG_SHA256'):
        return require_active_code()['runtime_revision']
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()


def delegate(module, args):
    """A live checkout command delegates to frozen code; it never starts a daemon."""
    value = installed()
    if value is None or os.environ.get('NR_CONFIG_SHA256'):
        return None
    env = dict(os.environ, NR_HOST_ROOT=str(ROOT), NR_CONFIG_SHA256=value['config_sha256'],
               PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([str(ROOT / '.runtime/temporal-venv/bin/python'), '-B', '-m', module, *args],
                          cwd=Path(value['directory']) / 'runtime', env=env, check=False).returncode
