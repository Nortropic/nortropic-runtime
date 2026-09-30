"""P1 checks every declared runtime heartbeat and both actual worker calls."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def seconds(node):
    if (not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id!='timedelta'
        or node.args or len(node.keywords)!=1 or node.keywords[0].arg!='seconds'
        or not isinstance(node.keywords[0].value,ast.Constant)
        or type(node.keywords[0].value.value) not in (int,float) or node.keywords[0].value.value<=0):
        raise ValueError('Unqualified heartbeat duration')
    return node.keywords[0].value.value


def verify(files):
    timeouts=[];caps=[]
    for path,text in files.items():
        tree=ast.parse(text)
        timeouts.extend(seconds(n.value) for n in ast.walk(tree) if isinstance(n,ast.keyword) and n.arg=='heartbeat_timeout')
        if path=='worker.py':
            for call in ast.walk(tree):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='Worker':
                    named=[k.value for k in call.keywords if k.arg=='max_heartbeat_throttle_interval']
                    if len(named)!=1:raise ValueError('Worker lacks an explicit throttle cap')
                    caps.append(seconds(named[0]))
    if not timeouts or not caps:raise ValueError('No observable activity or worker')
    if any(min(.8*t,c)>.25*t for c in caps for t in timeouts):raise ValueError('Throttle exceeds one quarter of heartbeat timeout')
    return {'timeouts':sorted(timeouts),'worker_caps':caps}


class HeartbeatThrottle(unittest.TestCase):
    def setUp(self):self.files={str(p.relative_to(ROOT/'runtime')):p.read_text() for p in (ROOT/'runtime').rglob('*.py')}
    def test_all_runtime_timeouts_have_margin_in_every_worker(self):
        self.assertEqual(verify(self.files),{'timeouts':[10,10,15],'worker_caps':[2,2]})
    def test_missing_either_worker_cap_and_old_default_refuse(self):
        text=self.files['worker.py'];needle=', max_heartbeat_throttle_interval=timedelta(seconds=2)'
        starts=[i for i in range(len(text)) if text.startswith(needle,i)]
        self.assertEqual(len(starts),2)
        for start in starts:
            with self.assertRaisesRegex(ValueError,'lacks'):verify({**self.files,'worker.py':text[:start]+text[start:].replace(needle,'',1)})
        with self.assertRaisesRegex(ValueError,'lacks'):verify({**self.files,'worker.py':text.replace(needle,'')})
    def test_new_short_timeout_unknown_expression_and_large_cap_refuse(self):
        for files in ({**self.files,'new.py':'call(heartbeat_timeout=timedelta(seconds=1))'},
                      {**self.files,'new.py':'call(heartbeat_timeout=unknown)'},
                      {**self.files,'worker.py':self.files['worker.py'].replace('seconds=2','seconds=3')}):
            with self.assertRaises(ValueError):verify(files)
