"""The measurement profile (D034): one page, its views, no model.

    <runtime venv python> -B -m runtime.web_measure (--mal URL | --fil PATH) --etikett NAME [--sektioner N]
        [--delar skarm,rubrik,axe,lighthouse,detektor] [--handling-text TEXT] [--handling-selektor CSS]
        [--undantag-fil PATH] [--undantag-sort vercel-automation-bypass]
        [--vyer NAME=WIDTHxHEIGHT@SCALEm|d,...] [--axe-taggar TAG,...]

The views and the axe tags are professional defaults (D034's values, chosen by Digitala), not the engine's own
requirement (D037): a management function passes its own with --vyer and --axe-taggar, and the receipt records
which views and tags ran and whether the defaults were used. The mechanics - the browser, the parts, the snapshot, the
sandboxed detector, the receipt - are the engine's and do not change with them.

A local file is served read-only from its own directory on 127.0.0.1 for the length of the run, so every part
(including Lighthouse, which needs http) sees the same page. The host runs the detector afterwards on each view's
self-contained snapshot inside Runtime's sandbox, with no network and read access to the snapshot only.
"""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse

from . import web_common as common
from .profile import ROOT

PARTS = ('skarm', 'rubrik', 'axe', 'lighthouse', 'detektor')
VIEWPORTS = {
    'mobil-390': {'width': 390, 'height': 844, 'deviceScaleFactor': 2, 'isMobile': True, 'hasTouch': True},
    'desktop-1440': {'width': 1440, 'height': 900, 'deviceScaleFactor': 1, 'isMobile': False, 'hasTouch': False},
}
AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']
# D037: the two names above are parameters; a caller that reads PARAMETRAR knows this code takes them.
PARAMETRAR = ('vyer', 'axe-taggar')
VY = re.compile(r'\A([a-z][a-z0-9-]{0,19})=([0-9]{3,4})x([0-9]{3,4})@([1-3])([md])\Z')
AXE_TAG = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9.-]{1,23}\Z')
VY_MAX, TAG_MAX = 4, 12
FULL_PAGE_MAX = 16384
SELECTOR = re.compile(r'\A[A-Za-z0-9 .#:_\-\[\]="\'>+~*()^$|,]{1,200}\Z')
CODE = ('runtime/web_measure.py', 'runtime/web_common.py', 'runtime/web/measure.mjs', 'config/web-tools.lock.json')
MEASURE_SECONDS = 900
DETECTOR_SECONDS = 120


def target_url(value):
    parts = urllib.parse.urlsplit(value or '')
    loopback = parts.hostname in ('127.0.0.1', 'localhost')
    if parts.scheme not in ('https', 'http') or (parts.scheme == 'http' and not loopback) or not parts.hostname:
        raise ValueError('The address must be https, or http on 127.0.0.1 or localhost')
    if parts.username or parts.password:
        raise ValueError('An address may not carry credentials')
    return value


def parse_viewports(text):
    """NAME=WIDTHxHEIGHT@SCALE followed by m (mobile, touch) or d (desktop): 1-4 unique names within Chrome's range."""
    views = {}
    for item in (text or '').split(','):
        match = VY.match(item)
        if not match:
            raise ValueError('--vyer is NAMN=BREDDxHOJD@SKALAm|d, comma-separated: ' + item[:40])
        name, width, height, scale, kind = match.groups()
        width, height = int(width), int(height)
        if name in views or not 320 <= width <= 2560 or not 320 <= height <= 2000:
            raise ValueError('--vyer: repeated name or size outside 320-2560 x 320-2000: ' + item[:40])
        views[name] = {'width': width, 'height': height, 'deviceScaleFactor': int(scale), 'isMobile': kind == 'm',
                       'hasTouch': kind == 'm'}
    if not 1 <= len(views) <= VY_MAX:
        raise ValueError('--vyer names 1-%d views' % VY_MAX)
    return views


def parse_axe_tags(text):
    tags = (text or '').split(',')
    if not 1 <= len(tags) <= TAG_MAX or len(tags) != len(set(tags)) or any(not AXE_TAG.match(t) for t in tags):
        raise ValueError('--axe-taggar is 1-%d unique axe tag names' % TAG_MAX)
    return tags


