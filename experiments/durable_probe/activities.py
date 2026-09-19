"""No-model deterministic side effect, confined to this compatibility experiment."""
import json
import os
from pathlib import Path

from temporalio import activity

ROOT = Path(__file__).resolve().parents[2]


@activity.defn
async def record_effect(label: str) -> str:
    if label not in ('first', 'second'):
        raise ValueError(label)
    with (ROOT / '.runtime/durable-probe/effects.jsonl').open('a') as stream:
        stream.write(json.dumps({'label': label, 'activity_attempt': activity.info().attempt}) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return label
