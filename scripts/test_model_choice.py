"""The reusable model-choice transition (D029), on a synthetic host.

Nothing here touches the real service: the host is a temporary directory, the engine, launchctl and the database backup
are doubles, and every double that stands in for a function of the tool keeps that function's signature. The staging and
copying run for real on real files, with the tool's own bytes inside the synthetic release.
"""
import asyncio
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from scripts import model_choice as tool

TOOL_BYTES = Path(tool.__file__).read_bytes()
PATHS = tool.paths              # the real function, before any test replaces it
RT, OF = 'a' * 40, 'b' * 40
NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(coroutine):
    return asyncio.run(coroutine)


class Host:
    """A host with one active release holding the tool, code, private context and a history archive."""

    def __init__(self, root):
        self.root = Path(root)
        self.releases = self.root / '.runtime/ap10/releases'
        self.release = self.releases / (RT + '-' + OF)
        files = {'runtime/scripts/model_choice.py': (TOOL_BYTES, 0o444), 'runtime/runtime/x.py': (b'x = 1\n', 0o444),
                 'context/owner.md': (b'private context\n', 0o400), 'history/h.json': (b'{"events": []}\n', 0o400)}
        for name, (data, mode) in files.items():
            path = self.release / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data); path.chmod(mode)
        self.config = {'schema': 1, 'host_root': str(self.root), 'office_root': str(self.root.parent / 'office'),
                       'database': str(self.root / '.runtime/runtime.sqlite'), 'runtime_revision': RT, 'office_revision': OF,
                       'files': {name: sha(data) for name, (data, mode) in files.items()}, 'instruction_guards': {'g': 'h'},
                       'historical_archives': {'office-result-1': {'run_id': 'r', 'sha256': 's'}},
                       'development': {'id': 'office-ap11', 'contract_sha256': 'c' * 64,
                                       'executors': {'driver': 'claude', 'review': 'claude'},
                                       'models': {'claude': 'claude-opus-5'}}}
        self.config_path = self.release / 'config.json'
        self.config_path.write_text(json.dumps(self.config, indent=2) + '\n'); self.config_path.chmod(0o400)
        self.active = self.root / '.runtime/ap10/active.json'
        self.active.write_text(json.dumps({'config': str(self.config_path), 'sha256': sha(self.config_path.read_bytes())}))
        self.plist = self.root / 'LaunchAgents/label.plist'; self.plist.parent.mkdir(); self.plist.write_bytes(b'old plist')
        self.service = self.root / '.runtime/ap10/service.json'

    def installed(self):
        pointer = json.loads(self.active.read_text()); path = Path(pointer['config'])
        return {**json.loads(path.read_text()), 'config_path': str(path), 'config_sha256': pointer['sha256'],
                'directory': str(path.parent)}

    def paths(self, host):
        return {**PATHS(host), 'plist': self.plist}


class HostCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.host = Host(self.temp.name)
        for patcher in (patch.object(tool.release, 'installed', self.host.installed), patch.object(tool, 'paths', self.host.paths)):
            patcher.start(); self.addCleanup(patcher.stop)

    def stage(self, requested, now=NOW, code_root=None):
        return tool.stage(self.host.root, requested, code_root=code_root or self.host.release / 'runtime', now=now)


class HostRootTests(unittest.TestCase):
    def test_the_host_is_read_from_the_release_location(self):
        self.assertEqual(tool.host_root(Path('/h/.runtime/ap10/releases/r/runtime')), Path('/h'))

    def test_a_checkout_copy_of_the_tool_refuses(self):
        """A checkout would judge the choice by code the active release does not run."""
        for place in ('/work/runtime-checkout', '/h/.runtime/ap10/releases/r/other', '/h/.runtime/ap11/releases/r/runtime'):
            with self.subTest(place=place), self.assertRaises(SystemExit):
                tool.host_root(Path(place))


