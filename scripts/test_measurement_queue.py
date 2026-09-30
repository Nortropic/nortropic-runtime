"""The queue between sessions and the fixed measurement script (D042): what the agent runs, and nothing else.

sudo is never run here: the agent's runner is a double that records the exact argument list; the installation check is
exercised on real files; the session's side queues a real bundle of a real repository.
"""
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts import matning_provanvandare as fast
from scripts import measurement_queue as queue

ME = pwd.getpwuid(os.getuid()).pw_name


class QueueCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); os.umask(0o022)
        (self.root / 'Shared').mkdir(); (self.root / 'provhem').mkdir(); (self.root / 'host/.runtime/ap10').mkdir(parents=True)
        self.plats = fast.Plats(inkorg=self.root / 'Shared/nortropic-matning/in', provhem=self.root / 'provhem', prov=ME, agare=ME)
        self.host = self.root / 'host'
        self.repo = self.root / 'repo'; self.repo.mkdir()
        for args in (['init', '-q', '-b', 'main'], ['commit', '-q', '--allow-empty', '-m', 'one']):
            subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True)
        self.calls = []

    def runner(self, code=0):
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, code, stdout='{"returncode": 0}', stderr='')
        return run

    def queued(self):
        return queue.begar('runtime', self.repo, 'refs/heads/main', 3, plats=self.plats)


class SessionSideTests(QueueCase):
    def test_a_request_is_complete_before_it_is_visible_and_names_exactly_the_branch(self):
        ident = self.queued()
        self.assertRegex(ident, r'^runtime-[0-9a-f]{12}-\d{8}t\d{6}z$')
        request = json.loads((self.plats.inkorg / ident / 'begaran.json').read_text())
        head = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        self.assertEqual((request['candidate'], request['ref'], request['expected_test_count']), (head, 'refs/heads/main', 3))
        self.assertEqual(oct((self.plats.inkorg / ident).stat().st_mode & 0o777), '0o755')
        self.assertEqual(queue.pending(self.plats), [ident])

    def test_only_a_full_branch_name_and_a_known_repository(self):
        for repo, ref in (('other', 'refs/heads/main'), ('runtime', 'main'), ('runtime', 'refs/heads/../x')):
            with self.assertRaises(SystemExit):
                queue.begar(repo, self.repo, ref, None, plats=self.plats)

    def test_an_inbox_others_can_write_is_refused(self):
        self.plats.inkorg.parent.mkdir(mode=0o777); self.plats.inkorg.parent.chmod(0o777)
        with self.assertRaisesRegex(SystemExit, 'only you can write'):
            self.queued()

    def test_waiting_returns_the_result_and_copies_what_sealing_needs(self):
        ident = self.queued(); out = self.plats.ut / ident
        def finish():
            time.sleep(.3); out.mkdir(parents=True)
            for name in ('suite.json', 'suite.log', 'gransprob.json'):
                (out / name).write_text(name)
            (out / 'klar.json').write_text('{"returncode": 0}')
        threading.Thread(target=finish).start()
        value = queue.vanta(ident, tid=10, till=self.root / 'kopia', plats=self.plats, sov=.1)
        self.assertEqual(value, {'returncode': 0})
        self.assertEqual(sorted(p.name for p in (self.root / 'kopia').iterdir()), ['gransprob.json', 'klar.json', 'suite.json', 'suite.log'])

    def test_waiting_stops_when_the_agent_tried_and_left_nothing_or_time_runs_out(self):
        ident = self.queued()
        with self.assertRaisesRegex(SystemExit, 'no result'):
            queue.vanta(ident, tid=0, plats=self.plats, sov=.01)
        (self.plats.inkorg / ident / 'agent.json').write_text('{"returncode": 2, "stderr_tail": "VÄGRAR"}')
        with self.assertRaisesRegex(SystemExit, 'left no result'):
            queue.vanta(ident, tid=10, plats=self.plats, sov=.01)


