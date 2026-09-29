"""Release binding and native schedule definition, isolated fixtures only."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from temporalio.service import RPCError, RPCStatusCode
from scripts import install_ap10
from runtime.scheduled_operation import operation
from runtime.operation_schedule import definition
from runtime.operation_schedule import execution_status, operate


class ScheduledOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = {'directory': str(self.home), 'config_sha256': 'a' * 64, 'files': {},
            'scheduled_operations': {'accepted-case': {'input': 'operations/accepted-case.json', 'interval_seconds': 300}}}
        for name in ('operations/accepted-case.json', 'office/tools/driftoperation.py'):
            p = self.home / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{}')
            self.config['files'][name] = sha256(p.read_bytes()).hexdigest()
        self.request = {'operation': 'accepted-case', 'config_sha256': 'a' * 64}

    def test_exact_binding_and_paused_bounded_definition(self):
        self.assertEqual(operation(self.config, self.request)[0], self.home / 'operations/accepted-case.json')
        schedule = definition(self.config, 'accepted-case')
        self.assertTrue(schedule.state.paused)
        self.assertEqual(schedule.action.task_queue, 'office-operations')
        self.assertEqual(schedule.action.retry_policy.maximum_attempts, 1)
        self.assertEqual(schedule.policy.catchup_window.total_seconds(), 60)

    def test_unknown_id_release_tamper_and_input_refused(self):
        for request in ({**self.request, 'operation': 'other'}, {**self.request, 'config_sha256': 'b' * 64},
                        {**self.request, 'path': '/tmp/command'}):
            with self.assertRaises(ValueError): operation(self.config, request)
        (self.home / 'office/tools/driftoperation.py').write_text('changed')
        with self.assertRaises(ValueError): operation(self.config, self.request)

    def test_no_arbitrary_path_interval_or_symlink(self):
        for change in ({'input': '../outside.json'}, {'interval_seconds': 1}, {'interval_seconds': True}):
            config = copy.deepcopy(self.config); config['scheduled_operations']['accepted-case'].update(change)
            with self.assertRaises(ValueError): operation(config, self.request)
        path = self.home / 'operations/accepted-case.json'; path.unlink(); path.symlink_to(self.home / 'office/tools/driftoperation.py')
        with self.assertRaises(ValueError): operation(self.config, self.request)


class ExecutionObservationTests(unittest.IsolatedAsyncioTestCase):
    def observed(self, count=1):
        now = datetime.now(timezone.utc)
        return NS(info=NS(recent_actions=[NS(action=NS(workflow_id='work-' + str(i),
            first_execution_run_id='run-' + str(i)), scheduled_at=now, started_at=now)
            for i in range(count)]))

    async def test_missing_history_timeout_and_later_success_are_distinct(self):
        missing = NS(describe=AsyncMock(side_effect=RPCError('expired', RPCStatusCode.NOT_FOUND, b'')))
        slow = NS(describe=AsyncMock(return_value=NS(status=NS(name='COMPLETED'))),
                  result=AsyncMock(side_effect=TimeoutError()))
        healthy = NS(describe=AsyncMock(return_value=NS(status=NS(name='COMPLETED'))),
                     result=AsyncMock(return_value={'result': {'completed': True}}))
        client = NS(get_workflow_handle=Mock(side_effect=[missing, slow, healthy]))
        rows = await execution_status(client, self.observed(3))
        self.assertEqual(rows[0]['status'], 'unavailable')
        self.assertEqual(rows[0]['observation_error'], 'RPCError')
        self.assertIsNone(rows[0]['business_completed'])
        self.assertEqual(rows[1]['status'], 'COMPLETED')
        self.assertEqual(rows[1]['observation_error'], 'TimeoutError')
        self.assertIsNone(rows[1]['business_completed'])
        self.assertTrue(rows[2]['business_completed'])

    async def test_stop_retains_successful_native_mutation_when_history_expired(self):
        description = self.observed()
        description.schedule = NS(state=NS(paused=False, note=''))
        description.info.num_actions = 1
        description.info.num_actions_missed_catchup_window = 0
        description.info.num_actions_skipped_overlap = 0
        description.info.running_actions = []
        description.info.next_action_times = []
        async def pause(note):
            description.schedule.state.paused = True
            description.schedule.state.note = note
        schedule = NS(describe=AsyncMock(return_value=description), pause=AsyncMock(side_effect=pause))
        expired = NS(describe=AsyncMock(side_effect=RPCError('expired', RPCStatusCode.NOT_FOUND, b'')))
        client = NS(get_schedule_handle=Mock(return_value=schedule), get_workflow_handle=Mock(return_value=expired))
        service = AsyncMock(); service.__aenter__.return_value = client
        with patch('runtime.operation_schedule.require_active_code', return_value={'config_sha256': 'a'*64}), \
             patch('runtime.operation_schedule.definition'), patch('runtime.operation_schedule.validate', new=AsyncMock()), \
             patch('runtime.operation_schedule.SharedService', return_value=service):
            receipt = await operate('stop', 'accepted-case')
        schedule.pause.assert_awaited_once()
        self.assertTrue(receipt['paused'])
        self.assertTrue(receipt['note'].startswith('STOPPED'))
        self.assertEqual(receipt['recent_executions'][0]['status'], 'unavailable')


if __name__ == '__main__': unittest.main()


class WeeklyBoundTests(unittest.TestCase):
    """The wakeup's bounds and the release binding an operation can actually use."""

    def test_bounds_are_ordered_and_the_schedule_carries_the_outermost(self):
        from runtime.scheduled_operation import (ACTIVITY_BOUND, SCHEDULE_TO_CLOSE_BOUND,
                                                 EXECUTION_BOUND, HEARTBEAT_BOUND)
        self.assertLess(HEARTBEAT_BOUND, ACTIVITY_BOUND)
        self.assertLess(ACTIVITY_BOUND, SCHEDULE_TO_CLOSE_BOUND)
        self.assertLess(SCHEDULE_TO_CLOSE_BOUND, EXECUTION_BOUND)
        # Office's own BOUND_SECONDS is deliberately NOT copied here. A second copy of
        # that number would drift, and this suite cannot see the Office repository.
        # probe_veckodrift.py reads BOUND_SECONDS out of the handler bytes actually
        # under test and refuses the qualification when the relation does not hold.
        home = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, home)
        config = {'directory': str(home), 'config_sha256': 'a' * 64, 'files': {},
                  'scheduled_operations': {'weekly-case': {'input': 'operations/weekly-case.json',
                                                           'interval_seconds': 3600}}}
        for name in ('operations/weekly-case.json', 'office/tools/driftoperation.py'):
            path = home / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{}')
            config['files'][name] = sha256(path.read_bytes()).hexdigest()
        schedule = definition(config, 'weekly-case')
        self.assertEqual(schedule.action.execution_timeout.total_seconds(), EXECUTION_BOUND)
        self.assertEqual(schedule.spec.intervals[0].every.total_seconds(), 3600)


