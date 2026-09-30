"""Append-only decision history, with explicit corrections and exact redactions."""
import hashlib
import re
from .content_guard import PATTERNS, ContentRefused, _git, load_policy

TARGETS = ('Nortropic/nortropic-runtime', 'Nortropic/nortropic-projektkontor')
PATH = 'docs/decisions.md'


def sections(raw):
    text = raw.decode('utf-8')
    result, name, lines, fence = {}, '__preamble__', [], None
    for line in text.splitlines(keepends=True):
        mark = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if mark:
            token=mark[1]
            if fence is None:fence=token
            elif token[0]==fence[0] and len(token)>=len(fence):fence=None
        heading = None if fence else re.match(r'^## ([A-Za-z0-9][A-Za-z0-9_-]*)(?=\s|$)',line)
        if heading:
            result[name]=''.join(lines);name=heading[1];lines=[]
            if name in result:raise ContentRefused('Duplicate decision identity')
        lines.append(line)
    if name in result:raise ContentRefused('Duplicate decision identity')
    result[name]=''.join(lines)
    return result


def redacted(text, literals):
    """Only actual scanner matches may be replaced by an exact digest marker."""
    raw=text.encode('utf-8');spans=[]
    for pattern in PATTERNS.values():spans.extend(m.span() for m in pattern.finditer(raw))
    for literal in literals:
        start=0
        while (pos:=raw.find(literal,start))>=0:spans.append((pos,pos+len(literal)));start=pos+1
    merged=[]
    for start,end in sorted(spans):
        if merged and start<merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    for start,end in reversed(merged):
        marker=b'[REDACTED sha256='+hashlib.sha256(raw[start:end]).hexdigest().encode()+b']'
        raw=raw[:start]+marker+raw[end:]
    return raw.decode('utf-8')


def retained(old,new):
    # Ignore wrapping/whitespace, retain every text token in its original order.
    remaining=iter(new.split())
    return all(any(n==token for n in remaining) for token in old.split())


def inspect(old,new,policy):
    before,after=sections(old),sections(new)
    corrections=set()
    for key in after.keys()-before.keys():
        corrections.update(re.findall(r'(?m)^(?:Rättelse av|Correction of): ([A-Za-z0-9][A-Za-z0-9_-]*)\s*$',after[key]))
    changed=[]
    for key,prior in before.items():
        current=after.get(key)
        if current is not None and retained(redacted(prior,policy['literals']),redacted(current,policy['literals'])):continue
        if key!='__preamble__' and key in corrections:changed.append({'id':key,'basis':'named-correction'});continue
        if (key!='__preamble__' and current is not None and re.search(r'\bSUPERSEDED\b',current)
            and not re.search(r'\bSUPERSEDED\b',prior)):
            changed.append({'id':key,'basis':'new-superseded-marker'});continue
        raise ContentRefused('Decision text removed without a named correction: '+key)
    return {'schema':1,'old_sha256':hashlib.sha256(old).hexdigest(),'new_sha256':hashlib.sha256(new).hexdigest(),
            'old_sections':len(before)-1,'new_sections':len(after)-1,'exceptions':changed,'passed':True}


def require_decisions(repo,base,candidate,target,policy=None):
    if target not in TARGETS:return {'applicable':False}
    def blob(commit):
        if not _git(repo,'ls-tree','-z',commit,'--',PATH):return b''
        size=_git(repo,'cat-file','-s',commit+':'+PATH).strip()
        if not size.isdigit() or int(size)>16*1024*1024:raise ContentRefused('Decision log exceeds limit')
        return _git(repo,'show',commit+':'+PATH)
    old,new=blob(base),blob(candidate)
    if old==new:return {'applicable':True,'unchanged':True,'sha256':hashlib.sha256(old).hexdigest()}
    return inspect(old,new,load_policy() if policy is None else policy)
