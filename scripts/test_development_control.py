"""Scoped stop races: absent native children never block remaining own stops."""
import unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from temporalio.service import RPCError,RPCStatusCode
from runtime.development_control import operate


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_reinspection_after_rpc_failure_does_not_reopen_scope(self):
        current={'control':'active','tasks':{'own':{}}};events=[]
        def control(value,reason):current['control']=value;events.append(value)
        scope=SimpleNamespace(control=control,inspect=lambda:current)
        own=SimpleNamespace(cancel=AsyncMock(side_effect=[RPCError('transient',RPCStatusCode.UNAVAILABLE,b''),None]))
        parent=SimpleNamespace(cancel=AsyncMock(),query=AsyncMock(return_value={'phase':'stopped'}))
        service=AsyncMock();service.__aenter__.return_value=SimpleNamespace(get_workflow_handle=lambda name:own if name=='own' else parent)
        with patch('runtime.development_control.require_active_code',return_value={'development':{'contract_sha256':'fixture'},'config_sha256':'fixture'}),patch('runtime.development_control.active_scope',return_value=(scope,{})),patch('runtime.development_control.SharedService',return_value=service):
            with self.assertRaisesRegex(RuntimeError,'Scope is stopped'):await operate('stop','first')
            result=await operate('stop','reinspect explicit transient cancellation failure')
        self.assertEqual(events,['stopped']);self.assertEqual(own.cancel.await_count,2);self.assertEqual(parent.cancel.await_count,2)
        self.assertEqual(result['scope']['control'],'stopped')

    async def test_bound_not_started_and_missing_parent_do_not_block_other_child_stop(self):
        not_found=RPCError('not started',RPCStatusCode.NOT_FOUND,b'')
        handles={name:SimpleNamespace(cancel=AsyncMock(side_effect=not_found if name!='running' else None),
            query=AsyncMock(side_effect=not_found)) for name in ('bound','running','office-ap11')}
        events=[]
        scope=SimpleNamespace(control=lambda state,reason:events.append((state,reason)),
            inspect=lambda:{'control':'active' if not events else 'stopped','tasks':{'bound':{},'running':{}}})
        client=SimpleNamespace(get_workflow_handle=lambda name:handles[name])
        service=AsyncMock();service.__aenter__.return_value=client
        with patch('runtime.development_control.require_active_code',return_value={'development':{'contract_sha256':'fixture'},'config_sha256':'fixture'}), \
             patch('runtime.development_control.active_scope',return_value=(scope,{})), \
             patch('runtime.development_control.SharedService',return_value=service):
            result=await operate('stop','accepted scoped stop')
        self.assertEqual(events,[('stopped','accepted scoped stop')])
        for handle in handles.values():handle.cancel.assert_awaited_once()
        self.assertFalse(result['native']['available'])

    async def test_status_unavailable_never_changes_control_or_cancels(self):
        missing=RPCError('not started',RPCStatusCode.NOT_FOUND,b'')
        handle=SimpleNamespace(cancel=AsyncMock(),query=AsyncMock(side_effect=missing))
        from unittest.mock import Mock
        scope=SimpleNamespace(control=Mock(),inspect=lambda:{'control':'paused','tasks':{}})
        service=AsyncMock();service.__aenter__.return_value=SimpleNamespace(get_workflow_handle=lambda _:handle)
        with patch('runtime.development_control.require_active_code',return_value={'development':{'contract_sha256':'fixture'},'config_sha256':'fixture'}),patch('runtime.development_control.active_scope',return_value=(scope,{})),patch('runtime.development_control.SharedService',return_value=service):
            result=await operate('status')
        self.assertFalse(result['native']['available']);scope.control.assert_not_called();handle.cancel.assert_not_awaited()

    async def test_pause_resume_and_wake_tell_the_waiting_parent_best_effort_and_status_never_does(self):
        from unittest.mock import Mock
        for action,reason,controlled in (('pause','operator pause','paused'),('resume','diagnosed resume','active'),('wake',None,None),('status',None,None)):
            for failure in (None,RPCError('gone',RPCStatusCode.NOT_FOUND,b''),TimeoutError()):
                handle=SimpleNamespace(signal=AsyncMock(side_effect=failure),query=AsyncMock(return_value={'phase':'waiting_control'}),cancel=AsyncMock())
                scope=SimpleNamespace(control=Mock(),inspect=lambda:{'control':'paused','tasks':{}})
                service=AsyncMock();service.__aenter__.return_value=SimpleNamespace(get_workflow_handle=lambda _:handle)
                with patch('runtime.development_control.require_active_code',return_value={'development':{'contract_sha256':'fixture'},'config_sha256':'fixture'}),patch('runtime.development_control.active_scope',return_value=(scope,{})),patch('runtime.development_control.SharedService',return_value=service):
                    result=await operate(action,reason)
                with self.subTest(action=action,failure=failure):
                    self.assertEqual(result['native'],{'phase':'waiting_control'});handle.cancel.assert_not_awaited()
                    if action=='status':self.assertNotIn('wake_signal',result)
                    elif failure is None:self.assertEqual(result['wake_signal'],'accepted by the engine')
                    else:self.assertIn('NOT delivered',result['wake_signal']);self.assertIn('repeat wake',result['wake_signal'])
                    if action=='status':handle.signal.assert_not_awaited()
                    else:
                        handle.signal.assert_awaited_once();self.assertEqual(handle.signal.await_args.args[0].__name__,'host_state_changed')
                    if controlled:scope.control.assert_called_once_with(controlled,reason)
                    else:scope.control.assert_not_called()

    async def test_the_scope_control_is_written_before_the_parent_is_told_to_read_it(self):
        """Otherwise the woken parent could read the OLD control and sleep on a fresh fallback timer."""
        for action,value in (('pause','paused'),('resume','active')):
            order=[]
            handle=SimpleNamespace(signal=AsyncMock(side_effect=lambda *a:order.append('signal')),query=AsyncMock(return_value={'phase':'waiting_control'}),cancel=AsyncMock())
            scope=SimpleNamespace(control=lambda state,reason:order.append(('control',state)),inspect=lambda:{'control':value,'tasks':{}})
            service=AsyncMock();service.__aenter__.return_value=SimpleNamespace(get_workflow_handle=lambda _:handle)
            with patch('runtime.development_control.require_active_code',return_value={'development':{'contract_sha256':'fixture'},'config_sha256':'fixture'}),patch('runtime.development_control.active_scope',return_value=(scope,{})),patch('runtime.development_control.SharedService',return_value=service):
                await operate(action,'ordered')
            with self.subTest(action=action):self.assertEqual(order,[('control',value),'signal'])


if __name__=='__main__':unittest.main()