class ActiveCopyTests(HostCase):
    """Every action, not only staging, runs as the copy in the release the active pointer names."""

    def test_the_active_release_copy_is_accepted(self):
        self.assertEqual(tool.require_active_copy(self.host.root, self.host.release / 'runtime'), self.host.release)

    def test_another_release_copy_even_byte_identical_refuses(self):
        record, _ = self.stage({'claude': 'claude-opus-5-5'})
        with self.assertRaises(SystemExit) as caught:
            tool.require_active_copy(self.host.root, Path(record['config']).parent / 'runtime')
        self.assertIn(str(self.host.release / tool.TOOL), str(caught.exception), 'and it names the copy to run')


class InvariantTests(unittest.TestCase):
    BASE = {'files': {'a': '1'}, 'development': {'id': 'g', 'executors': {'driver': 'claude'}, 'models': {'claude': 'm'}}}

    def test_a_change_of_models_only_is_accepted(self):
        new = copy.deepcopy(self.BASE); new['development']['models'] = {'claude': 'n', 'codex': 'o'}
        tool.only_models_differ(self.BASE, new)

    def test_any_other_change_refuses(self):
        for change in (lambda c: c['development']['executors'].update(driver='codex'), lambda c: c['files'].update(b='2'),
                       lambda c: c.update(runtime_revision='x'), lambda c: c['development'].pop('id')):
            new = copy.deepcopy(self.BASE); change(new)
            with self.subTest(new=new), self.assertRaises(SystemExit):
                tool.only_models_differ(self.BASE, new)

    def test_a_configuration_without_a_development_selection_refuses(self):
        with self.assertRaises(SystemExit):
            tool.only_models_differ({'files': {}}, {'files': {}})


class CopyTests(HostCase):
    def test_every_bound_file_is_copied_byte_for_byte_with_its_mode(self):
        target = self.host.releases / 'copy'; target.mkdir()
        tool.copy_release(self.host.release, target, self.host.config['files'])
        for name in self.host.config['files']:
            self.assertEqual((target / name).read_bytes(), (self.host.release / name).read_bytes())
            self.assertEqual((target / name).stat().st_mode & 0o777, (self.host.release / name).stat().st_mode & 0o777)

    def test_a_file_that_differs_from_the_configuration_refuses_and_names_the_active_release(self):
        """Refused at the source, before it is copied, and said to be the active release's fault, not the copy's."""
        files = dict(self.host.config['files'], **{'runtime/runtime/x.py': sha(b'something else')})
        target = self.host.releases / 'copy'; target.mkdir()
        with self.assertRaises(SystemExit) as caught:
            tool.copy_release(self.host.release, target, files)
        self.assertIn('differs in the active release: runtime/runtime/x.py', str(caught.exception))
        self.assertFalse((target / 'runtime/runtime/x.py').exists())

    def test_a_link_in_place_of_a_bound_file_refuses(self):
        (self.host.release / 'context/owner.md').unlink(); (self.host.release / 'context/owner.md').symlink_to('/etc/hosts')
        target = self.host.releases / 'copy'; target.mkdir()
        with self.assertRaises(SystemExit):
            tool.copy_release(self.host.release, target, self.host.config['files'])