class ReleaseOperationBindingTests(unittest.TestCase):
    """bind_operations must produce exactly what scheduled_operation.operation accepts."""

    def setUp(self):
        # Under the repository, not /var: the reviewed staging checks refuse a
        # symlinked ancestor, and on macOS /var itself is one.
        scratch = Path('.scratch'); scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).absolute()
        self.release = self.home / 'release'; self.release.mkdir()
        handler = self.release / 'office/tools/driftoperation.py'
        handler.parent.mkdir(parents=True); handler.write_text('# reviewed handler\n')
        self.files = {'office/tools/driftoperation.py': sha256(handler.read_bytes()).hexdigest()}
        self.input = self.home / 'reviewed-input.json'
        self.write_input({'schema': 'office-drift/1', 'state': str(self.home / 'private'),
                          'period_seconds': 604800, 'drift': dict(self.DRIFT)})
        self.manifest = self.home / 'operations.json'
        self.write_manifest({'digitala-vecka': {'input': str(self.input), 'interval_seconds': 3600}})

    # A complete drift channel, because staging now refuses a partial one: the handler
    # needs every one of these keys to start a frozen tool at all.
    DRIFT = {'digitala_root': '/abs/frozen',
             'digitala_files': {'verktyg/drift_kontroll.py': 'a' * 64},
             'python_path': '/abs/python', 'python_sha256': 'd' * 64,
             'plan': '/abs/DRIFT.json', 'plan_sha256': 'e' * 64, 'receipts': '/abs/kund'}
    INTAKE = {'digitala_root': '/abs/frozen',
              'digitala_files': {'verktyg/kundstart.py': 'b' * 64},
              'python_path': '/abs/python', 'python_sha256': 'd' * 64,
              'base_url': 'https://k.example', 'key_file': '/abs/k.secret',
              'customer': '/abs/kund', 'executor': 'runtime-veckodrift'}

    def write_input(self, value):
        self.input.write_text(json.dumps(value))

    def write_manifest(self, value):
        self.manifest.write_text(json.dumps(value))

    def bind(self):
        # A release is staged once into a fresh directory; each call gets its own.
        self.release = self.home / ('release-' + str(len(list(self.home.glob('release*')))))
        handler = self.release / 'office/tools/driftoperation.py'
        handler.parent.mkdir(parents=True)
        handler.write_text('# reviewed handler\n')
        self.files = {'office/tools/driftoperation.py': sha256(handler.read_bytes()).hexdigest()}
        return install_ap10.bind_operations(self.release, self.files, self.manifest)

    def test_rebinding_a_name_in_place_is_refused(self):
        self.bind()
        with self.assertRaises(ValueError):
            install_ap10.bind_operations(self.release, self.files, self.manifest)

    def test_bound_operation_is_accepted_by_the_runtime_validator(self):
        bound = self.bind()
        self.assertEqual(bound, {'digitala-vecka': {'input': 'operations/digitala-vecka.json',
                                                    'interval_seconds': 3600}})
        copied = self.release / 'operations/digitala-vecka.json'
        self.assertEqual(copied.read_bytes(), self.input.read_bytes())
        self.assertEqual(stat.S_IMODE(copied.stat().st_mode), 0o444)
        self.assertEqual(self.files['operations/digitala-vecka.json'],
                         sha256(copied.read_bytes()).hexdigest())
        # The round trip is the point: a staged release must be runnable, which the
        # injected qualification configuration never proved for the installer.
        config = {'directory': str(self.release), 'config_sha256': 'c' * 64,
                  'files': self.files, 'scheduled_operations': bound}
        selected, handler = operation(config, {'operation': 'digitala-vecka',
                                               'config_sha256': 'c' * 64})
        self.assertEqual(selected, copied)
        self.assertEqual(handler, self.release / 'office/tools/driftoperation.py')
        self.assertEqual(json.loads(selected.read_text())['period_seconds'], 604800)

    def test_manifest_entry_shape_name_and_interval_are_closed(self):
        for manifest in ({}, {'Digitala': {'input': str(self.input), 'interval_seconds': 3600}},
                         {'-bad': {'input': str(self.input), 'interval_seconds': 3600}},
                         {'ok': {'input': str(self.input)}},
                         {'ok': {'input': str(self.input), 'interval_seconds': 3600, 'extra': 1}},
                         {'ok': {'input': str(self.input), 'interval_seconds': 59}},
                         {'ok': {'input': str(self.input), 'interval_seconds': 86401}},
                         {'ok': {'input': str(self.input), 'interval_seconds': True}},
                         {'ok': {'input': 'reviewed-input.json', 'interval_seconds': 3600}},
                         {'ok': [str(self.input), 3600]}):
            self.write_manifest(manifest)
            with self.assertRaises(ValueError): self.bind()
        self.write_manifest({'a%d' % i: {'input': str(self.input), 'interval_seconds': 3600}
                             for i in range(9)})
        with self.assertRaises(ValueError): self.bind()

    def test_foreign_schema_relative_state_and_empty_input_are_refused(self):
        for value in ({'schema': 'other/1', 'state': str(self.home / 'private')},
                      {'schema': 'office-drift/1', 'state': 'private'},
                      {'schema': 'office-drift/1'},
                      ['office-drift/1']):
            self.write_input(value)
            with self.assertRaises(ValueError): self.bind()
        self.input.write_bytes(b'')
        with self.assertRaises(ValueError): self.bind()

    def test_a_symlinked_manifest_or_input_is_refused(self):
        link = self.home / 'linked-input.json'; link.symlink_to(self.input)
        self.write_manifest({'ok': {'input': str(link), 'interval_seconds': 3600}})
        with self.assertRaises(ValueError): self.bind()
        linked_manifest = self.home / 'linked-operations.json'
        linked_manifest.symlink_to(self.manifest)
        self.manifest = linked_manifest
        with self.assertRaises(ValueError): self.bind()

    def test_operations_require_the_reviewed_office_handler_in_the_release(self):
        release = self.home / 'utan-hanterare'; release.mkdir()
        with self.assertRaises(ValueError):
            install_ap10.bind_operations(release, {}, self.manifest)

    def test_staging_without_operations_leaves_the_key_absent(self):
        with patch.object(install_ap10, 'copy_code', return_value={'AGENTS.md': 'a' * 64}), \
             patch.object(install_ap10, 'instruction_guards', return_value={}), \
             patch.object(install_ap10, 'ROOT', self.home / 'host'):
            (self.home / 'host/.runtime/ap10').mkdir(parents=True)
            path = install_ap10.stage('a' * 40, 'b' * 40)
            self.assertNotIn('scheduled_operations', json.loads(Path(path).read_text()))

    def test_staging_refuses_an_operation_the_handler_could_only_refuse(self):
        # Otherwise a release could be staged, reviewed and activated carrying an
        # operation that can only ever fail, surfacing as a weekly incident instead.
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for value in (base,                                            # no channel
                      {**base, 'monitor': {}},                          # empty channel
                      {**base, 'drift': self.DRIFT, 'period_seconds': 60},
                      {**base, 'drift': self.DRIFT, 'period_seconds': 2678401},
                      {**base, 'drift': self.DRIFT, 'period_seconds': True},
                      {**base, 'drift': self.DRIFT, 'period_seconds': '604800'}):
            self.write_input(value)
            with self.assertRaises(ValueError): self.bind()

    def test_a_wakeup_slower_than_the_period_is_refused(self):
        # A period can only be kept by a wakeup that comes at least as often as it.
        self.write_input({'schema': 'office-drift/1', 'state': str(self.home / 'private'),
                          'drift': self.DRIFT, 'period_seconds': 3600})
        self.write_manifest({'ok': {'input': str(self.input), 'interval_seconds': 3601}})
        with self.assertRaises(ValueError): self.bind()
        self.write_manifest({'ok': {'input': str(self.input), 'interval_seconds': 3600}})
        self.assertEqual(self.bind()['ok']['interval_seconds'], 3600)

    def test_the_period_bounds_here_match_the_handler_the_release_binds(self):
        # Two copies of a bound is a drift risk; the qualification measures both
        # against the handler bytes under test. This only pins what staging enforces.
        self.assertEqual((install_ap10.PERIOD_FLOOR, install_ap10.PERIOD_CEILING),
                         (3600, 2678400))

    def test_a_probe_only_monitor_binding_cannot_reach_a_release(self):
        # Plain HTTP and isolated_test belong to a loopback probe. A staged release is
        # never one, so it is refused here rather than at the first weekly wakeup.
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        good = {'url': 'https://kund.example/api/health', 'candidate': 'a' * 40}
        for monitor in ({**good, 'url': 'http://kund.example/api/health'},
                        {**good, 'url': 'http://127.0.0.1:3131/api/health'},
                        {**good, 'isolated_test': True},
                        {**good, 'isolated_test': False},
                        {**good, 'url': 'https://u:p@kund.example/h'},
                        {**good, 'url': 'https://kund.example/h#frag'},
                        {**good, 'url': 'https:///h'},
                        {**good, 'candidate': 'A' * 40},
                        {**good, 'candidate': None}):
            self.write_input({**base, 'monitor': monitor})
            with self.assertRaises(ValueError): self.bind()
        self.write_input({**base, 'monitor': good})
        self.assertEqual(self.bind()['digitala-vecka']['interval_seconds'], 3600)

    def test_a_probe_flag_on_any_channel_is_refused(self):
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for channel in ('intake', 'drift'):
            whole = self.DRIFT if channel == 'drift' else self.INTAKE
            self.write_input({**base, channel: {**whole, 'isolated_test': True}})
            with self.assertRaises(ValueError): self.bind()
            self.write_input({**base, channel: whole})
            self.assertIn('digitala-vecka', self.bind())

    def test_an_incomplete_channel_binding_never_reaches_a_wakeup(self):
        # The handler needs every one of these to start a frozen tool at all, so a
        # release that omits one can only fail. Refuse it at staging instead.
        drift, intake = dict(self.DRIFT), dict(self.INTAKE)
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        self.write_input({**base, 'drift': drift, 'intake': intake})
        self.assertIn('digitala-vecka', self.bind())
        for channel, whole in (('drift', drift), ('intake', intake)):
            for key in whole:
                self.write_input({**base, channel: {k: v for k, v in whole.items() if k != key}})
                with self.assertRaises(ValueError): self.bind()
            for key in ('digitala_root', 'python_path'):
                self.write_input({**base, channel: {**whole, key: 'relativ/vag'}})
                with self.assertRaises(ValueError): self.bind()

    def test_a_candidate_that_is_not_a_string_is_refused_not_laundered(self):
        # str() would let an integer past and leave the handler to raise TypeError.
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for candidate in (int('1' * 40), None, ['a' * 40], True):
            self.write_input({**base, 'monitor': {'url': 'https://kund.example/health',
                                                  'candidate': candidate}})
            with self.assertRaises(ValueError): self.bind()

    def test_a_channel_must_freeze_the_tool_it_actually_starts(self):
        # The handler refuses a binding that freezes the wrong tool, so staging must
        # too - otherwise the release carries a channel that can only fail.
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for channel, wrong in (('drift', 'verktyg/kundstart.py'),
                               ('intake', 'verktyg/drift_kontroll.py')):
            whole = dict(self.DRIFT if channel == 'drift' else self.INTAKE)
            whole['digitala_files'] = {wrong: 'c' * 64}
            self.write_input({**base, channel: whole})
            with self.assertRaises(ValueError): self.bind()
            whole['digitala_files'] = {}
            self.write_input({**base, channel: whole})
            with self.assertRaises(ValueError): self.bind()

    def test_a_frozen_file_must_be_a_safe_relative_path_with_a_real_hash(self):
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        tool = 'verktyg/drift_kontroll.py'
        for files in ({tool: 'a' * 64, '/etc/passwd': 'b' * 64},
                      {tool: 'a' * 64, '../utanfor.py': 'b' * 64},
                      {tool: 'inte-en-hash'},
                      {tool: 'A' * 64},
                      {tool: None},
                      {tool: 'a' * 63}):
            self.write_input({**base, 'drift': {**self.DRIFT, 'digitala_files': files}})
            with self.assertRaises(ValueError): self.bind()

    def test_a_channel_that_is_not_an_object_is_refused_not_a_crash(self):
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for channel in ('intake', 'drift', 'monitor'):
            for given in ('en strang', ['lista'], 7):
                self.write_input({**base, channel: given})
                with self.assertRaises(ValueError): self.bind()

    def test_the_period_check_is_reached_after_every_channel_check(self):
        # Regression: an inner loop rebound the operation input, so the period check
        # silently tested membership in a hash string and never fired.
        self.write_input({'schema': 'office-drift/1', 'state': str(self.home / 'private'),
                          'drift': self.DRIFT, 'intake': self.INTAKE, 'period_seconds': 3600})
        self.write_manifest({'ok': {'input': str(self.input), 'interval_seconds': 3601}})
        with self.assertRaises(ValueError): self.bind()

    def test_a_hash_that_can_never_match_a_sha256_is_refused(self):
        base = {'schema': 'office-drift/1', 'state': str(self.home / 'private')}
        for key in ('python_sha256', 'plan_sha256'):
            for bad in ('y', 'A' * 64, 'a' * 63, None, 1):
                self.write_input({**base, 'drift': {**self.DRIFT, key: bad}})
                with self.assertRaises(ValueError): self.bind()
        self.write_input({**base, 'intake': {**self.INTAKE, 'python_sha256': 'z'}})
        with self.assertRaises(ValueError): self.bind()