def local_file(value):
    path = Path(value or '')
    if not path.is_absolute() or path.suffix.lower() not in ('.html', '.htm'):
        raise ValueError('A file target is an absolute path to an .html or .htm file')
    if path.is_symlink() or not path.is_file() or str(path.resolve()) != os.path.normpath(str(path)):
        raise ValueError('A file target must be a regular file reached without links')
    return path


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *arguments):
        pass


def serve_directory(directory):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def parse(argv):
    parser = argparse.ArgumentParser(prog='runtime.web_measure')
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument('--mal')
    where.add_argument('--fil')
    parser.add_argument('--etikett', required=True)
    parser.add_argument('--sektioner', type=int, default=2)
    parser.add_argument('--delar', default=','.join(PARTS))
    parser.add_argument('--handling-text')
    parser.add_argument('--handling-selektor')
    parser.add_argument('--undantag-fil')
    parser.add_argument('--undantag-sort', default='vercel-automation-bypass')
    parser.add_argument('--vyer')
    parser.add_argument('--axe-taggar')
    args = parser.parse_args(argv)
    common.label(args.etikett)
    args.viewports = parse_viewports(args.vyer) if args.vyer is not None else dict(VIEWPORTS)
    args.axe_tags = parse_axe_tags(args.axe_taggar) if args.axe_taggar is not None else list(AXE_TAGS)
    args.standardvarden = {'vyer': args.vyer is None, 'axe_taggar': args.axe_taggar is None}
    if not 0 <= args.sektioner <= 4:
        raise ValueError('--sektioner is 0-4')
    parts = [p for p in args.delar.split(',') if p]
    if not parts or len(parts) != len(set(parts)) or any(p not in PARTS for p in parts):
        raise ValueError('--delar is a subset of ' + ','.join(PARTS))
    args.parts = sorted(set(parts) | {'skarm'}, key=PARTS.index)
    if args.handling_text is not None and not 0 < len(args.handling_text) <= 80:
        raise ValueError('--handling-text is 1-80 characters')
    if args.handling_selektor is not None and not SELECTOR.match(args.handling_selektor):
        raise ValueError('--handling-selektor is 1-200 characters of a plain CSS selector')
    if args.undantag_fil and not args.mal:
        raise ValueError('An exception applies to an address, not to a local file')
    if args.undantag_fil and args.undantag_sort not in common.SECRET_KINDS:
        raise ValueError('Unknown exception kind')
    if args.mal:
        target_url(args.mal)
    else:
        local_file(args.fil)
    return args


def detector(run, name):
    """impeccable detect on one snapshot, in the sandbox: no network, read the snapshot, write only scratch."""
    snapshot = (run / 'ogonblick' / (name + '.html')).resolve()
    if not snapshot.is_file():
        return {'ran': False, 'reason': 'ingen ögonblicksbild'}
    scratch = run / '.detektor-scratch' / name
    scratch.mkdir(parents=True)
    scratch = scratch.resolve()
    # The sandbox grants what it executes by its real path; a linked bin directory would otherwise be refused.
    binary = common.impeccable_binary().resolve()
    table = {':minimal': 'read', str(binary): 'read', str(snapshot): 'read', str(scratch): 'write'}
    encoded = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in table.items()) + '}'
    from .codex_pin import BINARY
    argv = [str((ROOT / BINARY).resolve()), 'sandbox', '-c', 'permissions.nr.filesystem=' + encoded,
            '-c', 'permissions.nr.network.enabled=false', '-c', 'default_permissions="nr"', '-P', 'nr',
            '-C', str(scratch), str(binary), 'detect', '--json', '--no-config', str(snapshot)]
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(scratch), 'TMPDIR': str(scratch), 'LANG': 'C'}
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=scratch, env=env, capture_output=True, timeout=DETECTOR_SECONDS)
    except subprocess.TimeoutExpired:
        return {'ran': False, 'reason': 'tidsgräns'}
    record = {'ran': True, 'exit_code': done.returncode, 'seconds': round(time.monotonic() - started, 1),
              'meaning': {0: 'inga fynd', 2: 'fynd', 1: 'kunde inte skanna'}.get(done.returncode, 'okänt')}
    try:
        findings = json.loads(done.stdout.decode())
        record['findings'] = len(findings) if isinstance(findings, list) else None
    except ValueError:
        findings, record['findings'] = None, None
    (run / 'detektor').mkdir(exist_ok=True)
    (run / 'detektor' / (name + '.json')).write_bytes(done.stdout)
    shutil.rmtree(scratch)
    return record


