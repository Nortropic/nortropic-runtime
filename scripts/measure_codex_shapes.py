"""Measure, with the pinned Codex CLI (runtime/codex_pin.py), what the host relies on from it (D047):

config-read  no model call: the app-server started with exactly the global argument prefix runtime.profile.command builds
             for the exec route, then initialize, initialized and config/read - that the model argument is taken verbatim
             from the command line over the owner's own config.toml, with the reasoning effort beside it; and the
             default commands this code builds against those the ACTIVE release builds (only the binary may differ):
             the startup chain, the read-only, writable and allowed-paths exec commands and the interactive session
sandbox      no model call: runtime.profile.sandbox_command runs a shell that reads the workspace, writes .scratch, and
             tries to write a read-only directory, the stand-in home directory it runs with and the network
exec         ONE model call: the watch's route, runtime.profile.command(writable=False) - the private stage adds only
             --output-schema - on a synthetic read task in a git workspace, parsed by runtime.provider_result.parse('codex',
             ...) as the private stage does; the answer is the last agent message

Each writes <codex_pin.EVIDENCE>/<name>-shape.json in the checkout that holds this script, once (it refuses to overwrite),
in runtime.profile.environment(); raw protocol and events stay under the host's .runtime/codex-shapes-<VERSION>/, named
by their hash. Run with NR_HOST_ROOT set to the host, so the binary is named by its real path as in operation: Codex
re-executes itself inside its sandbox to load AGENTS.md, and the sandbox refuses a path through a symlink (measured for
0.155.1 and 0.159.2 alike).
usage: <runtime venv python> -B -m scripts.measure_codex_shapes config-read|sandbox|exec
"""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

from runtime import codex_pin, profile
from runtime.provider_result import parse
from runtime.release import ROOT

CODE = Path(__file__).resolve().parents[1]          # the checkout that holds this script (the candidate)
EVIDENCE = CODE / codex_pin.EVIDENCE
PRIVATE = ROOT / '.runtime' / ('codex-shapes-' + codex_pin.VERSION)
BINARY = ROOT / codex_pin.BINARY


def sha(data):
    return hashlib.sha256(data).hexdigest()


def workspace(parent, git=False):
    ws = Path(tempfile.mkdtemp(prefix='nr-codex-', dir=parent)).resolve()
    (ws / '.scratch').mkdir(); (ws / 'tools').mkdir()
    (ws / 'AGENTS.md').write_text('Synthetic Runtime measurement workspace. Read only; answer briefly.\n')
    if git:
        subprocess.run(['git', 'init', '-q', str(ws)], check=True, timeout=10)
    return ws


def config_read(parent, model):
    ws = workspace(parent)
    argv = profile.command(ws, writable=False, model=model)
    argv = argv[:argv.index('exec')] + ['app-server']
    process = subprocess.Popen(argv, cwd=ws, env=profile.environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    sent, raw = [], []

    def send(message):
        sent.append(message['method'])
        process.stdin.write((json.dumps(message) + '\n').encode()); process.stdin.flush()

    def answer(wanted, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if not select.select([process.stdout], [], [], 0.5)[0]:
                continue
            line = process.stdout.readline()
            if not line:
                break
            raw.append(line)
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('id') == wanted:
                return message
        raise SystemExit('no answer to request %s' % wanted)
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'nr-measure', 'version': '1'}}})
        answer(1)
        send({'method': 'initialized'})
        send({'id': 2, 'method': 'config/read', 'params': {'includeLayers': True, 'cwd': str(ws)}})
        result = answer(2).get('result') or {}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    blob = b''.join(raw)
    (PRIVATE / ('config-read-%s.jsonl' % (model or 'no_choice'))).write_bytes(blob)
    kind = lambda origin: ((origin or {}).get('name') or {}).get('type')
    config, origins, layers = result.get('config') or {}, result.get('origins') or {}, result.get('layers') or []
    return sent, layers, kind, {
        'model_argument': [a for a in argv if a.startswith('model=')], 'resolved_model': config.get('model'),
        'resolved_reasoning_effort': config.get('model_reasoning_effort'), 'origin_model': kind(origins.get('model')),
        'origin_reasoning_effort': kind(origins.get('model_reasoning_effort')), 'raw_sha256': sha(blob)}


