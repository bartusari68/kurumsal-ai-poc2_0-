"""Human portfolio lifecycle and receipts into existing creation transactions."""
from fastapi import HTTPException
from sqlalchemy import select,update,func,or_
from sqlalchemy.exc import IntegrityError
from .portfolio_models import PortfolioItem as Item,PortfolioEvent as Event,PortfolioHandoff as Handoff,PortfolioLink as Link
from .models import PortalUser,RequestRecord,RequestWorkflow,CourseVersion,CourseCatalog,DevelopmentItem,TrainingSession,RequestSkillNeed,CourseSkillMapping
from . import portfolio_policy as policy,portfolio_query
from .time_policy import utc_now,utc_stamp
from .utils import json_dumps,json_loads

def get(db,actor,identifier):
    policy.require_manager(actor)
    row=db.get(Item,identifier)
    if not row: raise HTTPException(404,'Planlama konusu bulunamadı.')
    return row

def brief(row):
    return {k:getattr(row,k) for k in ('id','skill_id','title','scope','owner_unit','assignee_id','state','rationale','decision','decision_note','version','created_by')} | {
        'state_label':policy.STATES[row.state],'decision_label':policy.DECISIONS.get(row.decision),
        'created_at':utc_stamp(row.created_at),'updated_at':utc_stamp(row.updated_at)}

