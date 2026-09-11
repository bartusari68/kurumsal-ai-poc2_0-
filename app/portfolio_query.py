"""Fixed-count batch SQL aggregates. No per-skill/per-version database lookups.

Only organization-wide needs analysts have this reporting capability, exactly as
in Faz 12. Operational handoff recipients never receive this aggregate payload.
"""
from collections import defaultdict
from datetime import datetime
from sqlalchemy import text
from . import portfolio_policy as policy
from .evaluation_policy import SOURCES, TEMPLATES
from .time_policy import utc_now, utc_stamp
from .utils import json_loads

MAP = '(SELECT DISTINCT skill_id,course_version_id FROM course_skill_mappings)'
CURRENT_EVAL = """e.status='ENROLLED' AND e.completion='COMPLETED' AND e.completed_at IS NOT NULL
    AND v.completion_at=e.completed_at AND v.status='COMPLETED'"""

def query(db, sql, **params):
    rows = [dict(r) for r in db.execute(text(sql), params).mappings()]
    # Raw SQLite aggregates bypass UTCDateTime's ORM result processor.
    for row in rows:
        for key in ('last_activity','published_at'):
            if row.get(key): row[key] = utc_stamp(datetime.fromisoformat(row[key]))
    return rows

def aggregate(db, actor):
    policy.require_manager(actor)
    now = utc_now(); stamp = utc_stamp(now)
    skills = query(db, 'SELECT s.id skill_id,s.canonical_name skill,s.group_id,g.name skill_group,s.status,s.updated_at last_activity FROM skills s JOIN skill_groups g ON g.id=s.group_id')
    rows = {r['skill_id']: {**r, 'scope': policy.SCOPE, 'planned_profiles': 0, 'observed_needs': 0,
        'open_needs': 0, 'resolved_needs': 0, 'repeated_needs': 0, 'published_versions': 0, 'planned_revision_ids': [],
        'catalog': [], 'development': [], 'training': {'upcoming_sessions': 0, 'completed_sessions': 0,
        'total_sessions': 0, 'known_capacity': 0, 'unbounded_sessions': 0, 'upcoming_capacity': 0,
        'upcoming_unbounded_sessions': 0, 'enrollments': 0, 'completions': 0}, 'privacy_suppressed': False} for r in skills}
    for r in query(db, """SELECT q.skill_id,count(DISTINCT p.id) n,json_group_array(DISTINCT v.id) revisions FROM position_profiles p
        JOIN position_revisions v ON v.profile_id=p.id AND v.version=p.version AND v.sealed=1
        JOIN position_requirements q ON q.revision_id=v.id
        WHERE p.status='ACTIVE' AND q.requirement_type='REQUIRED' GROUP BY q.skill_id"""):
        rows[r['skill_id']]['planned_profiles'] = r['n']
        rows[r['skill_id']]['planned_revision_ids'] = json_loads(r['revisions'],[])
    need_groups = defaultdict(list)
    for r in query(db, """SELECT n.skill_id, CASE WHEN w.status='RESOLVED' THEN 'resolved_needs' ELSE 'open_needs' END bucket,
        count(*) count,count(DISTINCT u.id) people FROM request_skill_needs n
        JOIN request_workflows w ON w.request_id=n.request_id JOIN portal_users u ON w.owner_hash=printf('user:%d',u.id)
        WHERE n.active=1 AND n.human_verified=1 GROUP BY n.skill_id,bucket"""):
        need_groups[r['skill_id']].append(r)
    # Demand totals are counted separately: the same person may own open and resolved requests.
    for r in query(db, """SELECT n.skill_id,count(*) count,count(DISTINCT u.id) people FROM request_skill_needs n
        JOIN request_workflows w ON w.request_id=n.request_id JOIN portal_users u ON w.owner_hash=printf('user:%d',u.id)
        WHERE n.active=1 AND n.human_verified=1 GROUP BY n.skill_id"""):
        item = rows[r['skill_id']]; groups = need_groups[r['skill_id']]
        safe = policy.partition(groups)
        item['observed_needs'] = policy.disclosed(r['count'], r['people']) if safe else None
        for group in groups: item[group['bucket']] = group['count'] if safe else None
        if not safe: item['open_needs'] = item['resolved_needs'] = None
        item['privacy_suppressed'] = not safe
    versions = {}
    for r in query(db, """SELECT m.skill_id,v.id,v.course_id,v.title,v.version_number,v.state,v.published_at,
        CASE WHEN v.state='PUBLISHED' AND c.current_version_id=v.id AND coalesce(g.lifecycle_state,'ACTIVE')='ACTIVE' THEN 1 ELSE 0 END current
        FROM """ + MAP + """ m JOIN course_versions v ON v.id=m.course_version_id
        LEFT JOIN course_catalog c ON c.course_id=v.course_id
        LEFT JOIN course_governance g ON g.course_id=v.course_id WHERE v.state IN ('PUBLISHED','ARCHIVED')"""):
        sid = r.pop('skill_id'); r.update(mapped_outcomes=[], outcomes=[], evaluation_count=0,
            completed_enrollments=0, enrollments=0)
        versions[(sid,r['id'])] = r; rows[sid]['catalog'].append(r)
        rows[sid]['published_versions'] += r['current']
        if r['published_at']: rows[sid]['last_activity'] = max(rows[sid]['last_activity'], r['published_at'])
    for r in query(db, 'SELECT skill_id,course_version_id,outcome_index,outcome_text FROM course_skill_mappings WHERE outcome_index>=0'):
        v = versions.get((r['skill_id'],r['course_version_id']))
        if v is not None: v['mapped_outcomes'].append({'index': r['outcome_index'], 'text': r['outcome_text']})
    for r in query(db, """SELECT m.skill_id,count(*) total_sessions,
        sum(CASE WHEN s.status='SCHEDULED' AND s.start_at>:now THEN 1 ELSE 0 END) upcoming_sessions,
        sum(CASE WHEN s.status='COMPLETED' THEN 1 ELSE 0 END) completed_sessions,
        coalesce(sum(s.capacity),0) known_capacity,sum(CASE WHEN s.capacity IS NULL THEN 1 ELSE 0 END) unbounded_sessions,
        coalesce(sum(CASE WHEN s.status='SCHEDULED' AND s.start_at>:now THEN s.capacity ELSE 0 END),0) upcoming_capacity,
        sum(CASE WHEN s.status='SCHEDULED' AND s.start_at>:now AND s.capacity IS NULL THEN 1 ELSE 0 END) upcoming_unbounded_sessions,
        max(s.updated_at) last_activity FROM """ + MAP + """ m JOIN training_sessions s ON s.course_version_id=m.course_version_id
        WHERE s.status<>'CANCELLED' GROUP BY m.skill_id""", now=now.replace(tzinfo=None).isoformat(' ')):
        sid=r.pop('skill_id'); last=r.pop('last_activity'); rows[sid]['training'].update(r)
        rows[sid]['last_activity']=max(rows[sid]['last_activity'],last)
    # Use grouping sets via UNION ALL to avoid summing distinct-user cells across versions.
    enroll_sql = """SELECT m.skill_id,{version} course_version_id,e.completion,count(*) count,count(DISTINCT e.user_id) people
        FROM """+MAP+""" m JOIN training_sessions s ON s.course_version_id=m.course_version_id
        JOIN training_enrollments e ON e.session_id=s.id WHERE e.status='ENROLLED' AND s.status<>'CANCELLED'
        GROUP BY m.skill_id,{group} e.completion"""
    enrollment_groups=defaultdict(list)
    for r in query(db, enroll_sql.format(version='NULL',group='')+' UNION ALL '+enroll_sql.format(version='s.course_version_id',group='s.course_version_id,')):
        enrollment_groups[(r['skill_id'],r['course_version_id'])].append(r)
    for (sid,vid), groups in enrollment_groups.items():
        safe=policy.partition(groups); count=sum(g['count'] for g in groups) if safe else None
        completed=sum(g['count'] for g in groups if g['completion']=='COMPLETED') if safe else None
        if vid is None: rows[sid]['training'].update(enrollments=count,completions=completed)
        elif (sid,vid) in versions: versions[(sid,vid)].update(enrollments=count,completed_enrollments=completed)
        rows[sid]['privacy_suppressed'] |= not safe
    # Counts and distributions never select free-text comments or individual evidence.
    for r in query(db, """SELECT m.skill_id,v.course_version_id,count(*) count,count(DISTINCT e.user_id) people
        FROM learning_evaluations v JOIN training_enrollments e ON e.id=v.enrollment_id
        JOIN """+MAP+""" m ON m.course_version_id=v.course_version_id WHERE """+CURRENT_EVAL+"""
        GROUP BY m.skill_id,v.course_version_id"""):
        v=versions.get((r['skill_id'],r['course_version_id']))
        if v is not None: v['evaluation_count']=policy.disclosed(r['count'],r['people'])
    evaluation_groups=defaultdict(list)
    distribution_sql = """SELECT m.skill_id,v.course_version_id,v.evaluator_source source,v.evaluation_type type,
        {index} outcome_index,{value} value,count(DISTINCT v.id) count,count(DISTINCT e.user_id) people
        FROM learning_evaluations v JOIN training_enrollments e ON e.id=v.enrollment_id
        JOIN {mapping} m ON m.course_version_id=v.course_version_id
        WHERE """+CURRENT_EVAL+""" AND v.evaluation_type=:kind {extra}
        GROUP BY m.skill_id,v.course_version_id,v.evaluator_source,outcome_index,value"""
    for kind,sql in [('APPLICATION',distribution_sql.format(index='-1',value='v.outcome',mapping=MAP,extra='')),
                     ('LEARNING',distribution_sql.format(index='m.outcome_index',value="json_extract(v.response_json,'$.outcome_'||m.outcome_index)",mapping='course_skill_mappings',extra='AND m.outcome_index>=0'))]:
        for r in query(db,sql,kind=kind):
            evaluation_groups[(r['skill_id'],r['course_version_id'],r['source'],kind,r['outcome_index'])].append(r)
    for (sid,vid,source,kind,index),groups in evaluation_groups.items():
        v=versions.get((sid,vid))
        if v is None: continue
        safe=policy.partition(groups); count=sum(g['count'] for g in groups) if safe else None
        # Each cell has >=5 distinct people if disclosed, not just five repeated submissions.
        sufficient=safe and sum(g['people'] for g in groups)>=policy.MIN_PERCENT_SAMPLE
        v['outcomes'].append({'type':kind,'type_label':TEMPLATES[kind]['title'],'source':source,'source_label':SOURCES[source],
            'outcome_index':index,'count':count,'state':'SUFFICIENT' if sufficient else 'INSUFFICIENT_DATA',
            'distribution':{g['value']:g['count'] for g in groups if g['value']} if safe else {},
            'percentages':{g['value']:round(100*g['count']/count,1) for g in groups if g['value']} if sufficient and count else {},
            'privacy_suppressed':not safe})
        if not safe: v['evaluation_count']=None; rows[sid]['privacy_suppressed']=True
    repeat_groups=defaultdict(list)
    for r in query(db, """WITH repeated AS (SELECT n.skill_id,n.request_id,u.id user_id,EXISTS (
          SELECT 1 FROM training_enrollments e JOIN training_sessions s ON s.id=e.session_id
          JOIN course_skill_mappings m ON m.course_version_id=s.course_version_id AND m.skill_id=n.skill_id
          WHERE e.user_id=u.id AND e.status='ENROLLED' AND e.completion='COMPLETED'
          AND e.completed_at<r.created_at AND (e.source_request_id IS NULL OR e.source_request_id<>r.id)) is_repeated
        FROM request_skill_needs n JOIN requests r ON r.id=n.request_id
        JOIN request_workflows w ON w.request_id=r.id JOIN portal_users u ON w.owner_hash=printf('user:%d',u.id)
        WHERE n.active=1 AND n.human_verified=1)
        SELECT skill_id,is_repeated,count(DISTINCT request_id) count,count(DISTINCT user_id) people
        FROM repeated GROUP BY skill_id,is_repeated"""):
        repeat_groups[r['skill_id']].append(r)
    for sid,groups in repeat_groups.items():
        item=rows[sid]
        item['repeated_needs']=sum(r['count'] for r in groups if r['is_repeated']) if policy.partition(groups) and item['observed_needs'] is not None else None
        item['privacy_suppressed'] |= item['repeated_needs'] is None
    for r in query(db, """SELECT DISTINCT n.skill_id,d.id,d.title,d.state,d.work_type,d.responsible_unit
        FROM development_items d JOIN request_skill_needs n ON n.request_id=d.source_request_id
        WHERE n.active=1 AND n.human_verified=1
        UNION SELECT DISTINCT m.skill_id,d.id,d.title,d.state,d.work_type,d.responsible_unit
        FROM development_items d JOIN course_versions v ON v.source_development_id=d.id
        JOIN course_skill_mappings m ON m.course_version_id=v.id"""):
        sid=r.pop('skill_id'); rows[sid]['development'].append(r)
    for row in rows.values(): row['signals']=policy.classify(row,stamp)
    return {'generated_at':stamp,'scope':policy.SCOPE,'items':list(rows.values()),
        'policy':{'minimum_people':policy.MIN_AGGREGATE_USERS,'minimum_outcome_sample':policy.MIN_PERCENT_SAMPLE,
                  'repeated_observations':policy.REPEATED_SIGNAL_COUNT},
        'meaning':'Planlanan = aktif profillerin güncel gerekli yetkinlikleri. Gözlenen = insan tarafından doğrulanmış, aktif talep ihtiyaçları. Açık = talep durumu çözüme ulaşmamış. Sonuç bildirimleri talep durumundan ayrıdır. Küçük hücreler ve çıkarımları gizlenir; sıfır ile gizli veri farklıdır.'}

