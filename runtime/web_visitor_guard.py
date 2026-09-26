"""PreToolUse guard for the Claude path of the visitor profile (D034).

Claude Code runs this before EVERY tool call of the visitor session and follows its answer. The rules are closed:
  Bash  only exactly `./handling <action>` as the shared grammar allows it, with single spaces and no character a
        shell would interpret; everything else is denied with a reason;
  Read  only a file whose resolved path lies inside the visitor's workspace;
  any other tool is denied.
Every decision is appended to NR_VISITOR_GUARD_LOG, outside the workspace, with the command or path shortened.
Reads the hook's JSON on stdin and answers in Claude Code's hook format on stdout. It starts with -I, so it puts its
own code root on the path explicitly and imports nothing from the working directory.
"""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.web_common import command_words, load_grammar, validate_action  # noqa: E402


def decide(payload, workspace, grammar):
    tool = payload.get('tool_name')
    arguments = payload.get('tool_input') or {}
    if tool == 'Bash':
        words = command_words(str(arguments.get('command', '')), grammar)
        if words is None:
            return 'deny', 'bara handlingskommandot (./handling <handling>) är tillåtet i denna session'
        try:
            validate_action(words, grammar)
        except ValueError as error:
            return 'deny', 'handlingen följer inte grammatiken: ' + str(error)
        return 'allow', 'handlingskommandot med en tillåten handling'
    if tool == 'Read':
        target = os.path.realpath(str(arguments.get('file_path', '')))
        root = os.path.realpath(workspace) if workspace else None
        if root and (target == root or target.startswith(root + os.sep)):
            return 'allow', 'fil i arbetsytan'
        return 'deny', 'läsning bara i arbetsytan'
    return 'deny', 'verktyget %s ingår inte i provarens profil' % tool


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    workspace = os.environ.get('NR_VISITOR_WORKSPACE', '')
    try:
        decision, reason = decide(payload, workspace, load_grammar())
    except Exception as error:  # an unreadable grammar or anything unexpected denies, never allows
        decision, reason = 'deny', 'vakten kunde inte pröva anropet: ' + type(error).__name__
    log = os.environ.get('NR_VISITOR_GUARD_LOG', '')
    if log:
        try:
            arguments = payload.get('tool_input') or {}
            with open(log, 'a') as stream:
                stream.write(json.dumps({'t': time.time(), 'tool': payload.get('tool_name'), 'decision': decision,
                                         'reason': reason,
                                         'summary': str(arguments.get('command') or arguments.get('file_path') or '')[:200]},
                                        ensure_ascii=False) + '\n')
        except OSError:
            pass
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': decision,
                                             'permissionDecisionReason': reason}}))


if __name__ == '__main__':
    main()