def items(db,actor,skill_id=None,offset=0,limit=20):
    policy.require_manager(actor)
    q=select(Item)
    if skill_id:q=q.where(Item.skill_id==skill_id)
    return {'items':[brief(r) for r in db.scalars(q.order_by(Item.id.desc()).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(q.subquery())),'offset':offset,'limit':limit}

def audit(db,row,actor,action,before=None,note='',snapshot=None):
    db.add(Event(item_id=row.id,version=row.version,action=action,from_state=before,to_state=row.state,
        actor_id=actor.user_id,actor_name=actor.display_name,note=note,decision=row.decision,
        snapshot_json=json_dumps(snapshot or {})))

def detail(db,actor,identifier):
    row=get(db,actor,identifier)
    assignee=db.get(PortalUser,row.assignee_id) if row.assignee_id else None
    return {**brief(row),'assignee_name':assignee.display_name if assignee else 'İhtiyaç analizi birim kuyruğu',
        'actions':[{'code':code,'label':v[2]} for code,v in policy.TRANSITIONS.items() if row.state==v[0] and (not row.assignee_id or row.assignee_id==actor.user_id)],
        'decisions':policy.DECISIONS,'states':policy.STATES,'can_handoff':row.state=='DECIDED' and row.decision in policy.HANDOFFS and (not row.assignee_id or row.assignee_id==actor.user_id),
        'history':[{'id':e.id,'action':e.action,'from_state':e.from_state,'to_state':e.to_state,'actor':e.actor_name,
            'from_label':policy.STATES.get(e.from_state,'Başlangıç'),'to_label':policy.STATES[e.to_state],
            'note':e.note,'decision':e.decision,'snapshot':json_loads(e.snapshot_json,{}),'at':utc_stamp(e.created_at)}
            for e in db.scalars(select(Event).where(Event.item_id==row.id).order_by(Event.id))],
        'handoffs':handoffs(db,actor,item_id=row.id)}

def create(db,actor,payload):
    policy.require_manager(actor)
    snapshot=portfolio_query.skill(db,actor,payload.skill_id)
    if snapshot['status']!='ACTIVE':raise HTTPException(422,'Aktif bir yetkinlik seçin.')
    if payload.assignee_id:
        u=db.get(PortalUser,payload.assignee_id)
        if not u or not u.active or u.role!='NEEDS_ANALYST':raise HTTPException(422,'Aktif ihtiyaç analizi sorumlusu seçin.')
    row=Item(**payload.model_dump(),created_by=actor.user_id)
    try:
        db.add(row);db.flush();audit(db,row,actor,'CREATED',note=row.rationale,snapshot=snapshot);db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Bu yetkinlik ve kapsam için açık bir planlama konusu zaten var.')
    return detail(db,actor,row.id)

def lock(db,row,actor,expected):
    if row.assignee_id and row.assignee_id!=actor.user_id:raise HTTPException(403,'Bu konunun atanan sorumlusu işlem yapmalıdır.')
    # Obtain SQLite writer reservation without mutating item history/version.
    db.execute(update(PortalUser).where(PortalUser.id==actor.user_id).values(active=PortalUser.active))
    db.refresh(row)
    if row.version!=expected:raise HTTPException(409,'Planlama konusu güncellendi. Güncel kaydı açın; taslağınız korunur.')

def act(db,actor,identifier,payload):
    row=get(db,actor,identifier);lock(db,row,actor,payload.expected_version)
    before,target,_=policy.TRANSITIONS[payload.action]
    if row.state!=before:raise HTTPException(422,'Bu aşamada bu işlem yapılamaz.')
    if (payload.action=='DECIDE') != bool(payload.decision):raise HTTPException(422,'Karar yalnızca karar kaydetme işleminde zorunludur.')
    snapshot=portfolio_query.skill(db,actor,row.skill_id) if payload.action=='DECIDE' else None
    row.state=target;row.version+=1;row.updated_at=utc_now()
    if payload.decision:row.decision=payload.decision;row.decision_note=payload.note
    db.flush();audit(db,row,actor,payload.action,before,payload.note,snapshot);db.commit()
    return detail(db,actor,identifier)

def recipient_actor(user):
    from .portal_auth import Principal
    return Principal(user_id=user.id,username=user.username,display_name=user.display_name,role=user.role)

def target_context(db,row,recipient,target_id):
    """Reuse actual target permissions. A decision never grants creation authority."""
    from . import training,development
    kind=policy.HANDOFFS[row.decision];actor=recipient_actor(recipient)
    context={'skill_id':row.skill_id,'title':row.title,'kind':kind}
    if kind=='REQUEST':
        if recipient.role!='EMPLOYEE' or target_id:raise HTTPException(422,'Yeni ihtiyacı mevcut çalışan talep ekranında hazırlayacak kişiyi seçin; hedef kayıt gerekmez.')
        # No aggregate evidence or private observations are copied to the recipient.
        from .skill_models import Skill
        skill=db.get(Skill,row.skill_id)
        context['prefill']=f'L&D planlama konusu #{row.id}. Yetkinlik: {skill.canonical_name}.\nBu alandaki iş ihtiyacım ve beklenen çıktı: '
    elif kind=='SESSION':
        version=db.get(CourseVersion,target_id) if target_id else None
        catalog=db.get(CourseCatalog,version.course_id) if version else None
        mapped=db.scalar(select(CourseSkillMapping.id).where(CourseSkillMapping.skill_id==row.skill_id,CourseSkillMapping.course_version_id==target_id))
        if not version or not catalog or not mapped or version.state!='PUBLISHED' or catalog.current_version_id!=version.id:raise HTTPException(422,'Bu yetkinliğe bağlı güncel yayımlanmış sürümü seçin.')
        if recipient.role not in training.policy.MANAGERS or catalog.responsible_unit and catalog.responsible_unit!=recipient.role:raise HTTPException(403,'Seçilen kişi bu ders için oturum planlayamaz.')
        context.update(course_version_id=version.id,course_title=version.title)
    else:
        record=db.get(RequestRecord,target_id) if target_id else None;flow=db.get(RequestWorkflow,target_id) if record else None
        from .workflow import owned_request
        if not record:raise HTTPException(422,'Zenginleştirme için doğrulanmış ve yönlendirilmiş kaynak talep seçin.')
        owned_request(db,record.id,actor.token_hash,admin=True,role=actor.role)
        need=db.scalar(select(RequestSkillNeed.id).where(RequestSkillNeed.request_id==record.id,RequestSkillNeed.skill_id==row.skill_id,RequestSkillNeed.active.is_(True),RequestSkillNeed.human_verified.is_(True)))
        from .workflow_policy import context as workflow_context
        draft=development.source_draft(db,record,flow);ctx=workflow_context(db,record,flow)
        if not need or not draft or draft['work_type']!='COURSE_ENRICHMENT':raise HTTPException(422,'Kaynak talep güncel analiz ve insan kararıyla zenginleştirme akışına hazır değil.')
        if recipient.role!=draft['responsible_unit'] or not ctx['analysis_review_ready'] or ctx['assignee'] and ctx['assignee']['id']!=recipient.id:raise HTTPException(403,'Talebin mevcut sorumlusunu seçin.')
        context.update(source_request_id=record.id,source_course_id=draft['source_course_id'])
    return context

def issue(db,actor,identifier,payload):
    row=get(db,actor,identifier);lock(db,row,actor,payload.expected_version)
    if row.state!='DECIDED' or row.decision not in policy.HANDOFFS:raise HTTPException(422,'İş akışına geçiş gerektiren kayıtlı bir karar yok.')
    user=db.get(PortalUser,payload.recipient_id)
    if not user or not user.active:raise HTTPException(422,'Aktif bir alıcı seçin.')
    context=target_context(db,row,user,payload.target_id)
    old=db.scalar(select(Handoff).where(Handoff.item_id==row.id,Handoff.recipient_id==user.id,Handoff.kind==context['kind'],Handoff.target_key==(payload.target_id or 0)))
    if old:return handoff_data(db,old,actor)
    decision=db.scalar(select(Event).where(Event.item_id==row.id,Event.action=='DECIDE'))
    entry=Handoff(item_id=row.id,recipient_id=user.id,decision_event_id=decision.id,kind=context['kind'],
        target_key=payload.target_id or 0,context_json=json_dumps(context),created_by=actor.user_id)
    db.add(entry);db.commit()
    return handoff_data(db,entry,actor)

def handoff_data(db,row,actor,link=None,item=None,joined=False):
    item=item or db.get(Item,row.item_id)
    if actor.role!='NEEDS_ANALYST' and row.recipient_id!=actor.user_id:raise HTTPException(404,'Planlama geçişi bulunamadı.')
    if link is None and not joined:link=db.scalar(select(Link).where(Link.handoff_id==row.id))
    return {'id':row.id,'item_id':row.item_id,'recipient_id':row.recipient_id,'kind':row.kind,
        'context':json_loads(row.context_json,{}),'created_at':utc_stamp(row.created_at),'decision_event_id':row.decision_event_id,
        'available':item.state=='DECIDED' and not link,'link':{'request_id':link.request_id,'development_id':link.development_id,'session_id':link.session_id} if link else None}

def handoffs(db,actor,item_id=None):
    q=select(Handoff,Item,Link).join(Item,Item.id==Handoff.item_id).outerjoin(Link,Link.handoff_id==Handoff.id)
    if item_id:
        policy.require_manager(actor);q=q.where(Handoff.item_id==item_id)
    else:q=q.where(Handoff.recipient_id==actor.user_id)
    # Batch joined list; separate detail only for explicit continuation.
    result=[]
    for h,i,l in db.execute(q.order_by(Handoff.id.desc()).limit(100)):
        value=handoff_data(db,h,actor,l,i,joined=True)
        if actor.role!='NEEDS_ANALYST' and h.kind!='REQUEST':
            try:target_context(db,i,db.get(PortalUser,actor.user_id),h.target_key)
            except HTTPException:
                value.update(context={'title':'Kaynak erişimi değişmiş planlama geçişi','kind':h.kind},available=False,link=None)
        result.append(value)
    return result

def targets(db,actor,identifier):
    item=get(db,actor,identifier)
    if item.decision=='PLAN_ADDITIONAL_SESSIONS':
        q=select(CourseVersion).join(CourseCatalog,CourseCatalog.current_version_id==CourseVersion.id).where(
            CourseVersion.state=='PUBLISHED',CourseVersion.id.in_(select(CourseSkillMapping.course_version_id).where(CourseSkillMapping.skill_id==item.skill_id)))
        return {'items':[{'id':v.id,'title':f'{v.title} · Sürüm {v.version_number}'} for v in db.scalars(q.limit(100))]}
    if item.decision=='START_COURSE_ENRICHMENT':
        q=select(RequestRecord).join(RequestWorkflow,RequestWorkflow.request_id==RequestRecord.id).where(
            RequestWorkflow.status.in_(('REFERRED','ACTION_PLANNED')),RequestRecord.id.in_(select(RequestSkillNeed.request_id).where(
                RequestSkillNeed.skill_id==item.skill_id,RequestSkillNeed.active.is_(True),RequestSkillNeed.human_verified.is_(True))))
        return {'items':[{'id':r.id,'title':f'#{r.id} · {r.topic or "Kaynak talep"}'} for r in db.scalars(q.order_by(RequestRecord.id.desc()).limit(100))]}
    return {'items':[]}

def accept(db,actor,handoff_id,kind,entity):
    """Called BEFORE the existing creation transaction commits; failures roll it back."""
    if not handoff_id:return
    row=db.get(Handoff,handoff_id)
    if not row or row.recipient_id!=actor.user_id or row.kind!=kind:raise HTTPException(404,'Bu işlem için planlama kaynağı bulunamadı.')
    item=db.get(Item,row.item_id)
    previous=db.scalar(select(Link).where(Link.handoff_id==row.id))
    field={'REQUEST':'request_id','DEVELOPMENT':'development_id','SESSION':'session_id'}[kind]
    if previous:
        if getattr(previous,field)==entity.id:return
        raise HTTPException(409,'Bu planlama geçişi zaten bir kayda bağlandı.')
    if item.state!='DECIDED':raise HTTPException(409,'Planlama konusu kapatılmış; yeni kayıt oluşturulamaz.')
    if kind=='SESSION' and entity.course_version_id!=row.target_key:raise HTTPException(422,'Oturum seçilen ders sürümüne ait olmalıdır.')
    if kind=='DEVELOPMENT' and (entity.source_request_id!=row.target_key or entity.work_type!='COURSE_ENRICHMENT'):raise HTTPException(422,'Geliştirme, seçilen talebin zenginleştirme çalışması olmalıdır.')
    db.add(Link(handoff_id=row.id,created_by=actor.user_id,**{field:entity.id}));db.flush()

def retry_request(db,request_id,handoff_id):
    link=db.scalar(select(Link).where(Link.request_id==request_id))
    if (link.handoff_id if link else None)!=handoff_id:raise HTTPException(409,'Aynı gönderim anahtarında planlama kaynağı değiştirilemez.')

def options(db,actor,search=''):
    policy.require_manager(actor)
    q=select(PortalUser).where(PortalUser.active.is_(True))
    if search:q=q.where(or_(PortalUser.display_name.contains(search,autoescape=True),PortalUser.username.contains(search,autoescape=True)))
    return {'users':[{'id':u.id,'name':u.display_name,'role':u.role} for u in db.scalars(q.order_by(PortalUser.display_name).limit(100))]}