def default_commands(code_root, parent):
    """The default commands built by the code under code_root, in an interpreter of its own, for one workspace."""
    ws = parent / 'default-ws'                         # one workspace for both code roots, as compared
    ws.mkdir(exist_ok=True); (ws / '.scratch').mkdir(exist_ok=True); (ws / 'AGENTS.md').write_text('x\n')
    script = ('import json, sys\nfrom runtime import profile\nfrom runtime.development_interactive import interactive_command\n'
              'from scripts.probe_bridge import worker_command\nfrom pathlib import Path\nws = Path(sys.argv[1])\n'
              'print(json.dumps({"worker": worker_command(), "read_only": profile.command(ws, writable=False),'
              ' "writable": profile.command(ws), "allowed": profile.command(ws, allowed_paths=["tools/x.py"]),'
              ' "interactive": interactive_command(ws, "p"), "root": str(Path(profile.__file__).resolve().parents[1])}))\n')
    done = subprocess.run([sys.executable, '-B', '-c', script, str(ws)], cwd=code_root, capture_output=True, text=True,
                          env=dict(profile.environment(), PYTHONPATH=str(code_root), NR_HOST_ROOT=str(ROOT)), timeout=60,
                          check=True)
    return json.loads(done.stdout)


def measure_config_read(parent):
    sent, layers, kind, no_choice = config_read(parent, None)
    _, _, _, probe_name = config_read(parent, 'nr-probe.model-1')
    active = Path(json.loads((ROOT / '.runtime/ap10/active.json').read_text())['config']).parent / 'runtime'
    old, new = default_commands(active, parent), default_commands(CODE, parent)
    shapes = ('worker', 'read_only', 'writable', 'allowed', 'interactive')
    only_binary = {s: len(old[s]) == len(new[s]) and old[s][1:] == new[s][1:] for s in shapes}
    return {
        'source': ('Actual no-model measurement %s with the pinned Codex CLI %s (scripts/measure_codex_shapes.py config-read): '
                   'the app-server started with exactly the global argument prefix runtime.profile.command(writable=False) '
                   'builds for the exec route, then initialize and config/read. No thread and no turn were requested. '
                   'Reduced mechanically to the resolved model, reasoning effort and the type of the layer each came '
                   'from; paths, the owner\'s own configuration values and the rest of the response are omitted. The raw '
                   'protocol stays in the private evidence root, named by its hash.' % (time.strftime('%Y-%m-%d', time.gmtime()), codex_pin.VERSION)),
        'why': ('The premise the Codex choice rests on, measured rather than assumed, again for this pin: that the pinned CLI '
                'takes the model argument the startup chain passes VERBATIM as its effective model, from the command-line '
                'layer, over the owner\'s own config.toml that names a model too.'),
        'cli': {'version': subprocess.run([str(BINARY), '--version'], capture_output=True, text=True).stdout.strip().split()[-1],
                'binary_sha256': sha(BINARY.read_bytes())},
        'requests': sorted(set(sent)), 'layers': [kind(layer) for layer in layers],
        'layer_sets_model': {kind(layer): 'model' in (layer.get('config') or {}) for layer in layers},
        'cases': {'no_choice': no_choice, 'probe_name': probe_name},
        'default_against_active': {
            'what': ('The default commands built by the ACTIVE release\'s own code (%s) and by this code, in separate '
                     'interpreters that each imported from their own code root, for the same workspace and host root.' % old['root'].replace(str(ROOT), '<host>')),
            'code_roots_differ': old['root'] != new['root'],
            'only_the_binary_differs': only_binary,
            'binaries': [old['worker'][0].replace(str(ROOT), '<host>'), new['worker'][0].replace(str(ROOT), '<host>')]}}


