"""SQLite query builders for the merged work queue; hydrate only the selected page.

The action predicates mirror operations.required_actions and the three domain
permission functions. Regression tests retain the pre-SQL implementation.
"""
from sqlalchemy import text, select
from .time_policy import utc_now


BASE = """
WITH grants AS (
 SELECT d.id did, d.delegator_id uid FROM delegations d
 JOIN portal_users a ON a.id=d.delegator_id
 JOIN portal_users b ON b.id=d.delegate_id
 LEFT JOIN user_organizations oa ON oa.user_id=a.id
 LEFT JOIN user_organizations ob ON ob.user_id=b.id
 WHERE d.delegate_id=:uid AND d.active=1 AND d.start_at<=:now AND d.end_at>:now
 AND a.active=1 AND b.active=1 AND a.id<>b.id AND a.role=b.role
 AND coalesce(oa.organization,'')=coalesce(ob.organization,'')
 AND coalesce(oa.directorate,'')=coalesce(ob.directorate,'')
 AND coalesce(oa.unit,'')=coalesce(ob.unit,'')
 AND coalesce(oa.chiefdom,'')=coalesce(ob.chiefdom,'')
), actors AS (SELECT 0 did, :uid uid UNION ALL SELECT did,uid FROM grants),
event_steps AS (
 SELECT e.*, lag(e.status) OVER (PARTITION BY e.request_id ORDER BY e.created_at,e.id) previous,
 row_number() OVER (PARTITION BY e.request_id ORDER BY e.created_at DESC,e.id DESC) last_row
 FROM request_events e
), event_age AS (
 SELECT e.request_id,
 max(CASE WHEN e.status<>coalesce(e.previous,CASE WHEN w.request_id IS NULL THEN 'LEGACY' ELSE 'IN_REVIEW' END) THEN e.created_at END) stage_at,
 max(CASE WHEN e.last_row=1 THEN e.status END) last_status
 FROM event_steps e LEFT JOIN request_workflows w ON w.request_id=e.request_id GROUP BY e.request_id
), analysis_rank AS (
 SELECT a.*, row_number() OVER(PARTITION BY request_id ORDER BY sequence DESC) latest
 FROM analysis_runs a
), completed_rank AS (
 SELECT a.*, row_number() OVER(PARTITION BY request_id ORDER BY sequence DESC) latest
 FROM analysis_runs a WHERE status='COMPLETED'
), request_context AS (
 SELECT r.id, coalesce(w.status,'LEGACY') state,w.owner_hash,
 CASE coalesce(w.status,'LEGACY')
 WHEN 'NEEDS_INFO' THEN 'EMPLOYEE' WHEN 'RESOLVED' THEN NULL
 WHEN 'REFERRED' THEN coalesce(ref.department,'NEEDS_ANALYST')
 WHEN 'ACTION_PLANNED' THEN coalesce(ref.department,'NEEDS_ANALYST')
 ELSE 'NEEDS_ANALYST' END scope,
 ref.department,ass.assignee_id,ass.responsible_scope,person.active assignee_active,person.role assignee_role,
 a.status analysis_status,
 CASE WHEN c.id IS NOT NULL THEN coalesce(c.result_json,'{}') ELSE coalesce(w.result_json,'{}') END result,
 CASE WHEN coalesce(e.last_status,CASE WHEN w.request_id IS NULL THEN 'LEGACY' ELSE 'IN_REVIEW' END)=coalesce(w.status,'LEGACY')
 THEN coalesce(e.stage_at,r.created_at) END stage_at
 FROM requests r LEFT JOIN request_workflows w ON w.request_id=r.id
 LEFT JOIN request_referrals ref ON ref.request_id=r.id AND ref.active=1 AND ref.training_need_confirmed=1
 LEFT JOIN request_assignments ass ON ass.request_id=r.id
 LEFT JOIN portal_users person ON person.id=ass.assignee_id
 LEFT JOIN event_age e ON e.request_id=r.id
 LEFT JOIN analysis_rank a ON a.request_id=r.id AND a.latest=1
 LEFT JOIN completed_rank c ON c.request_id=r.id AND c.latest=1
), request_work AS (
 SELECT 'request' kind,r.id,r.id request_id,a.did,0 kind_order,a.did tie_group,r.stage_at
 FROM request_context r CROSS JOIN actors a
 WHERE r.state<>'RESOLVED' AND coalesce(r.analysis_status,'') NOT IN ('PENDING','PROCESSING')
 AND (
  (:role='EMPLOYEE' AND r.owner_hash='user:'||a.uid AND
   ((r.analysis_status='FAILED' AND r.state='IN_REVIEW') OR
    (coalesce(r.analysis_status,'')<>'FAILED' AND (r.state='NEEDS_INFO' OR
     (r.state='ACTION_PLANNED' AND coalesce(json_extract(CASE WHEN json_valid(r.result) THEN r.result ELSE '{}' END,'$.classification.risk_level'),'')<>'KRITIK')))))
  OR (:role<>'EMPLOYEE' AND r.scope=:role
   AND (:role='NEEDS_ANALYST' OR r.department=:role)
   AND (CASE WHEN r.assignee_active=1 AND r.assignee_role=r.scope AND r.responsible_scope=r.scope THEN r.assignee_id END IS NULL OR r.assignee_id=a.uid)
   AND (a.did=0 OR (r.assignee_id=a.uid AND r.assignee_active=1 AND r.assignee_role=r.scope AND r.responsible_scope=r.scope))
   AND ((r.analysis_status='FAILED' AND :role='NEEDS_ANALYST' AND r.state IN ('LEGACY','IN_REVIEW')) OR
        (coalesce(r.analysis_status,'')<>'FAILED' AND r.state IN ('LEGACY','IN_REVIEW','REFERRED','ACTION_PLANNED'))))
 )), development_scope AS (
 SELECT i.*, CASE WHEN i.assignee_id IS NULL OR i.assignee_id=:uid THEN 0
 ELSE (SELECT min(g.did) FROM grants g WHERE g.uid=i.assignee_id) END did,
 w.status request_status, cat.responsible_unit catalog_unit
 FROM development_items i LEFT JOIN request_workflows w ON w.request_id=i.source_request_id
 LEFT JOIN request_referrals ref ON ref.request_id=i.source_request_id
 LEFT JOIN course_catalog cat ON cat.course_id=i.source_course_id
 WHERE i.responsible_unit=:role AND (:role='NEEDS_ANALYST' OR
 (ref.active=1 AND ref.training_need_confirmed=1 AND ref.department=:role))
), development_work AS (
 SELECT 'development' kind,id,source_request_id request_id,did,1 kind_order,0 tie_group,stage_started_at stage_at
 FROM development_scope WHERE did IS NOT NULL AND state NOT IN ('READY','CANCELLED') AND request_status IN ('REFERRED','ACTION_PLANNED')
), publication_work AS (
 SELECT 'publication' kind,v.id,i.source_request_id request_id,i.did,2 kind_order,0 tie_group,v.updated_at stage_at
 FROM course_versions v JOIN development_scope i ON i.id=v.source_development_id
 WHERE v.state IN ('DRAFT','READY_FOR_PUBLISH') AND i.did IS NOT NULL AND (i.catalog_unit IS NULL OR i.catalog_unit=:role)
), training_work AS (
 SELECT 'training' kind,s.id,0 request_id,a.did,3 kind_order,0 tie_group,s.updated_at stage_at
 FROM training_sessions s CROSS JOIN actors a
 WHERE s.responsible_unit=:role AND :role IN ('NEEDS_ANALYST','TECHNICAL_DESIGN','ENGINEERING_DESIGN')
 AND EXISTS (SELECT 1 FROM portal_users WHERE id=:uid AND active=1)
 AND ((a.did=0 AND (s.coordinator_id IS NULL OR s.coordinator_id=a.uid)) OR (a.did<>0 AND s.coordinator_id=a.uid))
 AND (s.status IN ('DRAFT','SCHEDULED','IN_PROGRESS') OR
 (s.status='COMPLETED' AND (s.attendance_finalized_at IS NULL OR EXISTS
 (SELECT 1 FROM training_enrollments e WHERE e.session_id=s.id AND e.status='ENROLLED' AND e.completion='PENDING'))))
)
"""


