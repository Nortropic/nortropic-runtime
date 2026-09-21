"""Fail closed on ambiguous/missing terminal output from the selected native CLI."""
# Measured with the pinned CLI: --json-schema adds exactly the StructuredOutput
# tool. A reviewer that could edit is not a reviewer, so the inventory is exact.
CLAUDE_TOOLS={'implementation':{'Read','Edit','Write'},'review':{'Read','StructuredOutput'}}


def parse(provider, records, role='implementation'):
    if provider == 'codex':
        starts=[e.get('thread_id') for e in records if e.get('type')=='thread.started']
        terminals=[e for e in records if e.get('type') in ('turn.completed','turn.failed')]
        errors=[e for e in records if e.get('type') in ('error','turn.failed')]
        valid=(len(terminals)==1 and terminals[0]['type']=='turn.completed' and not errors)
        extra={}
    elif provider == 'claude':
        if role not in CLAUDE_TOOLS: raise ValueError('Unsupported provider role')
        init=[e for e in records if e.get('type')=='system' and e.get('subtype')=='init']
        starts=[e.get('session_id') for e in init]
        terminals=[e for e in records if e.get('type')=='result']
        from .claude_profile import VERSION, MODEL
        tools=init[0].get('tools') if init else None
        valid=(len(init)==1 and len(terminals)==1 and terminals[0].get('is_error') is False
               and terminals[0].get('subtype')=='success' and terminals[0].get('terminal_reason')=='completed'
               and terminals[0].get('session_id')==init[0].get('session_id')
               and init[0].get('claude_code_version')==VERSION and init[0].get('model')==MODEL
               and isinstance(tools,list) and len(tools)==len(set(tools)) and set(tools)==CLAUDE_TOOLS[role]
               and init[0].get('mcp_servers')==[] and init[0].get('plugins')==[]
               and init[0].get('slash_commands')==[] and init[0].get('apiKeySource')=='none'
               and not any(e.get('type')=='error' for e in records))
        extra={'reported_list_cost_usd':terminals[-1].get('total_cost_usd') if terminals else None,
               'permission_denials':terminals[-1].get('permission_denials') if terminals else None}
    else: raise ValueError('Unsupported provider')
    identity=starts[0] if len(starts)==1 and isinstance(starts[0],str) and starts[0] else None
    return {'valid_terminal':bool(valid and identity),'thread_id':identity,
            'usage':terminals[-1].get('usage') if terminals else None,**extra}