def summary(run, result, detectors, viewports=VIEWPORTS):
    views = {}
    for name in viewports:
        entry = {'status': (result.get('views') or {}).get(name, {}).get('status')}
        measured = run / 'matning' / (name + '.json')
        if measured.is_file():
            data = json.loads(measured.read_text())
            entry['h1'] = [{k: h[k] for k in ('text', 'lines', 'font_size_px', 'in_first_view')} for h in data['h1']]
            entry['action'] = {k: data['action'].get(k) for k in ('found', 'match', 'text', 'fully_in_first_view')}
        axe = run / 'axe' / (name + '.json')
        if axe.is_file():
            data = json.loads(axe.read_text())
            entry['axe'] = {'violations': [v['id'] for v in data['violations']],
                            'incomplete': [v['id'] for v in data['incomplete']]}
        if name in detectors:
            entry['detector'] = {k: detectors[name].get(k) for k in ('exit_code', 'findings', 'meaning')}
            found = run / 'detektor' / (name + '.json')
            try:
                entry['detector']['antipatterns'] = sorted({f.get('antipattern') for f in json.loads(found.read_text())
                                                           if isinstance(f, dict)}) if found.is_file() else []
            except ValueError:
                entry['detector']['antipatterns'] = None
        view = (result.get('views') or {}).get(name, {})
        entry['sections'] = {'requested': view.get('sections_requested'), 'taken': view.get('sections_taken')}
        views[name] = entry
    return {'views': views, 'lighthouse': result.get('lighthouse'), 'primed': result.get('primed')}