def queue_sql(include_evaluations=True):
    extra = ''
    if include_evaluations:
        from .evaluation import inbox_sql
        extra = ' UNION ALL '+inbox_sql()
    return BASE+''', work AS (
 SELECT * FROM request_work UNION ALL SELECT * FROM development_work
 UNION ALL SELECT * FROM publication_work UNION ALL SELECT * FROM training_work
 '''+extra+'''), ranked AS (
 SELECT *, max(0,cast(round((julianday(:now)-julianday(coalesce(stage_at,:now)))*86400,3) AS INTEGER)) age FROM work
 ) '''


def inbox(db, principal, offset=0, limit=20):
    params={'uid':principal.user_id,'role':principal.role,'now':utc_now().replace(tzinfo=None).isoformat(sep=' '),'offset':offset,'limit':limit}
    sql=queue_sql(include_evaluations=True)
    total=db.scalar(text(sql+'SELECT count(*) FROM ranked'),params)
    keys=db.execute(text(sql+'SELECT kind,id,did FROM ranked ORDER BY age DESC,request_id,kind_order,tie_group,id,did LIMIT :limit OFFSET :offset'),params).all()
    return {'items':[hydrate(db,principal,*key) for key in keys],'total':total,'offset':offset,'limit':limit}


def hydrate(db, principal, kind, identifier, delegation_id):
    from . import operations, development, publishing, training
    if kind=='evaluation':
        from .evaluation import inbox_item
        return inbox_item(db,identifier,principal)
    if kind!='request':
        module={'development':development,'publication':publishing,'training':training}[kind]
        rows=module.inbox_items(db,principal,identifiers=[identifier])
        return next(row for row in rows if (row.get('delegation') or {}).get('id',0)==delegation_id)
    from .models import RequestRecord, RequestWorkflow, Notification
    from .workflow import _queue_projection
    from .process import action_projection
    from .analysis_pipeline import current_result
    from .time_policy import utc_stamp
    from . import workflow_policy as policy
    record=db.get(RequestRecord,identifier);flow=db.get(RequestWorkflow,identifier)
    acting=operations.acting_principal(db,principal,delegation_id,identifier) if delegation_id else principal
    ctx=policy.context(db,record,flow)
    actions=operations.required_actions(db,record,flow,acting)
    return {'request_id':record.id,'topic':record.topic or f'Talep #{record.id}','text':record.text[:180],
        'updated_at':utc_stamp(flow.updated_at if flow else record.created_at),
        'responsible_unit_label':policy.DEPARTMENTS.get(ctx['scope'],'İhtiyaç Analizi' if ctx['scope']=='NEEDS_ANALYST' else 'Talep sahibi'),
        'status':ctx['state'],'status_label':policy.STATUSES[ctx['state']],
        'fit_percent':current_result(db,record,flow).get('coverage',{}).get('fit_percent'),
        **action_projection(ctx['state'],active_department=ctx['department']),
        **_queue_projection(db,record,flow,principal.role),'required_actions':actions,'action_required':actions[0]['label'],
        'unread':bool(db.scalar(select(Notification.id).where(Notification.request_id==identifier,Notification.recipient_id==principal.user_id,Notification.read_at.is_(None)).limit(1))),
        'delegation':acting.delegation}