class StageTests(HostCase):
    def test_stage_copies_the_active_release_and_changes_only_the_selection(self):
        record, directory = self.stage({'claude': 'claude-opus-5-5', 'codex': None})
        staged = Path(record['config'])
        self.assertEqual(staged.parent.name, '%s-%s-models-%s' % (RT, OF, NOW.strftime('%Y%m%dT%H%M%SZ')))
        new = json.loads(staged.read_text())
        self.assertEqual(new['development']['models'], {'claude': 'claude-opus-5-5'})
        tool.only_models_differ(self.host.config, new)
        for name in self.host.config['files']:
            self.assertEqual((staged.parent / name).read_bytes(), (self.host.release / name).read_bytes())
        self.assertEqual(record['sha256'], sha(staged.read_bytes()))
        self.assertEqual(record['old_config_sha256'], sha(self.host.config_path.read_bytes()))
        self.assertEqual(record['tool_sha256'], sha(TOOL_BYTES))
        self.assertEqual((record['models_before']['claude'], record['models_after']['claude']), ('claude-opus-5', 'claude-opus-5-5'))
        self.assertEqual(json.loads((directory / 'staged.json').read_text()), record)
        self.assertEqual(json.loads(self.host.active.read_text())['config'], str(self.host.config_path), 'nothing is selected')

    def test_a_codex_choice_is_staged_by_a_release_that_can_run_it(self):
        record, _ = self.stage({'codex': 'gpt-6-other'})
        self.assertEqual(record['selection'], {'claude': 'claude-opus-5', 'codex': 'gpt-6-other'})
        self.assertEqual(record['models_after']['codex'], 'gpt-6-other')

    def test_making_the_baseline_explicit_is_a_change_of_the_selection(self):
        record, _ = self.stage({'codex': 'gpt-6-astra'})
        self.assertEqual(record['models_before'], record['models_after'], 'what runs is the same')
        self.assertEqual(record['selection'], {'claude': 'claude-opus-5', 'codex': 'gpt-6-astra'})

    def test_refusals_leave_no_release_behind(self):
        cases = {'unchanged': {'claude': 'claude-opus-5'}, 'nothing named': {'claude': None, 'codex': None},
                 'flag-like name': {'claude': '--restricted'}, 'padded name': {'codex': 'gpt-6-astra '}}
        for label, requested in cases.items():
            with self.subTest(case=label), self.assertRaises(SystemExit):
                self.stage(requested)
        self.assertEqual(sorted(p.name for p in self.host.releases.iterdir()), [RT + '-' + OF])

    def test_a_copy_of_the_tool_outside_the_active_release_refuses(self):
        with self.assertRaises(SystemExit):
            self.stage({'claude': 'claude-opus-5-5'}, code_root=Path(tool.__file__).resolve().parents[1])

    def test_a_tool_the_release_does_not_bind_refuses(self):
        """A tool file lying in the release without being in its file map is not the release's tool, and a copy made
        from that map would not carry it forward."""
        config = json.loads(self.host.config_path.read_text()); del config['files'][tool.TOOL]
        self.host.config_path.chmod(0o600); self.host.config_path.write_text(json.dumps(config, indent=2) + '\n')
        self.host.active.write_text(json.dumps({'config': str(self.host.config_path), 'sha256': sha(self.host.config_path.read_bytes())}))
        with self.assertRaises(SystemExit) as caught:
            self.stage({'claude': 'claude-opus-5-5'})
        self.assertIn('does not bind these tool bytes', str(caught.exception))

    def test_edited_tool_bytes_refuse(self):
        (self.host.release / 'runtime/scripts/model_choice.py').chmod(0o644)
        (self.host.release / 'runtime/scripts/model_choice.py').write_bytes(TOOL_BYTES + b'\n# edited\n')
        with self.assertRaises(SystemExit):
            self.stage({'claude': 'claude-opus-5-5'})

    def test_an_existing_release_or_record_is_never_overwritten(self):
        self.stage({'claude': 'claude-opus-5-5'})
        with self.assertRaises(SystemExit):
            self.stage({'claude': 'claude-sonnet-5'})               # same second: same name