def overview(db,actor,signal='',group_id=None,coverage='',open_only=False,sort='activity',offset=0,limit=20):
    data=aggregate(db,actor); rows=data['items']
    from .portfolio_models import PortfolioItem
    from sqlalchemy import select,func
    data['summary']={kind:sum(any(s['type']==kind for s in r['signals']) for r in rows) for kind in policy.SIGNALS}
    data['summary']['under_review']=db.scalar(select(func.count()).select_from(PortfolioItem).where(PortfolioItem.state=='UNDER_REVIEW'))
    data['groups']=list({r['group_id']:{'id':r['group_id'],'name':r['skill_group']} for r in rows}.values())
    rows=[r for r in rows if (not signal or any(s['type']==signal for s in r['signals'])) and (not group_id or r['group_id']==group_id)
          and (not coverage or bool(r['published_versions'])==(coverage=='PRESENT')) and (not open_only or (r['open_needs'] or 0)>0)]
    key={'activity':lambda r:r['last_activity'],'planned':lambda r:r['planned_profiles'],
         'observed':lambda r:r['observed_needs'] if r['observed_needs'] is not None else -1,'open':lambda r:r['open_needs'] if r['open_needs'] is not None else -1,'name':lambda r:r['skill'].casefold()}[sort]
    rows.sort(key=lambda r:r['skill_id']);rows.sort(key=key,reverse=sort!='name')
    data.update(items=rows[offset:offset+limit],total=len(rows),offset=offset,limit=limit,signal_types=policy.SIGNALS)
    return data

def skill(db,actor,skill_id):
    from fastapi import HTTPException
    data=aggregate(db,actor)
    row=next((r for r in data['items'] if r['skill_id']==skill_id),None)
    if row is None: raise HTTPException(404,'Yetkinlik bulunamadı.')
    return {**row,'generated_at':data['generated_at'],'policy':data['policy'],'meaning':data['meaning']}
