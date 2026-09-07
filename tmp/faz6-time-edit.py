from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name in ('models.py', 'workflow.py', 'workflow_core.py', 'portal_auth.py', 'analysis_pipeline.py', 'learning.py', 'indexing.py'):
    path = root / 'app' / name
    source = path.read_text(encoding='utf-8')
    source = source.replace('datetime.utcnow()', 'utc_now()').replace('default=datetime.utcnow', 'default=utc_now').replace('onupdate=datetime.utcnow', 'onupdate=utc_now')
    anchor = 'from __future__ import annotations\n'
    addition = 'from .time_policy import utc_now, as_utc, utc_stamp\n'
    if anchor in source:
        source = source.replace(anchor, anchor + addition, 1)
    else:
        # Insert after the module docstring.
        pos = source.index('\n') + 1
        source = source[:pos] + addition + source[pos:]
    if name == 'models.py':
        source = source.replace('Boolean, DateTime,', 'Boolean, Index,')
        source = source.replace('from .database import Base', 'from .database import Base\nfrom .time_policy import UTCDateTime as DateTime')
    if name == 'workflow.py':
        source = source.replace('return value.isoformat() + "Z" if value else None', 'return utc_stamp(value)')
    if name == 'workflow_core.py':
        source = source.replace('(now - value)', '(now - as_utc(value))')
        source = source.replace('last_at = max([record.created_at] + [event.created_at for event in events] + ([flow.updated_at] if flow else []))', 'last_at = max(as_utc(value) for value in [record.created_at] + [event.created_at for event in events] + ([flow.updated_at] if flow else []))')
        source = source.replace('stage_at.isoformat() + "Z" if known else None', 'utc_stamp(stage_at) if known else None').replace('last_at.isoformat() + "Z"', 'utc_stamp(last_at)')
    if name == 'learning.py':
        source = source.replace('analyzed.completed_at.isoformat() + "Z"', 'utc_stamp(analyzed.completed_at)').replace('utc_now().isoformat() + "Z"', 'utc_stamp(utc_now())')
    path.write_text(source, encoding='utf-8')