class AgentSideTests(QueueCase):
    def test_nothing_is_run_before_the_owner_installed_the_test_user_and_the_root_owned_script(self):
        ident = self.queued()
        state = queue.run_pending(self.host, plats=self.plats, runner=self.runner(), skript=self.root / 'saknas')
        self.assertEqual((state['state'], state['queued'], self.calls), ('not_installed', [ident], []))
        status = json.loads((self.host / '.runtime/ap10/measurement-status.json').read_text())
        self.assertEqual(status['schema'], 'measurement-queue-status/1')

    def test_a_script_the_owner_could_change_is_not_the_installed_one(self):
        own = self.root / 'matning'; own.write_text('x')          # owned by this account, not root
        self.assertFalse(queue.installed(self.plats, own))

    def test_each_queued_request_runs_through_exactly_the_one_rule(self):
        first = self.queued(); time.sleep(1.1); second = self.queued()
        with patch.object(queue, 'installed', lambda plats, skript: True):
            state = queue.run_pending(self.host, plats=self.plats, runner=self.runner(), skript=queue.SKRIPT)
        self.assertEqual([c[0] for c in self.calls],
                         [['/usr/bin/sudo', '-n', '-u', ME, '/usr/local/libexec/nortropic/matning', 'mat', ident]
                          for ident in (first, second)])
        self.assertEqual(self.calls[0][1]['stdin'], subprocess.DEVNULL)
        self.assertEqual(state['state'], 'measured')
        for ident in (first, second):
            record = json.loads((self.plats.inkorg / ident / 'agent.json').read_text())
            self.assertEqual(record['returncode'], 0)
        self.assertEqual(queue.pending(self.plats), [])             # tried once; the result or agent.json ends it

    def test_the_budget_ends_a_look_and_the_rest_waits(self):
        self.queued(); time.sleep(1.1); later = self.queued()
        with patch.object(queue, 'installed', lambda plats, skript: True):
            state = queue.run_pending(self.host, plats=self.plats, runner=self.runner(), budget=-1, skript=queue.SKRIPT)
        self.assertEqual(self.calls, []); self.assertEqual(state['state'], 'idle'); self.assertIn(later, state['queued'])

    def test_a_measurement_that_hangs_is_recorded_as_such(self):
        ident = self.queued()
        def hang(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        with patch.object(queue, 'installed', lambda plats, skript: True):
            queue.run_pending(self.host, plats=self.plats, runner=hang, skript=queue.SKRIPT)
        record = json.loads((self.plats.inkorg / ident / 'agent.json').read_text())
        self.assertIsNone(record['returncode']); self.assertIn('exceeded', record['stderr_tail'])

    def test_each_measurement_starts_only_with_a_whole_measurement_of_room_before_the_watch(self):
        first = self.queued(); time.sleep(1.1); second = self.queued()
        asked = []
        def quiet(margin):
            asked.append(margin)
            if len(asked) == 2:
                raise SystemExit('REFUSED: the next AP10 run is less than 20 minutes away (with room for heavy work: 5400 s)')
        with patch.object(queue, 'installed', lambda plats, skript: True):
            state = queue.run_pending(self.host, plats=self.plats, runner=self.runner(), skript=queue.SKRIPT, quiet=quiet)
        self.assertEqual(asked, [queue.MEASURE_LIMIT, queue.MEASURE_LIMIT])
        self.assertEqual([c[0][-1] for c in self.calls], [first])
        self.assertEqual((state['state'], state['queued']), ('measured', [second]))       # the first ran; the second waits
        self.assertIn('less than 20 minutes', state['reason'])
        self.assertGreater(queue.MEASURE_LIMIT, 300 + 600 + 5 * 60 + 2 * 900 + 1800)   # the fixed script's own limits

    def test_nothing_is_measured_while_the_watch_is_near(self):
        ident = self.queued()
        def near(margin):
            raise RuntimeError('the next AP10 run is less than 20 minutes away')
        with patch.object(queue, 'installed', lambda plats, skript: True):
            state = queue.run_pending(self.host, plats=self.plats, runner=self.runner(), skript=queue.SKRIPT, quiet=near)
        self.assertEqual((state['state'], state['queued'], self.calls), ('waiting', [ident], []))
        self.assertIn('20 minutes', state['reason'])

    def test_a_digitala_request_carries_a_view_of_the_active_runtime_release_without_its_private_files(self):
        host = self.root / 'runtimehost'; release = host / '.runtime/ap10/releases/r1'
        files = {'runtime/runtime/web_critique.py': b'x\n', 'context/owner.md': b'private\n', 'history/h.json': b'{}\n'}
        for name, data in files.items():
            (release / name).parent.mkdir(parents=True, exist_ok=True); (release / name).write_bytes(data)
        import hashlib
        config = json.dumps({'files': {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
        (release / 'config.json').write_bytes(config); (host / '.runtime/temporal-venv').mkdir(parents=True)
        (host / '.runtime/ap10/active.json').write_text(json.dumps({'config': str(release / 'config.json'),
                                                                    'sha256': hashlib.sha256(config).hexdigest()}))
        plats = fast.Plats(inkorg=self.plats.inkorg, provhem=self.plats.provhem, prov=ME, agare=ME, runtime=host)
        ident = queue.begar('digitala', self.repo, 'refs/heads/main', None, plats=plats)
        view = self.plats.inkorg / ident / 'runtime-vy'
        pointer = json.loads((view / '.runtime/ap10/active.json').read_text())
        self.assertEqual(Path(pointer['config']).read_bytes(), config)
        self.assertTrue(Path(pointer['config']).is_relative_to(view))
        self.assertTrue((view / '.runtime/ap10/releases/r1/runtime/runtime/web_critique.py').is_file())
        self.assertEqual((view / 'runtime/web_critique.py').read_bytes(), b'x\n')      # as a checkout has it
        self.assertFalse((view / '.runtime/ap10/releases/r1/context').exists())
        self.assertFalse((view / '.runtime/ap10/releases/r1/history').exists())
        env = fast.miljo(plats, fast.PROFILER['digitala'], self.root / 'w', self.root / 'w/repo', self.plats.inkorg / ident) \
            if (self.root / 'w').mkdir() is None else None
        self.assertEqual(env['NR_HOST_ROOT'], str(view))

    def test_a_directory_that_is_not_a_request_is_ignored(self):
        self.plats.inkorg.mkdir(parents=True)
        for name in ('UPPER', 'x..y', 'ok-but-empty'):
            (self.plats.inkorg / name).mkdir()
        self.assertEqual(queue.pending(self.plats), [])

    def test_two_agents_never_measure_together(self):
        import fcntl
        with (self.host / '.runtime/ap10/measurement.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertIsNone(queue.run_pending(self.host, plats=self.plats, runner=self.runner()))


class QuietRuleTests(unittest.TestCase):
    """model_choice.ap10_quiet: heavy work waits while the watch runs or is near; a far run lets it through."""

    def run_with(self, info, margin):
        import asyncio
        from datetime import datetime, timedelta, timezone
        from scripts import model_choice as tool
        async def temporal():
            return None
        async def raw_schedule(client):
            return {'info': info(datetime.now(timezone.utc), timedelta)}
        with patch.object(tool, 'temporal', temporal), patch.object(tool, 'raw_schedule', raw_schedule):
            return asyncio.run(tool.ap10_quiet(margin)), tool

    def test_a_run_in_progress_a_near_or_unknown_run_waits_and_a_far_one_does_not(self):
        z = lambda t: t.isoformat().replace('+00:00', 'Z')
        with self.assertRaisesRegex(SystemExit, 'in progress; heavy work waits'):
            self.run_with(lambda now, d: {'running_workflows': [{}], 'future_action_times': [z(now + d(days=1))]}, 0)
        with self.assertRaisesRegex(SystemExit, 'less than 20 minutes away'):
            self.run_with(lambda now, d: {'future_action_times': [z(now + d(seconds=1200 + 100))]}, 900)
        with self.assertRaisesRegex(SystemExit, 'less than 20 minutes away'):
            self.run_with(lambda now, d: {}, 0)
        value, tool = self.run_with(lambda now, d: {'future_action_times': [z(now + d(seconds=1200 + 1000))]}, 900)
        self.assertTrue(value.endswith('Z'))

    def test_an_engine_that_cannot_be_asked_is_a_wait(self):
        import asyncio
        from scripts import model_choice as tool
        async def down():
            raise OSError('connection refused')
        with patch.object(tool, 'temporal', down):
            with self.assertRaisesRegex(SystemExit, 'could not be read.*heavy work waits'):
                asyncio.run(tool.ap10_quiet(0))


class TickTests(unittest.TestCase):
    """The agent's look: the choice, then the measurements; a failing part never stops the next, and the file is unchanged."""

    def test_a_failing_choice_does_not_stop_the_measurements(self):
        import contextlib, io
        from scripts import model_choice as tool
        seen = []
        async def broken(host):
            raise RuntimeError('the engine could not be asked')
        def measure(host, quiet=None):
            seen.append(('measure', host, callable(quiet)))
        out = io.StringIO()
        with patch.object(tool, 'automatic', broken), patch.object(queue, 'run_pending', measure), contextlib.redirect_stdout(out):
            tool.tick('/h')
        self.assertEqual(seen, [('measure', '/h', True)])
        self.assertIn('choice: unexpected', out.getvalue())

    def test_the_agent_file_is_the_one_d040_installed(self):
        from scripts import model_choice as tool
        self.assertIn('model_choice.py" auto', tool.agent_plist('/h')['ProgramArguments'][2])
        self.assertEqual(tool.AGENT_INTERVAL, 300)


if __name__ == '__main__':
    unittest.main()
