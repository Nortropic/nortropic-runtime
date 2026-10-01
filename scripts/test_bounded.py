"""Real process regressions for the operator experiment limiter."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('bounded.py')
CHILD = 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'


class BoundedTest(unittest.TestCase):
    def test_child_does_not_inherit_the_parents_temporary_stop_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'evidence'
            program='import signal; blocked=signal.pthread_sigmask(signal.SIG_BLOCK, []); assert not ({signal.SIGINT,signal.SIGTERM} & blocked), blocked'
            result=subprocess.run([sys.executable,'-B',str(SCRIPT),'--seconds','10','--output',str(output),
                                   '--',sys.executable,'-B','-c',program],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,(output/'stderr.log').read_text())

    def test_ready_child_runs_its_sigterm_cleanup_before_group_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'evidence';ready=root/'ready';cleaned=root/'cleaned'
            program=('import signal,sys,time; from pathlib import Path\n'
                     'def finish(*args):\n Path(sys.argv[2]).write_text("cleaned");sys.exit(0)\n'
                     'signal.signal(signal.SIGTERM,finish)\n'
                     'Path(sys.argv[1]).write_text("ready");time.sleep(60)\n')
            proc=subprocess.Popen([sys.executable,'-B',str(SCRIPT),'--seconds','30','--output',str(output),
                                   '--',sys.executable,'-B','-c',program,str(ready),str(cleaned)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+10
                while not ready.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists(),'Child did not acknowledge its installed handler')
                proc.send_signal(signal.SIGTERM)
                stdout,stderr=proc.communicate(timeout=10)
                self.assertEqual(proc.returncode,143,stdout+stderr)
                self.assertTrue(cleaned.exists(),'Child cleanup was replaced by forced killing')
                self.assertEqual(cleaned.read_text(),'cleaned')
                self.assertTrue(json.loads((output/'run.json').read_text())['process_group_removed'])
            finally:
                if proc.poll() is None:proc.kill();proc.wait(timeout=10)
                if (output/'run.json').exists():
                    pid=json.loads((output/'run.json').read_text()).get('pid')
                    if pid:
                        try:os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError:pass

    def test_metadata_failure_after_spawn_still_removes_the_real_group(self):
        import importlib.util
        from unittest import mock
        spec=importlib.util.spec_from_file_location('bounded_metadata',SCRIPT)
        bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded)
        for failure in (OSError('synthetic ENOSPC'),bounded.StopRequested(signal.SIGTERM)):
            with self.subTest(failure=type(failure).__name__),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);out=root/'out';children=[];spawn=subprocess.Popen;write=Path.write_text
                handlers={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
                def observed(*a,**kw):
                    child=spawn(*a,**kw);children.append(child);return child
                failed=[]
                def writing(path,*a,**kw):
                    if path.name=='run.json' and not failed:failed.append(True);raise failure
                    return write(path,*a,**kw)
                argv=['bounded','--seconds','10','--output',str(out),'--',sys.executable,'-B','-c','import time;time.sleep(60)']
                try:
                    with mock.patch.object(sys,'argv',argv),mock.patch.object(bounded.subprocess,'Popen',side_effect=observed), \
                         mock.patch.object(Path,'write_text',writing):
                        if isinstance(failure,OSError):
                            with self.assertRaises(OSError):bounded.main()
                        else:self.assertEqual(bounded.main(),143)
                    self.assertEqual(len(children),1)
                    self.assertIsNotNone(children[0].poll())
                    with self.assertRaises(ProcessLookupError):os.killpg(children[0].pid,0)
                    self.assertEqual({sig:signal.getsignal(sig) for sig in handlers},handlers)
                finally:
                    for child in children:
                        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)

    def test_stop_signal_during_spawn_is_deferred_until_child_is_owned(self):
        import importlib.util
        from unittest import mock
        spec=importlib.util.spec_from_file_location('bounded_signal',SCRIPT)
        bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded)
        with tempfile.TemporaryDirectory() as temporary:
            children=[];spawn=subprocess.Popen
            def observed(*a,**kw):
                child=spawn(*a,**kw);children.append(child)
                os.kill(os.getpid(),signal.SIGTERM)
                return child
            argv=['bounded','--seconds','10','--output',str(Path(temporary)/'out'),'--',sys.executable,'-B','-c','import time;time.sleep(60)']
            try:
                with mock.patch.object(sys,'argv',argv),mock.patch.object(bounded.subprocess,'Popen',side_effect=observed):
                    self.assertEqual(bounded.main(),143)
                self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())
                metadata=json.loads((Path(temporary)/'out/run.json').read_text())
                self.assertEqual(metadata['pid'],children[0].pid)
                with self.assertRaises(ProcessLookupError):os.killpg(children[0].pid,0)
            finally:
                for child in children:
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)

    def exercise(self, mode):
        with tempfile.TemporaryDirectory(prefix='nr-bounded-') as directory:
            output = Path(directory) / 'evidence'
            leader = ('import subprocess,sys,time; '
                      'p=subprocess.Popen([sys.executable,"-c",' + repr(CHILD) + '],stdout=subprocess.PIPE); '
                      'p.stdout.readline(); print(p.pid,flush=True); '
                      + ('time.sleep(60)' if mode != 'normal' else 'sys.exit(0)'))
            proc = subprocess.Popen([sys.executable, str(SCRIPT), '--seconds', '1' if mode == 'timeout' else '30',
                                     '--output', str(output), '--', sys.executable, '-c', leader],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    p = output / 'stdout.log'
                    if p.exists() and p.read_text().strip():
                        break
                    time.sleep(0.02)
                else:
                    self.fail('fixture child never became ready')
                child_pid = int(p.read_text().strip())
                if mode == 'signal':
                    proc.send_signal(signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=10)
                self.assertEqual(proc.returncode, {'normal': 0, 'timeout': 124, 'signal': 143}[mode], stderr + stdout)
                metadata = json.loads((output / 'run.json').read_text())
                self.assertTrue(metadata['process_group_removed'])
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def test_normal_leader_exit_with_term_ignoring_child(self):
        self.exercise('normal')

    def test_timeout_with_term_ignoring_child(self):
        self.exercise('timeout')

    def test_sigterm_with_term_ignoring_child(self):
        self.exercise('signal')

    def test_eperm_requires_reaped_leader_and_absent_os_group(self):
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location('bounded', SCRIPT); bounded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bounded)
        proc = mock.Mock(pid=4242); proc.poll.return_value = 0
        absent = subprocess.CompletedProcess([],0,b'1 Ss\n',b'')
        with mock.patch.object(bounded.os,'killpg',side_effect=PermissionError()), \
             mock.patch.object(bounded.subprocess,'run',return_value=absent):
            self.assertTrue(bounded.stop_group(proc))
        # Exhaust the bounded grace immediately; none of these observations
        # may establish absence, including an unreadable or zombie group.
        for poll, result in ((None,absent), (0,subprocess.CompletedProcess([],0,b'4242 Z\n',b'')),
                             (0,subprocess.CompletedProcess([],1,b'',b'')),
                             (0,subprocess.CompletedProcess([],0,b'bad listing\n',b''))):
            proc.poll.return_value=poll
            with self.subTest(poll=poll,output=result.stdout), \
                 mock.patch.object(bounded.os,'killpg',side_effect=PermissionError()), \
                 mock.patch.object(bounded.subprocess,'run',return_value=result), \
                 mock.patch.object(bounded.time,'monotonic',side_effect=range(0,100,3)):
                self.assertFalse(bounded.stop_group(proc))


if __name__ == '__main__':
    unittest.main()