def run(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    started = common.now()
    tools = common.tool_identity(with_impeccable='detektor' in args.parts)
    secret = common.read_secret(args.undantag_fil, ROOT / '.runtime/profiler') if args.undantag_fil else None
    run_directory = common.new_run_directory('matning', args.etikett)
    server, target = None, {}
    try:
        if args.fil:
            path = local_file(args.fil)
            server = serve_directory(path.parent)
            url = 'http://127.0.0.1:%d/%s' % (server.server_address[1], urllib.parse.quote(path.name))
            target = {'kind': 'fil', 'path': str(path), 'sha256': common.sha256_file(path), 'served_as': url}
        else:
            url = args.mal
            target = {'kind': 'adress', 'address': url}
        profile_directory = run_directory / '.chrome-profil'
        profile_directory.mkdir()
        config = {'target_url': url, 'target_origin': '%s://%s' % urllib.parse.urlsplit(url)[:2],
                  'parts': args.parts, 'sections': args.sektioner, 'viewports': args.viewports, 'axe_tags': args.axe_tags,
                  'full_page_max': FULL_PAGE_MAX, 'action_text': args.handling_text,
                  'action_selector': args.handling_selektor, 'out_dir': str(run_directory),
                  'profile_dir': str(profile_directory), 'chrome_path': str(common.CHROME),
                  'tools_dir': str(common.tools_directory()),
                  'secret': common.SECRET_KINDS[args.undantag_sort] if secret else None}
        (run_directory / 'matning-konfig.json').write_text(json.dumps(config, indent=1, ensure_ascii=False) + '\n')
        env = common.filtered_environment({'NR_UNDANTAG': secret} if secret else None)
        env['PATH'] = str(common.NODE.parent) + ':/usr/bin:/bin'
        log = (run_directory / 'matning.log').open('wb')
        started_node = time.monotonic()
        try:
            node = subprocess.Popen([str(common.NODE), str(common.WEB / 'measure.mjs'),
                                     str(run_directory / 'matning-konfig.json')],
                                    cwd=run_directory, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                node_exit = node.wait(timeout=MEASURE_SECONDS)
            except subprocess.TimeoutExpired:
                common.end_group(node)
                node_exit = 'tidsgräns'
            except BaseException:
                common.end_group(node)
                raise
        finally:
            log.close()
        node_seconds = round(time.monotonic() - started_node, 1)
    finally:
        # Also after an error or an interrupt: Chrome runs in a group of its own and must not outlive the run (D035); no
        # stop signal cuts this short, and the Chrome profile, which may hold a protected host's cookie, goes (D036).
        with common.shielded():
            if server is not None:
                server.shutdown()
                server.server_close()
            survivors = common.end_chrome(run_directory / '.chrome-profil')
            shutil.rmtree(run_directory / '.chrome-profil', ignore_errors=True)
    result_file = run_directory / 'matning-resultat.json'
    result = json.loads(result_file.read_text()) if result_file.is_file() else {'fatal': 'inget resultat'}
    detectors = {}
    if 'detektor' in args.parts and not result.get('fatal'):
        for name in args.viewports:
            detectors[name] = detector(run_directory, name)
    shutil.rmtree(run_directory / '.detektor-scratch', ignore_errors=True)
    (run_directory / 'SAMMANFATTNING.json').write_text(
        json.dumps(summary(run_directory, result, detectors, args.viewports), indent=1, ensure_ascii=False) + '\n')
    removed = []
    if secret:
        removed = common.remove_contaminated(run_directory, common.secret_hits(run_directory, secret))
    failed = [name for name, view in (result.get('views') or {}).items() if view.get('errors')]
    failed += [form for form, value in (result.get('lighthouse') or {}).items() if value.get('error')]
    failed += [name for name, value in detectors.items() if not value.get('ran') or value.get('exit_code') not in (0, 2)]
    produced = sorted(p.name for p in (run_directory / 'skarm').glob('*.png')) if (run_directory / 'skarm').is_dir() else []
    if removed:
        outcome_name, reason = 'hemlighet_i_utdata', 'undantagets värde fanns i utdata; filerna är borttagna'
    elif not produced:
        outcome_name, reason = 'fel', result.get('fatal') or ('webbläsarhalvan: ' + str(node_exit))
    elif result.get('fatal') or node_exit not in (0,):
        outcome_name, reason = 'delvis', result.get('fatal') or ('webbläsarhalvan: ' + str(node_exit))
    elif failed:
        outcome_name, reason = 'delvis', 'delar föll: ' + ', '.join(failed)
    else:
        outcome_name, reason = 'klar', None
    receipt = {'profile': 'matning', 'code': common.code_files(*CODE), **common.code_root_info(),
               'started_at': started, 'target': target, 'parameters': {
                   'sections': args.sektioner, 'parts': args.parts, 'action_text': args.handling_text,
                   'action_selector': args.handling_selektor, 'label': args.etikett,
                   'exception': args.undantag_sort if secret else None,
                   'vyer': args.vyer, 'axe_taggar': args.axe_taggar, 'standardvarden': args.standardvarden},
               'viewports': args.viewports, 'axe_tags': args.axe_tags, 'tools': tools, 'browser_half': {'exit': node_exit, 'seconds': node_seconds,
                                                                       'result': result},
               'detector': detectors, 'chrome_profile_removed': not (run_directory / '.chrome-profil').exists(),
               'chrome_running_after_stop': survivors,
               'secret': {'used': bool(secret), 'hits_removed': removed},
               'outcome': outcome_name, 'reason': reason}
    common.write_receipt(run_directory, receipt)
    print(json.dumps({'run': str(run_directory), 'outcome': outcome_name, 'reason': reason}, ensure_ascii=False))
    return 0 if outcome_name == 'klar' else 1


if __name__ == '__main__':
    try:
        with common.stop_signals():
            sys.exit(run())
    except ValueError as error:
        print(json.dumps({'outcome': 'vagrad', 'reason': str(error)}, ensure_ascii=False))
        sys.exit(2)
    except common.Stopped as error:
        print(json.dumps({'outcome': 'avbruten', 'reason': str(error)}, ensure_ascii=False))
        sys.exit(3)