def measure_sandbox(parent):
    ws, home = workspace(parent), Path(tempfile.mkdtemp(prefix='nr-codex-home-', dir=parent)).resolve()
    (home / 'h/.codex').mkdir(parents=True); (home / 'h/.codex/config.toml').write_text('')
    (ws / 'AGENTS.md').write_text('las-mig\n')
    script = ('cat AGENTS.md; echo "read:$?"; echo ok > .scratch/ok; echo "scratch:$?"; echo no > tools/no; echo "tools:$?"; '
              'echo no > %s/no; echo "home:$?"; /usr/bin/curl -s -m 5 -o /dev/null https://example.com; echo "network:$?"' % (home / 'h'))
    done = subprocess.run(profile.sandbox_command(ws, ['/bin/sh', '-c', script], writable=False), cwd=ws, capture_output=True,
                          text=True, env=dict(profile.environment(), HOME=str(home / 'h')), timeout=60)
    status = dict(line.split(':', 1) for line in done.stdout.splitlines()
                  if ':' in line and line.split(':')[0] in ('read', 'scratch', 'tools', 'home', 'network'))
    return {'source': ('Actual no-model run %s of runtime.profile.sandbox_command(writable=False) with the pinned Codex CLI %s '
                       '(scripts/measure_codex_shapes.py sandbox).' % (time.strftime('%Y-%m-%d', time.gmtime()), codex_pin.VERSION)),
            'returncode': done.returncode, 'exit_status': status, 'read_the_workspace': 'las-mig' in done.stdout,
            'scratch_written': (ws / '.scratch/ok').exists(), 'read_only_written': (ws / 'tools/no').exists(),
            'home_written': (home / 'h/no').exists()}


def measure_exec(parent):
    ws = workspace(parent, git=True)
    (ws / 'NOTE.md').write_text('The value is 42.\n')
    done = subprocess.run(profile.command(ws, writable=False), cwd=ws, env=profile.environment(),
                          input='Read NOTE.md and answer with the value only.', capture_output=True, text=True, timeout=180)
    (PRIVATE / 'exec.jsonl').write_text(done.stdout)
    rows = []
    for line in done.stdout.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    parsed = parse('codex', rows)
    messages = [r['item'].get('text') for r in rows if r.get('type') == 'item.completed' and isinstance(r.get('item'), dict)
                and r['item'].get('type') == 'agent_message']
    return {'source': ('Actual run %s, one model call: the watch\'s route runtime.profile.command(writable=False) (the private '
                       'stage adds only --output-schema) with the pinned Codex CLI %s on a synthetic read task in a git '
                       'workspace, parsed by runtime.provider_result.parse as the private stage does '
                       '(scripts/measure_codex_shapes.py exec). The raw events stay in the private evidence root, named by '
                       'their hash.' % (time.strftime('%Y-%m-%d', time.gmtime()), codex_pin.VERSION)),
            'returncode': done.returncode, 'raw_sha256': sha(done.stdout.encode()),
            'event_types': sorted({r.get('type') for r in rows}),
            'item_types': sorted({(r.get('item') or {}).get('type') for r in rows if isinstance(r.get('item'), dict)} - {None}),
            'valid_terminal': parsed.get('valid_terminal'), 'answer': (messages or [None])[-1],
            'answer_correct': isinstance((messages or [None])[-1], str) and messages[-1].strip() == '42'}


def main():
    part = sys.argv[1] if sys.argv[1:] in (['config-read'], ['sandbox'], ['exec']) else None
    if not part:
        raise SystemExit('usage: measure_codex_shapes config-read|sandbox|exec')
    if BINARY.resolve() != BINARY or BINARY.is_symlink():
        raise SystemExit('set NR_HOST_ROOT to the host: %s is reached through a link' % BINARY)
    if not BINARY.is_file() or sha(BINARY.read_bytes()) != codex_pin.SHA256:
        raise SystemExit('the host copy at %s is not the pinned bytes' % codex_pin.BINARY)
    target = EVIDENCE / (part + '-shape.json')
    if target.exists():
        raise SystemExit('%s exists; a pin is measured once into its own directory' % target)
    EVIDENCE.mkdir(parents=True, exist_ok=True); PRIVATE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nr-codex-shapes-') as parent:
        record = {'config-read': measure_config_read, 'sandbox': measure_sandbox, 'exec': measure_exec}[part](Path(parent))
    target.write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k not in ('source', 'why')}, indent=1, ensure_ascii=False)[:2500])


if __name__ == '__main__':
    main()
