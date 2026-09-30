"""Real disposable children; failures in selector setup must still reap and close."""
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime import check_issuer, measurement_observer
from scripts import matning_provanvandare


class WebGroupCleanupTests(unittest.TestCase):
    # The child acknowledges its installed SIGTERM handler before the leader
    # either sleeps or exits. No timing guess establishes the stubborn child.
    PROGRAM = '''import os,signal,sys,time
reader,writer=os.pipe()
child=os.fork()
if child==0:
 os.close(reader);signal.signal(signal.SIGTERM,signal.SIG_IGN)
 os.write(writer,b'R');os.close(writer);time.sleep(60);os._exit(0)
os.close(writer);assert os.read(reader,1)==b'R';os.close(reader)
if sys.argv[1]=='exit':os._exit(0)
time.sleep(60)
'''

    def stop_disposable(self, child):
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait(timeout=10)

    def test_web_cleanup_kills_child_after_its_leader_already_exited(self):
        from runtime import web_common
        child=subprocess.Popen([sys.executable,'-B','-c',self.PROGRAM,'exit'],start_new_session=True)
        self.addCleanup(self.stop_disposable,child)
        self.assertEqual(child.wait(timeout=10),0)
        os.killpg(child.pid,0)  # the child, not the reaped leader, keeps this group alive
        self.assertEqual(web_common.end_group(child,grace=.1),0)
        with self.assertRaises(ProcessLookupError):os.killpg(child.pid,0)

    def test_web_timeout_kills_child_ignoring_sigterm_after_leader_dies(self):
        from runtime import web_common
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();children=[];spawn=subprocess.Popen
            def observed(*args,**kwargs):
                child=spawn(*args,**kwargs);children.append(child);self.addCleanup(self.stop_disposable,child);return child
            stop=web_common.end_group
            with (root/'stream').open('wb') as output, patch.object(web_common.subprocess,'Popen',side_effect=observed), \
                 patch.object(web_common,'end_group',side_effect=lambda child:stop(child,grace=.1)):
                result=web_common.run_session([sys.executable,'-B','-c',self.PROGRAM,'sleep'],root,dict(os.environ),'prompt',output,1)
            self.assertEqual(result,(-signal.SIGTERM,'tidsgrans'))
            self.assertEqual(len(children),1)
            with self.assertRaises(ProcessLookupError):os.killpg(children[0].pid,0)

    def test_unverified_web_group_cleanup_is_an_error(self):
        from runtime import web_common
        with patch('scripts.bounded.stop_group',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'could not be verified'):
                web_common.end_group(object(),grace=.1)


class SetupCleanupTests(unittest.TestCase):
    def exercise(self, kind, registrations):
        real_selector = selectors.DefaultSelector
        real_popen = subprocess.Popen
        for fail_at in range(registrations + 1):
            with self.subTest(kind=kind, fail_at=fail_at), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                children, selectors_created, cleanup_calls = [], [], []

                class FaultSelector:
                    def __init__(self):
                        if fail_at == 0:raise OSError('synthetic selector allocation failure')
                        self.inner = real_selector(); self.count = 0; self.closed = False
                        selectors_created.append(self)
                    def register(self, *args):
                        self.count += 1
                        if self.count == fail_at:raise OSError('synthetic selector registration failure')
                        return self.inner.register(*args)
                    def close(self):
                        self.inner.close(); self.closed = True

                def spawn(argv, **kwargs):
                    if argv[0] == 'fixture-sleep':
                        argv = [sys.executable, '-B', '-c', 'import time;time.sleep(30)']
                        child = real_popen(argv, **kwargs); children.append(child); return child
                    return real_popen(argv, **kwargs)

                def cleanup(child):
                    cleanup_calls.append(child.pid)
                    try:os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:pass

                def invoke():
                    if kind == 'receive':
                        return measurement_observer.receive_process(['fixture-sleep'], root, None, [{'name':'test_synthetic.T.test_sleep','file':'scripts/test_synthetic.py'}], root/'result',
                            5, cleanup, lambda p: p.poll() is not None, popen=spawn)
                    if kind == 'prepare':
                        return measurement_observer.capture_stage(['fixture-sleep'], root/'result',
                            5, cleanup, lambda p: p.poll() is not None)
                    if kind == 'acceptance':
                        (root/'.scratch').mkdir(); (root/'source').mkdir()
                        with patch('runtime.profile.sandbox_command', return_value=['fixture-sleep', 'permissions.nr.filesystem={}']):
                            return check_issuer.run_isolated(root, root/'unused-probe', timeout=5)
                    # Replace only this synthetic sandbox launcher; use its real
                    # child pipes/group and the production kill/wait code.
                    def legacy_spawn(argv, **kwargs):
                        if argv[0] == '/usr/bin/sandbox-exec':argv = ['fixture-sleep']
                        return spawn(argv, **kwargs)
                    with patch.object(subprocess, 'Popen', side_effect=legacy_spawn):
                        return matning_provanvandare.observe_child(['unused'], root, None, '(allow default)', 5)

                try:
                    with patch.object(selectors, 'DefaultSelector', FaultSelector), \
                         patch.object(subprocess, 'Popen', side_effect=spawn):
                        with self.assertRaises((OSError, measurement_observer.ObservationInterrupted)):
                            invoke()
                    self.assertEqual(len(children), 1)
                    child = children[0]
                    self.assertIsNotNone(child.poll())
                    self.assertTrue(all(stream.closed for stream in (child.stdin, child.stdout, child.stderr) if stream))
                    self.assertTrue(all(s.closed for s in selectors_created))
                    if kind in ('receive', 'prepare'):self.assertEqual(cleanup_calls, [child.pid])
                    with self.assertRaises(ProcessLookupError):os.killpg(child.pid, 0)
                finally:
                    # Test failure must not leave the disposable child alive.
                    for child in children:
                        if child.poll() is None:cleanup(child)
                        child.wait(timeout=10)
                        for stream in (child.stdin, child.stdout, child.stderr):
                            if stream and not stream.closed:stream.close()
                    for selector in selectors_created:
                        if not selector.closed:selector.close()

    def test_receiver_reaps_after_factory_and_each_registration_failure(self):self.exercise('receive', 2)
    def test_preparation_reaps_after_factory_and_each_registration_failure(self):self.exercise('prepare', 2)
    def test_acceptance_reaps_after_factory_and_each_registration_failure(self):self.exercise('acceptance', 3)
    def test_legacy_observer_reaps_after_factory_and_registration_failure(self):self.exercise('legacy', 1)
