from app.operations import *
from sqlalchemy import select, or_
import app.development as _development
_development_scope=dict(vars(_development))
exec("def development_inbox_items(db, principal):\n    from .operations import valid_delegation\n    rows = db.scalars(query(principal).where(Item.state.not_in(policy.TERMINAL)))\n    items = []\n    for item in rows:\n        actor = principal\n        if not can_act(db, item, actor):\n            delegation = next((row for row in db.scalars(select(Delegation).where(Delegation.delegator_id == item.assignee_id,\n                Delegation.delegate_id == principal.user_id)) if valid_delegation(db, row, principal.user_id)), None)\n            if not delegation:\n                continue\n            actor = authorized_actor(db, item, principal, delegation.id)\n        if not can_act(db, item, actor):\n            continue\n        row = summary(db, item)\n        items.append({**row, 'kind': 'development', 'development_id': item.id, 'request_id': item.source_request_id,\n            'topic': item.title, 'text': item.summary[:180], 'action_required': row['next_action'], 'fit_percent': None,\n            'delegation': actor.delegation, 'unread': False})\n    return items\n", _development_scope)
development_inbox_items=_development_scope['development_inbox_items']
import app.publishing as _publishing
_publishing_scope=dict(vars(_publishing))
exec("def publishing_inbox_items(db, principal):\n    rows=db.scalars(select(Version).where(Version.state.in_(('DRAFT','READY_FOR_PUBLISH'))))\n    items=[]\n    from .operations import valid_delegation\n    for row in rows:\n        item=db.get(DevelopmentItem,row.source_development_id)\n        if not item or not development.visible(db,item,principal):continue\n        actor=principal\n        if not permission(db,item,actor):\n            delegation=next((value for value in db.scalars(select(Delegation).where(Delegation.delegator_id==item.assignee_id,\n                Delegation.delegate_id==principal.user_id)) if valid_delegation(db,value,principal.user_id)),None)\n            if not delegation:continue\n            actor=development.authorized_actor(db,item,principal,delegation.id)\n        if not permission(db,item,actor):continue\n        items.append({'kind':'publication','publication_id':row.id,'request_id':item.source_request_id,'topic':row.title,\n            'title':row.title,'state':row.state,'state_label':policy.STATES[row.state],'work_type_label':'Ders yayını',\n            'action_required':'Ders sürümünü yayınla' if row.state=='READY_FOR_PUBLISH' else 'Ders sürümünü yayınlamaya hazırla',\n            'updated_at':utc_stamp(row.updated_at),'responsible_unit_label':policy.DEPARTMENTS[item.responsible_unit],\n            'aging':{'current_stage_seconds':max(0,int((utc_now()-row.updated_at).total_seconds()))},'delegation':actor.delegation,\n            'assignee':development.summary(db,item)['assignee'],'unread':False,'fit_percent':None})\n    return items\n", _publishing_scope)
publishing_inbox_items=_publishing_scope['publishing_inbox_items']
import app.training as _training
_training_scope=dict(vars(_training))
exec("def training_inbox_items(db, actor):\n    rows = db.scalars(select(Session).where(visible_query(actor), Session.status != 'CANCELLED'))\n    result=[]\n    for row in rows:\n        next_label=next_action(db,row)\n        if next_label=='Bekleyen işlem yok': continue\n        actors=[actor]+[delegated(db,row,actor,d['id']) for d in delegation_options(db,row,actor)]\n        for effective in actors:\n            if not can_act(db,row,effective):continue\n            result.append({'kind':'training','session_id':row.id,'request_id':0,'title':row.title,\n                'state':row.status,'state_label':policy.STATES[row.status], 'status':row.status,\n                'work_type_label':'Eğitim oturumu','responsible_unit_label':policy.ROLES[row.responsible_unit],\n                'assignee':user_info(db,row.coordinator_id),'updated_at':utc_stamp(row.updated_at),\n                'aging':{'current_stage_seconds':max(0,int((utc_now()-as_utc(row.updated_at)).total_seconds()))},\n                'action_required':next_label,'delegation':getattr(effective,'delegation',None)})\n    return result\n", _training_scope)
training_inbox_items=_training_scope['training_inbox_items']

def legacy_inbox(db, principal, offset=0, limit=20):
    from app.workflow import audience_scope, _queue_projection
    from app.process import action_projection
    from app.analysis_pipeline import current_result
    normal = select(RequestRecord, RequestWorkflow).outerjoin(RequestWorkflow).where(
        audience_scope(principal.token_hash, principal.role != 'EMPLOYEE', principal.role),
        or_(RequestWorkflow.status != 'RESOLVED', RequestWorkflow.request_id.is_(None)))
    candidates = {(record.id, None): (record, flow, principal) for record, flow in db.execute(normal)}
    for row in db.scalars(select(Delegation).where(Delegation.delegate_id == principal.user_id, Delegation.active.is_(True))):
        if not valid_delegation(db, row):
            continue
        query = select(RequestRecord, RequestWorkflow).join(RequestWorkflow)
        if principal.role == 'EMPLOYEE':
            query = query.where(RequestWorkflow.owner_hash == f'user:{row.delegator_id}')
        else:
            query = query.join(RequestAssignment).where(RequestAssignment.assignee_id == row.delegator_id)
        for record, flow in db.execute(query):
            if delegation_scope(db, row, record, flow):
                candidates[(record.id, row.id)] = (record, flow, acting_principal(db, principal, row.id, record.id))
    items = []
    unread = set(db.scalars(select(Notification.request_id).where(Notification.recipient_id == principal.user_id, Notification.read_at.is_(None))))
    for record, flow, acting in candidates.values():
        actions = required_actions(db, record, flow, acting)
        if not actions:
            continue
        ctx = policy.context(db, record, flow)
        items.append({'request_id': record.id, 'topic': record.topic or f'Talep #{record.id}', 'text': record.text[:180],
            'updated_at': utc_stamp(flow.updated_at if flow else record.created_at),
            'responsible_unit_label': policy.DEPARTMENTS.get(ctx['scope'], 'İhtiyaç Analizi' if ctx['scope'] == 'NEEDS_ANALYST' else 'Talep sahibi'),
            'status': ctx['state'], 'status_label': policy.STATUSES[ctx['state']],
            'fit_percent': current_result(db, record, flow).get('coverage', {}).get('fit_percent'),
            **action_projection(ctx['state'], active_department=ctx['department']),
            **_queue_projection(db, record, flow, principal.role), 'required_actions': actions,
            'action_required': actions[0]['label'],
            'unread': record.id in unread, 'delegation': acting.delegation})
    from inbox_reference import development_inbox_items as inbox_items
    items.extend(inbox_items(db, principal))
    from inbox_reference import publishing_inbox_items as publication_inbox
    items.extend(publication_inbox(db, principal))
    from inbox_reference import training_inbox_items as training_inbox
    items.extend(training_inbox(db, principal))
    items.sort(key=lambda item: (-(item['aging']['current_stage_seconds'] or 0), item['request_id']))
    return {'items': items[offset:offset+limit], 'total': len(items), 'offset': offset, 'limit': limit}