class Engine:
    """Doubles for the engine-facing functions preconditions() calls; each attribute is one observable of the engine."""

    def __init__(self, old_sha):
        # The engine's own form, measured live 2026-09-24: an ISO time with a Z suffix, and no running_workflows key while idle.
        self.running = []; self.upcoming = (NOW + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.argument = [{'config_sha256': old_sha, 'mode': 'daily', 'obligation': tool.WATCH}]
        self.busy, self.idle = [], [{'id': 'office-watch-policy-1', 'type': 'DevelopmentTask'}]
        self.start_error = None

    async def temporal(self):
        return SimpleNamespace(name='client')

    async def raw_schedule(self, client):
        info = {'future_action_times': [self.upcoming] if self.upcoming else []}
        if self.running:
            info['running_workflows'] = self.running
        return {'info': info, 'schedule': {'action': {'start_workflow': {'input': 'x'}}}}

    async def schedule_argument(self, client):
        return SimpleNamespace(schedule='reference'), self.argument

    async def work_in_progress(self, client):
        return self.busy, self.idle

    async def delivered_histories(self, client, config):
        if self.start_error:
            raise ValueError(self.start_error)
        return {'office-result-1': {'source': 'engine'}}


class PreconditionTests(HostCase):
    def setUp(self):
        super().setUp()
        self.record, self.directory = self.stage({'claude': 'claude-opus-5-5'})
        self.engine = Engine(self.record['old_config_sha256']); self.way_back = True
        self.host.service.write_text(json.dumps({'config_sha256': self.record['old_config_sha256']}))
        fakes = {'temporal': self.engine.temporal, 'raw_schedule': self.engine.raw_schedule,
                 'schedule_argument': self.engine.schedule_argument, 'work_in_progress': self.engine.work_in_progress,
                 'alive': lambda service: {'daemon': 1, 'engine': 2, 'worker': 3}, 'plist': lambda path: b'new plist',
                 'startable': lambda config: self.way_back, 'check_unfinished_writers': lambda: None,
                 'check_private_processes': lambda: None}
        for name, value in fakes.items():
            patcher = patch.object(tool, name, value); patcher.start(); self.addCleanup(patcher.stop)
        for name, value in (('delivered_histories', self.engine.delivered_histories), ('archived_delivery', lambda config, name: {})):
            patcher = patch.object(tool.daemon, name, value); patcher.start(); self.addCleanup(patcher.stop)
        now = patch.object(tool, 'datetime', wraps=datetime); self.clock = now.start(); self.addCleanup(now.stop)
        self.clock.now.side_effect = lambda tz=None: NOW

    def check(self):
        return run(tool.preconditions(self.host.root, self.directory, self.record))

    def refused(self, fragment):
        with self.assertRaises(SystemExit) as caught:
            self.check()
        self.assertIn(fragment, str(caught.exception))

    def test_the_preconditions_hold_on_an_idle_host_and_name_the_idle_development_work(self):
        p = self.check()
        self.assertEqual(p['idle'], [{'id': 'office-watch-policy-1', 'type': 'DevelopmentTask'}])
        self.assertEqual(p['new']['development']['models'], {'claude': 'claude-opus-5-5'})

    def test_a_running_ap10_watch_refuses(self):
        self.engine.running = [{'workflow_id': 'watch'}]; self.refused('AP10 watch run is in progress')

    def test_the_next_ap10_run_too_close_or_unknown_refuses(self):
        for upcoming in ((NOW + timedelta(minutes=19)).strftime('%Y-%m-%dT%H:%M:%SZ'), None):
            with self.subTest(upcoming=upcoming):
                self.engine.upcoming = upcoming; self.refused('less than 20 minutes')

    def test_a_schedule_not_bound_to_the_active_selection_refuses(self):
        self.engine.argument = [{'config_sha256': 'f' * 64, 'mode': 'daily', 'obligation': tool.WATCH}]
        self.refused('not bound to the active selection')

    def test_a_service_that_is_not_the_recorded_one_refuses(self):
        self.host.service.write_text(json.dumps({'config_sha256': 'e' * 64})); self.refused('not the recorded one')

    def test_work_in_progress_refuses(self):
        self.engine.busy = [{'id': 'task-1', 'type': 'DevelopmentTask'}]; self.refused('work is in progress')

    def test_a_staged_release_whose_daemon_could_not_start_refuses(self):
        self.engine.start_error = 'history gone'; self.refused('could not pass its own daemon start requirements')

    def test_no_way_back_refuses_before_anything_is_stopped(self):
        """A switch that could leave the service down with nothing to restore is an operational risk for the owner to decide."""
        self.way_back = False; self.refused('no way back')

    def test_a_changed_staged_configuration_refuses(self):
        path = Path(self.record['config']); path.chmod(0o600); path.write_text(path.read_text() + ' ')
        self.refused('changed since staging')

    def test_an_active_selection_that_moved_since_staging_refuses(self):
        """Another release became active meanwhile: a valid pointer to another configuration, not a broken one."""
        moved = Path(self.record['config'])
        self.host.active.write_text(json.dumps({'config': str(moved), 'sha256': sha(moved.read_bytes())}))
        self.refused('the active selection changed since staging')

    def test_a_different_tool_refuses(self):
        self.record = dict(self.record, tool_sha256='0' * 64); self.refused('not the one that staged')


class ForwardTests(HostCase):
    """The activation after a completed stop, with launchctl, the engine and the backup replaced."""

    def setUp(self):
        super().setUp()
        self.record, record_directory = self.stage({'claude': 'claude-opus-5-5'})
        self.directory = record_directory / 'activation-20260924T080000Z'; self.directory.mkdir()
        (self.directory / 'old-active.json').write_bytes(self.host.active.read_bytes())
        (self.directory / 'old.plist').write_bytes(self.host.plist.read_bytes())
        self.schedule = {'info': {'future_action_times': ['t']}, 'schedule': {'action': {'start_workflow': {'input': 'old'}}}}
        (self.directory / 'before-schedule.json').write_text(json.dumps(self.schedule))
        self.host.service.write_text(json.dumps({'config_sha256': self.record['old_config_sha256']}))
        self.state = {'staged': self.record, 'old_config_sha256': self.record['old_config_sha256'],
                      'old_service': {k: {'pid': n, 'identity': 'i'} for n, k in enumerate(('daemon', 'engine', 'worker'))}}
        self.calls = []
        fakes = {'backup': lambda host, dest: {'sha256': 'b'}, 'plist': lambda path: b'new plist',
                 'bootstrap': lambda host: self.calls.append('bootstrap'), 'alive': lambda service: {'daemon': 1, 'engine': 2, 'worker': 3},
                 'start_diagnostics': lambda host: {}, 'raw_schedule': self.raw_schedule, 'complete_rebind': self.complete_rebind}
        for name, value in fakes.items():
            patcher = patch.object(tool, name, value); patcher.start(); self.addCleanup(patcher.stop)
        launchctl = patch.object(tool.subprocess, 'run', side_effect=lambda argv, **kw: self.calls.append(tuple(argv)) or SimpleNamespace(returncode=0))
        launchctl.start(); self.addCleanup(launchctl.stop)

    async def raw_schedule(self, client):
        return copy.deepcopy(self.schedule)

    async def complete_rebind(self, client, directory, staged):
        self.calls.append('rebind'); return True, [{'config_sha256': staged['sha256']}], None

    def forward(self, select, started):
        # forward() prints its result and its messages; the publication wrapper requires the suite's last line to be OK.
        with patch.object(tool, 'select', side_effect=select), patch.object(tool, 'started', side_effect=started), \
                contextlib.redirect_stdout(io.StringIO()):
            return run(tool.forward(self.host.root, copy.deepcopy(self.state), self.directory, {'point': 'stopped'}))

    def test_a_confirmed_start_rebinds_the_schedule_and_completes(self):
        def select(path):
            self.host.active.write_text(json.dumps({'config': str(path), 'sha256': sha(Path(path).read_bytes())}))
        async def started(host, expected, not_pids):
            self.assertEqual(expected, self.record['sha256'])
            return SimpleNamespace(), {'daemon': {}, 'engine': {}, 'worker': {}}
        self.forward(select, started)
        self.assertEqual(self.host.plist.read_bytes(), b'new plist')
        self.assertEqual(self.calls, ['bootstrap', 'rebind'])
        results = sorted(self.directory.glob('transition-result-*.json'))
        self.assertTrue(json.loads(results[-1].read_text())['completed'])

    def test_a_failed_start_restores_and_restarts_the_previous_release(self):
        old_active, old_plist = self.host.active.read_bytes(), self.host.plist.read_bytes()
        seen = []
        def select(path):
            self.host.active.write_text(json.dumps({'config': str(path), 'sha256': 'new'}))
        async def started(host, expected, not_pids):
            seen.append(expected)
            if expected == self.record['sha256']:
                raise RuntimeError('new release did not start')
            return SimpleNamespace(), {'config_sha256': expected}
        with self.assertRaises(SystemExit) as caught:
            self.forward(select, started)
        self.assertIn('activation failed', str(caught.exception))
        self.assertEqual(self.host.active.read_bytes(), old_active, 'the previous selection is back on disk')
        self.assertEqual(self.host.plist.read_bytes(), old_plist, 'and so is its launch definition')
        self.assertEqual(seen, [self.record['sha256'], self.record['old_config_sha256']], 'the previous release was started and confirmed')
        self.assertNotIn('rebind', self.calls, 'the AP10 schedule is never rebound on a failed start')
        self.assertEqual(json.loads((self.directory / 'rollback.json').read_text())['restored_service'],
                         {'config_sha256': self.record['old_config_sha256']})


class SafetyStepTests(HostCase):
    """The steps around the stop, each on its own: the backup, the offline start check, the stop and the confirmed start."""

    def test_the_backup_is_a_consistent_checked_copy_of_the_database(self):
        database = self.host.root / '.runtime/runtime.sqlite'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE t (v)'); db.execute("INSERT INTO t VALUES ('kept')")
        receipt = tool.backup(self.host.root, self.host.root / 'copy.sqlite')
        self.assertEqual(receipt['integrity'], 'ok'); self.assertEqual(receipt['tables'], [('t',)])
        with sqlite3.connect(self.host.root / 'copy.sqlite') as db:
            self.assertEqual(db.execute('SELECT v FROM t').fetchall(), [('kept',)])

    def test_startable_is_the_release_offline_archive_check_and_any_failure_is_no(self):
        seen = []
        with patch.object(tool.daemon, 'archived_delivery', side_effect=lambda config, name: seen.append(name)):
            self.assertTrue(tool.startable({'directory': 'r'}))
        self.assertEqual(seen, list(tool.daemon.HISTORICAL))
        with patch.object(tool.daemon, 'archived_delivery', side_effect=ValueError('archive gone')):
            self.assertFalse(tool.startable({'directory': 'r'}))

    def stop(self, alive, returncode):
        state = {'old_service': {k: {'pid': n, 'identity': 'i'} for n, k in enumerate(('daemon', 'engine', 'worker'))}}
        directory = self.host.root / 'activation'; directory.mkdir(exist_ok=True)
        for name in ('interruption.json', 'bootout.json'):
            (directory / name).unlink(missing_ok=True)
        clock = iter(range(0, 10000, 50))
        with patch.object(tool, 'alive', side_effect=alive), patch.object(tool.time, 'monotonic', side_effect=lambda: next(clock)), \
                patch.object(tool.asyncio, 'sleep', new=AsyncMock()), contextlib.redirect_stdout(io.StringIO()), \
                patch.object(tool.subprocess, 'run', return_value=SimpleNamespace(returncode=returncode, stderr='refused')) as launchctl:
            progress = {'point': 'stop requested'}
            run(tool.stop_service(state, directory, progress))
        self.assertEqual(launchctl.call_args[0][0][:2], ['launchctl', 'bootout'])
        return state, progress

    def test_a_clean_stop_records_when_the_old_processes_were_gone(self):
        answers = iter([{'daemon': 1, 'engine': 2, 'worker': 3}, {}, {}])
        state, progress = self.stop(lambda service: next(answers), 0)
        self.assertEqual(progress['point'], 'stopped; nothing selected'); self.assertIsNotNone(state['old_worker_gone_at'])

    def test_a_refused_stop_leaves_everything_running_and_says_so(self):
        with self.assertRaises(SystemExit) as caught:
            self.stop(lambda service: {'daemon': 1, 'engine': 2, 'worker': 3}, 1)
        self.assertIn('the stop was refused', str(caught.exception))

    def test_a_stop_that_leaves_processes_behind_refuses_before_anything_is_selected(self):
        with self.assertRaises(SystemExit) as caught:
            self.stop(lambda service: {'worker': 3}, 0)
        self.assertIn('still present after the stop', str(caught.exception))

    def test_a_start_counts_only_as_a_fresh_receipt_for_the_expected_selection_with_its_native_identity(self):
        receipt = {'config_sha256': 'new', 'identity_workflow': 'ap10-service-new', 'native_identity': {'n': 1},
                   **{k: {'pid': 10 + n, 'identity': 'fresh'} for n, k in enumerate(('daemon', 'engine', 'worker'))}}
        self.host.service.write_text(json.dumps(receipt))

        async def temporal():
            async def query(name):
                return {'n': 1}
            return SimpleNamespace(get_workflow_handle=lambda name: SimpleNamespace(query=query))
        with patch.object(tool, 'temporal', temporal), patch.object(tool, 'alive', return_value={'daemon': 1, 'engine': 2, 'worker': 3}):
            client, found = run(tool.started(self.host.root, 'new', {(1, 'old')}))
            self.assertEqual(found['config_sha256'], 'new')
            clock = iter(range(0, 10000, 100))
            for expected, not_pids in (('other', set()), ('new', {(10, 'fresh')})):
                with self.subTest(expected=expected, not_pids=not_pids), self.assertRaises(ValueError), \
                        patch.object(tool.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(tool.asyncio, 'sleep', new=AsyncMock()):
                    run(tool.started(self.host.root, expected, not_pids))


class CompleteRebindTests(unittest.TestCase):
    """Whether to rebind at all is judged against the schedule as it was before the stop."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.directory = Path(self.temp.name)
        self.before = {'info': {}, 'schedule': {'spec': 'daily', 'action': {'start_workflow': {'input': 'old'}}}}
        (self.directory / 'before-schedule.json').write_text(json.dumps(self.before))
        self.staged = {'old_config_sha256': 'o', 'sha256': 'n'}

    def complete(self, now, current):
        calls = []
        async def raw_schedule(client):
            return now
        async def schedule_argument(client):
            return SimpleNamespace(schedule='reference'), current
        async def rebind(client, old_arg, new_sha, reference):
            calls.append((old_arg, new_sha)); return True, 'rebound', None
        with patch.object(tool, 'raw_schedule', raw_schedule), patch.object(tool, 'schedule_argument', schedule_argument), \
                patch.object(tool, 'rebind', rebind):
            return run(tool.complete_rebind(None, self.directory, self.staged)), calls

    def test_an_unchanged_schedule_is_rebound_in_its_config_hash(self):
        old = [{'config_sha256': 'o', 'mode': 'daily', 'obligation': tool.WATCH}]
        now = copy.deepcopy(self.before); now['schedule']['action']['start_workflow']['input'] = 'encoded'
        (done, actual, error), calls = self.complete(now, old)
        self.assertTrue(done); self.assertEqual(calls, [(old, 'n')])

    def test_an_already_rebound_schedule_is_left_alone(self):
        (done, actual, error), calls = self.complete(copy.deepcopy(self.before), [{'config_sha256': 'n', 'mode': 'daily', 'obligation': tool.WATCH}])
        self.assertTrue(done); self.assertEqual(calls, [])

    def test_a_changed_or_running_schedule_is_not_rebound(self):
        changed = copy.deepcopy(self.before); changed['schedule']['spec'] = 'hourly'
        running = copy.deepcopy(self.before); running['info']['running_workflows'] = [{'id': 'watch'}]
        for now in (changed, running):
            with self.subTest(now=now):
                (done, actual, error), calls = self.complete(now, [{'config_sha256': 'o', 'mode': 'daily', 'obligation': tool.WATCH}])
                self.assertFalse(done); self.assertEqual(calls, [])


class WorkInProgressTests(unittest.TestCase):
    def test_pending_work_is_busy_and_idle_development_work_is_named(self):
        executions = [SimpleNamespace(id='ap10-service-1', run_id='a', workflow_type='ServiceIdentity'),
                      SimpleNamespace(id='office-watch-policy-1', run_id='b', workflow_type='DevelopmentTask'),
                      SimpleNamespace(id='task-2', run_id='c', workflow_type='DevelopmentTask'),
                      SimpleNamespace(id='watch-3', run_id='d', workflow_type='PrivateWatch')]
        pending = {'task-2': (['activity'], False), 'watch-3': ([], True)}

        class Raw:
            def __init__(self, name):
                self.pending_activities, self.task = pending.get(name, ([], False))
            def HasField(self, field):
                return field == 'pending_workflow_task' and self.task

        class Client:
            async def list_workflows(self, query):
                assert query == 'ExecutionStatus = "Running"'
                for execution in executions:
                    yield execution
            def get_workflow_handle(self, name, run_id=None):
                async def describe():
                    return SimpleNamespace(raw_description=Raw(name))
                return SimpleNamespace(describe=describe)
        busy, idle = run(tool.work_in_progress(Client()))
        self.assertEqual([b['id'] for b in busy], ['task-2', 'watch-3'])
        self.assertEqual(idle, [{'id': 'office-watch-policy-1', 'type': 'DevelopmentTask'}])


class RebindTests(unittest.TestCase):
    """Only the config hash of the AP10 schedule action may change, and not while it runs or has changed."""

    def schedule(self, argument):
        return SimpleNamespace(spec='daily 07:00', policy='p', state='s', action=SimpleNamespace(args=argument))

    def client(self, observed, running=()):
        updates = []

        class Handle:
            async def update(self, callback):
                inp = SimpleNamespace(description=SimpleNamespace(schedule=observed, info=SimpleNamespace(running_actions=list(running))))
                result = await callback(inp)
                if result is not None:
                    updates.append(result); observed.action.args = result.schedule.action.args

        async def decode(args):
            return args

        async def describe():
            return SimpleNamespace(schedule=observed)
        handle = Handle(); handle.describe = describe
        return SimpleNamespace(get_schedule_handle=lambda name: handle, data_converter=SimpleNamespace(decode=decode)), updates

    def test_only_the_config_hash_changes(self):
        old = [{'config_sha256': 'o', 'mode': 'daily', 'obligation': tool.WATCH}]
        observed = self.schedule(copy.deepcopy(old)); client, updates = self.client(observed)
        done, actual, error = run(tool.rebind(client, old, 'n', SimpleNamespace(schedule=self.schedule(old))))
        self.assertTrue(done); self.assertIsNone(error)
        self.assertEqual(actual, [{'config_sha256': 'n', 'mode': 'daily', 'obligation': tool.WATCH}])
        self.assertEqual((observed.spec, observed.policy, observed.state), ('daily 07:00', 'p', 's'))

    def test_a_running_or_changed_schedule_is_not_rebound(self):
        old = [{'config_sha256': 'o', 'mode': 'daily', 'obligation': tool.WATCH}]
        for running, argument in (([1], copy.deepcopy(old)), ((), [{'config_sha256': 'x', 'mode': 'daily', 'obligation': tool.WATCH}])):
            with self.subTest(running=running, argument=argument), patch.object(tool.asyncio, 'sleep', new=AsyncMock()):
                observed = self.schedule(argument); client, updates = self.client(observed, running)
                done, actual, error = run(tool.rebind(client, old, 'n', SimpleNamespace(schedule=self.schedule(old))))
                self.assertFalse(done); self.assertEqual(updates, [])


if __name__ == '__main__':
    unittest.main()
