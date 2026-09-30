"""Pinned AP10 code is separate from the one canonical host state directory."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('NR_HOST_ROOT', CODE_ROOT)).resolve()
ACTIVE = ROOT / '.runtime/ap10/active.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# D041: every Runtime command that runs a Codex model sets model and model_reasoning_effort itself
# (scripts/probe_bridge.worker_command), so the owner's own top-level choice of those two keys in the Codex home
# configuration never reaches a Runtime run. That file is bound without them; everything else in it stays bound.
WITHOUT_OWN_CHOICE = 'without-model-and-effort:'
OWN_CHOICE = re.compile(r'(model|model_reasoning_effort)[ \t]*=[ \t]*"[^"\\\n]*"')


def codex_home_config():
    return Path.home()/'.codex/config.toml'


def _depth_change(line):
    """How much one line changes the array depth, outside strings and comments; None when a multi-line string opens."""
    depth, quote, i = 0, None, 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == '\\' and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif line.startswith(('"""', "'''"), i):
            return None
        elif c in '"\'':
            quote = c
        elif c == '#':
            break
        elif c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
        i += 1
    return depth


def codex_config_digest(path):
    """sha256 of the Codex configuration without its top-level model and model_reasoning_effort assignments (the
    part before the first table, read with array depth). A file this reading cannot be sure of - not UTF-8, or a
    multi-line string before the first table - is hashed whole, so every change to it still counts."""
    data = Path(path).read_bytes()
    try:
        lines = data.decode('utf-8').split('\n')
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    kept, depth = [], 0
    for index, line in enumerate(lines):
        if depth == 0 and line.strip().startswith('['):
            kept.extend(lines[index:])
            break
        change = _depth_change(line)
        if change is None:
            return hashlib.sha256(data).hexdigest()
        if depth == 0 and OWN_CHOICE.fullmatch(line.strip()):
            continue
        depth += change
        kept.append(line)
    return hashlib.sha256('\n'.join(kept).encode('utf-8')).hexdigest()


def guard_value(path, whole=False):
    """One input's bound value: its sha256, 'unsafe' for a link or a non-file, None when absent. The Codex home
    configuration is bound without the owner's two top-level keys (D041), unless it is asked for whole."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return 'unsafe' if path.exists() or path.is_symlink() else None
    if not whole and path == codex_home_config():
        return WITHOUT_OWN_CHOICE + codex_config_digest(path)
    return sha(path)


def guard_paths():
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
    return sorted(paths)


def instruction_guards():
    """Bind live native instruction/config inputs; never copy authentication data.

    A changed input causes unavailable execution, never silently new instructions.
    The snapshots remain usable after ordinary source branch changes.
    """
    return {str(p): guard_value(p) for p in guard_paths()}


def guard_differences(expected):
    """The bound inputs that differ now, each read in the form its release bound it: a release staged before D041
    bound the Codex home configuration whole, and it is still checked whole."""
    actual = {}
    for path in guard_paths():
        bound = expected.get(str(path))
        whole = isinstance(bound, str) and bound != 'unsafe' and not bound.startswith(WITHOUT_OWN_CHOICE)
        actual[str(path)] = guard_value(path, whole=whole)
    return {key: {'expected': expected.get(key), 'actual': actual.get(key)}
            for key in sorted(set(expected) | set(actual))
            if key not in expected or key not in actual or expected.get(key) != actual.get(key)}


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


def inspect_installation():
    """Read and verify installed bytes while reporting native guard drift.

    This is diagnosis/staging input only. It never authorizes execution and does
    not update the active pointer or private user configuration.
    """
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
    differences = guard_differences(value.get('instruction_guards', {}))
    for name, expected in value['files'].items():
        path = config.parent / name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError('Pinned active code changed: ' + name)
    value.update(config_path=str(config), config_sha256=pointer['sha256'], directory=str(config.parent))
    value['guard_differences'] = differences
    return value


def installed():
    value = inspect_installation()
    if value is not None and value.pop('guard_differences'):
        raise ValueError('Native instruction/configuration inputs changed; inspect before a new model call')
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
