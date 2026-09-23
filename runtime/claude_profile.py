"""Native restricted Claude file tools; host owns execution/tests/publication."""
import json
import hashlib
from pathlib import Path
import re
import subprocess
import uuid

MODEL = 'claude-fable-5-1'
# A provider model id: alphanumeric start, then the characters real ids use, bounded. Deliberately
# narrow - this value becomes an argv element, and the only names that need to pass are model ids.
MODEL_NAME = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
VERSION = '2.1.257'
BINARY_SHA256 = '64590d7d9d9c189d33fb3dfa58c5408eaf2a10fe556bd84155d95efaab46b60e'


def qualified_binary():
    """The pinned CLI, from the host's own copy beside its pinned Codex and Temporal binaries.

    Resolving `claude` on PATH shared the binary with the owner's own chat, so an update of that global
    install stopped every Runtime Claude role: on 2026-09-23 it updated itself from the qualified 2.1.257
    to 2.1.280. The host keeps exactly the qualified bytes instead, checked by the same hash as before.
    """
    from .release import ROOT
    binary = ROOT / '.runtime/bin' / ('claude-' + VERSION)
    if binary.is_symlink() or not binary.is_file():
        raise ValueError('Qualified Claude CLI is unavailable')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
        raise ValueError('Claude binary changed; qualify the new version before execution')
    return str(binary)


SETTINGS={'enabledPlugins':{'slack@claude-plugins-official':False},
          'autoMemoryEnabled':False,
          'permissions':{'defaultMode':'dontAsk','blockReadsOutsideWorkingDirectories':True}}


def selected_model(model=None):
    """The release's explicit model choice, or this profile's own qualified model when none is bound.

    The name must be a plain provider model id. Anything else is refused HERE rather than after a
    launch: a padded or newline-bearing name reaches argv and only fails once the provider answers,
    having already spent a call, and an embedded NUL makes Popen itself raise where the caller's
    preflight handler could not classify it. The value is checked again after the run - provider_result
    compares it against the identity the provider reports - so a substitution fails the terminal too.
    """
    chosen = MODEL if model is None else model
    if not isinstance(chosen, str) or not MODEL_NAME.match(chosen):
        raise ValueError('Claude profile needs a plain model name')
    return chosen


def interactive_command(workspace, prompt, answer, session, model=None):
    """Genuine TUI session that may read its workspace and write ONE scratch file.

    Measured with the pinned CLI: the prompt must come first because the variadic
    tool options swallow a trailing positional; the permission mode refuses every
    other write; slash commands are disabled, so the operator ends the session with
    two Ctrl-C (exit 0); the host-chosen session id names the native record.
    Print-only flags do not apply to a TUI.
    """
    workspace=Path(workspace).resolve(); answer=Path(answer).resolve()
    if answer.parent!=workspace/'.scratch' or not isinstance(prompt,str) or not prompt.strip() or prompt.startswith('-'):
        raise ValueError('Interactive profile needs a plain prompt and one scratch answer file')
    if not isinstance(session,str) or str(uuid.UUID(session))!=session:
        raise ValueError('Interactive profile needs a canonical host-chosen session id')
    return [qualified_binary(),prompt,'--session-id',session,'--model',selected_model(model),'--effort','medium',
            '--restricted','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
            '--tools','Read,Write','--allowedTools','Read','Edit(/'+str(answer)+')',
            '--permission-mode','dontAsk','--no-chrome','--disable-slash-commands',
            '--settings',json.dumps(SETTINGS),
            '--append-system-prompt-file',str(workspace/'AGENTS.md')]


def command(workspace, allowed_paths=(), writable=True, model=None):
    workspace=Path(workspace).resolve()
    grants=['Read']
    if writable:
        grants += ['Edit(/'+str(workspace/name)+')' for name in allowed_paths]
    settings=SETTINGS
    return [qualified_binary(),'-p','--model',selected_model(model),'--effort','medium',
            '--output-format','stream-json','--verbose','--include-hook-events',
            '--restricted','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
            '--tools','Read,Edit,Write' if writable else 'Read',
            '--allowedTools',*grants,'--permission-mode','dontAsk',
            '--no-chrome','--disable-slash-commands','--no-session-persistence',
            '--settings',json.dumps(settings),
            '--append-system-prompt-file',str(workspace/'AGENTS.md')]


def require_subscription():
    from .profile import environment
    result = subprocess.run([qualified_binary(), 'auth', 'status'], env=environment(),
                            capture_output=True, text=True, check=True, timeout=10)
    auth = json.loads(result.stdout)
    safe = {k: auth.get(k) for k in ('loggedIn','authMethod','apiProvider','subscriptionType')}
    if safe != {'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty','subscriptionType':'max'}:
        raise ValueError('Previously qualified subscription path is not active; no API fallback')
    return safe
