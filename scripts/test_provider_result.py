import copy
import json
from pathlib import Path
import unittest
from runtime.provider_result import parse


class ProviderResultTest(unittest.TestCase):
    def test_real_claude_terminal_and_fail_closed_variants(self):
        events=[json.loads(l) for l in Path('evidence/claude-qualification/boundary-direct/stdout.log').read_text().splitlines()]
        self.assertTrue(parse('claude',events)['valid_terminal'])
        terminal=next(e for e in events if e.get('type')=='result')
        for field,value in [('is_error',True),('is_error',0),('subtype','error_during_execution'),
                            ('terminal_reason','interrupted'),('session_id','wrong')]:
            changed=copy.deepcopy(events)
            next(e for e in changed if e.get('type')=='result')[field]=value
            self.assertFalse(parse('claude',changed)['valid_terminal'],field)
        self.assertFalse(parse('claude',events+[terminal])['valid_terminal'])
        self.assertFalse(parse('claude',[e for e in events if e.get('type')!='result'])['valid_terminal'])
        changed=copy.deepcopy(events)
        next(e for e in changed if e.get('subtype')=='init')['tools'].append('Bash')
        self.assertFalse(parse('claude',changed)['valid_terminal'])

    def test_codex_keeps_original_terminal_rules(self):
        start={'type':'thread.started','thread_id':'same-history'}
        done={'type':'turn.completed','usage':{'input_tokens':9}}
        self.assertTrue(parse('codex',[start,done])['valid_terminal'])
        for events in ([done],[start],[start,done,done],[start,done,{'type':'error'}]):
            self.assertFalse(parse('codex',events)['valid_terminal'])

if __name__=='__main__':unittest.main()
