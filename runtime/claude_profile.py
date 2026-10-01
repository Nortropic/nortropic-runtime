"""Native restricted Claude file tools; host owns execution/tests/publication."""
import json
import hashlib
from pathlib import Path
import re
import subprocess
import uuid

MODEL = 'claude-fable-5-1'
# The effort every Claude command carried before the effort became a release choice (D040). It stays the default, so
# a release without a choice builds exactly the command it always did.
EFFORT = 'medium'
# A provider model id: alphanumeric start, then the characters real ids use, bounded. Deliberately
# narrow - this value becomes an argv element, and the only names that need to pass are model ids.
MODEL_NAME = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
# A reasoning level as the CLIs name them (low, medium, high, xhigh, max, and Codex's ultra): lower-case letters only,
# bounded. It becomes an argv element too, so anything that could be read as a flag or a second value is refused.
EFFORT_NAME = re.compile(r'\A[a-z]{1,16}\Z')
VERSION = '2.1.285'
BINARY_SHA256 = '51f09bd1e021d9fa8a1864c179799bd37cb39962a937935c5cf6823398e86db4'
# Everything measured with the pinned bytes lives in one directory per version (D046): the qualification runs
# (D019's probes), the review terminal, the interactive session and the model-binding init. The records of an
# earlier version stay where they were, as history; a new pin measures again into its own directory.
EVIDENCE = 'evidence/claude-' + VERSION


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


# 2.1.285 starts two built-in plugins even under --restricted: cc-plugin-agents-md (automatic AGENTS.md loading, which
# D019 replaced by --append-system-prompt-file) and cc-plugin-telemetry. The qualified shape has no plugins (the
# terminal checks require plugins == []), so the profile turns both off; measured in D046's qualification.
# G1 calibration observed cc-plugin-diff as another built-in; an unexpected plugin
# is a refused terminal, never an accepted review. Disable it explicitly as well.
PLUGINS_OFF={'slack@claude-plugins-official':False,'cc-plugin-agents-md@builtin':False,'cc-plugin-telemetry@builtin':False,'cc-plugin-diff@builtin':False}
SETTINGS={'enabledPlugins':dict(PLUGINS_OFF),
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


def selected_effort(effort=None):
    """The release's explicit effort choice (D040), or this profile's own pinned level when none is bound.

    Refused here, before a launch, by the same kind of rule as the model name: a level that is not a plain word
    never reaches an argument list. Whether the pinned CLI accepts the level for the model is measured, not assumed
    here; the workplace offers only what worked in its measurement of this binary.
    """
    chosen = EFFORT if effort is None else effort
    if not isinstance(chosen, str) or not EFFORT_NAME.match(chosen):
        raise ValueError('Claude profile needs a plain effort level')
    return chosen


def interactive_command(workspace, prompt, answer, session, model=None, effort=None):
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
    return [qualified_binary(),prompt,'--session-id',session,'--model',selected_model(model),'--effort',selected_effort(effort),
            '--restricted','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
            '--tools','Read,Write','--allowedTools','Read','Edit(/'+str(answer)+')',
            '--permission-mode','dontAsk','--no-chrome','--disable-slash-commands',
            '--settings',json.dumps(SETTINGS),
            '--append-system-prompt-file',str(workspace/'AGENTS.md')]


def command(workspace, allowed_paths=(), writable=True, model=None, effort=None):
    workspace=Path(workspace).resolve()
    grants=['Read']
    if writable:
        grants += ['Edit(/'+str(workspace/name)+')' for name in allowed_paths]
    settings=SETTINGS
    return [qualified_binary(),'-p','--model',selected_model(model),'--effort',selected_effort(effort),
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
