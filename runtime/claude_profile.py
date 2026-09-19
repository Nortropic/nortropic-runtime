"""Native restricted Claude file tools; host owns execution/tests/publication."""
import json
import hashlib
from pathlib import Path
import shutil

MODEL = 'claude-fable-5-1'
VERSION = '2.1.257'
BINARY_SHA256 = '64590d7d9d9c189d33fb3dfa58c5408eaf2a10fe556bd84155d95efaab46b60e'


def qualified_binary():
    selected = shutil.which('claude')
    if not selected:
        raise ValueError('Qualified Claude CLI is unavailable')
    binary = Path(selected).resolve(strict=True)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
        raise ValueError('Claude binary changed; qualify the new version before execution')
    return str(binary)


def command(workspace, allowed_paths=(), writable=True):
    workspace=Path(workspace).resolve()
    grants=['Read']
    if writable:
        grants += ['Edit(/'+str(workspace/name)+')' for name in allowed_paths]
    settings={'enabledPlugins':{'slack@claude-plugins-official':False},
              'autoMemoryEnabled':False,
              'permissions':{'defaultMode':'dontAsk','blockReadsOutsideWorkingDirectories':True}}
    return [qualified_binary(),'-p','--model',MODEL,'--effort','medium',
            '--output-format','stream-json','--verbose','--include-hook-events',
            '--restricted','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
            '--tools','Read,Edit,Write' if writable else 'Read',
            '--allowedTools',*grants,'--permission-mode','dontAsk',
            '--no-chrome','--disable-slash-commands','--no-session-persistence',
            '--settings',json.dumps(settings),
            '--append-system-prompt-file',str(workspace/'AGENTS.md')]
