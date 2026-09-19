"""Whole accepted report contract, host-owned and frozen before continuation."""
import json
from acceptance.run_report_phase1 import verify as verify_codex, run

PYTHON='/opt/homebrew/bin/python3.12'


def verify(workspace):
    observations=verify_codex(workspace)['observations']
    usage={'input_tokens':17,'output_tokens':9,'cache_read_input_tokens':13,
           'cache_creation_input_tokens':4,'nested':{'reported':True}}
    done={'type':'result','subtype':'success','is_error':False,'usage':usage,'total_cost_usd':0.03125}
    cases=[('completed',[done],'completed',usage,0.03125),
           ('actual-error-shape',[{**done,'is_error':True}],'failed',usage,0.03125),
           ('error-subtype',[{**done,'subtype':'error_during_execution'}],'failed',usage,0.03125),
           ('missing',[],'incomplete',None,None),
           ('start-only',[{'type':'system','subtype':'init'}],'incomplete',None,None),
           ('duplicate',[done,done],'invalid',None,None),
           ('absent-usage',[{'type':'result','subtype':'success','is_error':False}],'completed',None,None),
           ('missing-error-flag',[{'type':'result','subtype':'success'}],None,None,None),
           ('wrong-error-flag',[{**done,'is_error':0}],None,None,None)]
    for name,events,status,values,cost in cases:
        lines=[json.dumps(e) for e in events]
        code='import json; from tools.run_report import summarize; print(json.dumps(summarize("claude", '+repr(lines)+')))'
        proc=run(workspace,[PYTHON,'-B','-c',code])
        try:actual=json.loads(proc.stdout)
        except ValueError:actual=None
        passed=(proc.returncode==0 and isinstance(actual,dict) and actual.get('provider')=='claude'
                and actual.get('status') in ('completed','failed','invalid','incomplete')
                and (actual['status']==status if status else actual['status']!='completed')
                and (status not in ('completed','failed','incomplete') or
                     (actual.get('usage')==values and actual.get('total_cost_usd')==cost)))
        observations.append({'case':'claude-'+name,'passed':passed,'actual':actual,'stderr':proc.stderr,'returncode':proc.returncode})
    for line in ('{','null','[]'):
        proc=run(workspace,[PYTHON,'-B','-c','import json; from tools.run_report import summarize; print(json.dumps(summarize("claude", '+repr([line])+')))'])
        try:actual=json.loads(proc.stdout)
        except ValueError:actual=None
        observations.append({'case':'claude-malformed-'+line,'passed':proc.returncode==0 and isinstance(actual,dict) and actual.get('status')=='invalid','actual':actual,'stderr':proc.stderr})
    for provider,events,code in [('claude',[done],0),('claude',[{**done,'is_error':True}],1),
                                  ('claude',[],1),('claude',[done,done],1),('codex',[],1)]:
        text='\n'.join(json.dumps(e) for e in events)+'\n'
        argv=[PYTHON,'-B','tools/run_report.py','--provider',provider,'/dev/stdin']
        first=run(workspace,argv,text);second=run(workspace,argv,text)
        try:actual=json.loads(first.stdout)
        except ValueError:actual=None
        observations.append({'case':provider+'-CLI-'+str(code)+'-'+str(len(events)),
            'passed':first.returncode==second.returncode==code and first.stdout==second.stdout
                     and isinstance(actual,dict) and actual.get('provider')==provider,
            'actual':actual,'returncode':first.returncode,'stderr':first.stderr})
    for args in (['--provider','claude','.scratch/definitely-missing-input'],['--provider','unsupported','/dev/stdin'],[]):
        proc=run(workspace,[PYTHON,'-B','tools/run_report.py',*args])
        observations.append({'case':'CLI-usage-file-error','args':args,'passed':proc.returncode==2,
                             'returncode':proc.returncode,'stderr':proc.stderr})
    proc=run(workspace,[PYTHON,'-B','-m','unittest','tools.test_run_report','-v'])
    observations.append({'case':'candidate-regression-tests','passed':proc.returncode==0,
                         'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    return {'passed':all(x['passed'] for x in observations),'observations':observations}
