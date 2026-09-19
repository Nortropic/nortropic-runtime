"""Explicit no-model injection into the real guardian, only for recovery evidence."""
import json
import sys
from runtime import attempt
from runtime.profile import sandbox_command

request=json.load(sys.stdin)
def fixture_command(workspace, writable=True):
    return sandbox_command(workspace, ['/opt/homebrew/bin/python3.12','-B',
                                      '.scratch/fixture_provider.py',str(request['number'])],writable=True)
attempt.command=fixture_command
raise SystemExit(attempt.execute(**request))
