"""Human-governed canonical vocabulary, version mappings and request verification."""
import re
import unicodedata
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_, and_, delete
from sqlalchemy.exc import IntegrityError
from .skill_models import Skill,SkillGroup,SkillTerm,CourseSkillMapping as Mapping,RequestSkillNeed as Need,SkillAudit
from .models import CourseVersion,DevelopmentItem,RequestRecord,RequestWorkflow,PortalUser
from .time_policy import utc_now,utc_stamp
from .utils import json_loads,json_dumps


def normalize(value):
    # Deliberate Unicode/case/whitespace normalization; no fuzzy semantic merge.
    return ' '.join(unicodedata.normalize('NFKC',value).replace('İ','i').replace('ı','i').casefold().split())


def require_manager(actor):
    if actor.role not in ('NEEDS_ANALYST','TECHNICAL_DESIGN','ENGINEERING_DESIGN'):
        raise HTTPException(403,'Yetkinlik kataloğu için yönetim erişimi gerekir.')


def require_steward(actor):
    if actor.role!='NEEDS_ANALYST':raise HTTPException(403,'Ortak yetkinlik sözlüğünü ihtiyaç analisti yönetir.')


def audit(db,actor,action,**values):
    details=values.pop('details',{})
    if getattr(actor,'delegation',None):details={**details,'delegation':actor.delegation}
    db.add(SkillAudit(actor_id=actor.user_id,actor_name=actor.display_name,action=action,details_json=json_dumps(details),**values))


def skill_data(db,row):
    group=db.get(SkillGroup,row.group_id)
    return {'id':row.id,'canonical_name':row.canonical_name,'description':row.description,'status':row.status,
        'group_id':row.group_id,'group':group.name,'version':row.version,'created_at':utc_stamp(row.created_at),
        'updated_at':utc_stamp(row.updated_at),'aliases':list(db.scalars(select(SkillTerm.label).where(
            SkillTerm.skill_id==row.id,SkillTerm.normalized!=row.normalized_name).order_by(SkillTerm.normalized)))}


def get_skill(db,identifier,active=False):
    row=db.get(Skill,identifier)
    if not row:raise HTTPException(404,'Yetkinlik bulunamadı.')
    if active and row.status!='ACTIVE':raise HTTPException(422,'Yeni ilişki için aktif yetkinlik seçin.')
    return row


def write_skill(db,actor,payload,identifier=None):
    require_steward(actor)
    if not db.get(SkillGroup,payload.group_id):raise HTTPException(422,'Geçerli yetkinlik grubu seçin.')
    name=normalize(payload.canonical_name)
    if not name:raise HTTPException(422,'Yetkinlik adı boş olamaz.')
    terms={normalize(v):v for v in [payload.canonical_name,*payload.aliases]}
    try:
        if identifier:
            row=get_skill(db,identifier)
            before=skill_data(db,row)
            changed=db.execute(update(Skill).where(Skill.id==identifier,Skill.version==payload.expected_version)
                .values(version=Skill.version+1,updated_at=utc_now()))
            if changed.rowcount!=1:raise HTTPException(409,'Yetkinlik güncellendi. Güncel kaydı açın.')
        else:
            row=Skill(canonical_name=payload.canonical_name,normalized_name=name,description=payload.description,group_id=payload.group_id,created_by=actor.user_id)
            db.add(row);db.flush();before=None
        for normalized,label in terms.items():
            existing=db.get(SkillTerm,normalized)
            if existing and existing.skill_id!=row.id:raise HTTPException(409,'Bu ad veya eş ad başka bir canonical yetkinliğe bağlı.')
            if not existing:db.add(SkillTerm(normalized=normalized,label=label,skill_id=row.id,created_by=actor.user_id))
        row.canonical_name,row.normalized_name,row.description,row.group_id,row.status=payload.canonical_name,name,payload.description,payload.group_id,payload.status
        db.flush();audit(db,actor,'SKILL_UPDATED' if identifier else 'SKILL_CREATED',skill_id=row.id,details={'before':before,'after':skill_data(db,row)})
        db.commit();return skill_data(db,row)
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Yetkinlik adı veya eş ad eşzamanlı işlemde kullanıldı.')


def search_query(search='',active=False):
    stmt=select(Skill)
    if search:
        stmt=stmt.where(Skill.id.in_(select(SkillTerm.skill_id).where(SkillTerm.normalized.icontains(normalize(search),autoescape=True))))
    if active:stmt=stmt.where(Skill.status=='ACTIVE')
    return stmt


def options(db,search=''):
    return [skill_data(db,row) for row in db.scalars(search_query(search,True).order_by(Skill.normalized_name).limit(100))]


def mappings(db,version):
    return [{'id':row.id,'skill_id':row.skill_id,'skill':db.get(Skill,row.skill_id).canonical_name,
        'skill_status':db.get(Skill,row.skill_id).status,'outcome_index':row.outcome_index,'outcome_text':row.outcome_text,
        'source':row.source,'created_by':row.created_by,'created_at':utc_stamp(row.created_at)}
        for row in db.scalars(select(Mapping).where(Mapping.course_version_id==version.id).order_by(Mapping.skill_id,Mapping.outcome_index))]


def mapping_editable(db,version,actor):
    from .publishing import permission
    item=db.get(DevelopmentItem,version.source_development_id) if version.source_development_id else None
    return bool(version.state=='DRAFT' and item and permission(db,item,actor))


def save_mappings(db,version,actor,payload):
    from . import publishing
    if not mapping_editable(db,version,actor):raise HTTPException(403,'Eşleştirmeler yalnızca yetkili ders taslağında düzenlenebilir.')
    publishing.lock(db,version,payload.expected_version)
    pairs={(row.skill_id,row.outcome_index) for row in payload.mappings}
    if len(pairs)!=len(payload.mappings):raise HTTPException(422,'Aynı kazanım/yetkinlik eşleştirmesi yinelenemez.')
    outcomes=json_loads(version.outcomes_json,[])
    for skill_id,index in pairs:
        get_skill(db,skill_id,True)
        # Serialize with deactivation, so inactive terms cannot enter a new snapshot.
        db.execute(update(Skill).where(Skill.id==skill_id,Skill.status=='ACTIVE').values(version=Skill.version))
        if index>=len(outcomes):raise HTTPException(422,'Kazanım bu ders sürümüne ait değil.')
    before=mappings(db,version)
    db.execute(delete(Mapping).where(Mapping.course_version_id==version.id))
    for skill_id,index in sorted(pairs):
        db.add(Mapping(course_version_id=version.id,skill_id=skill_id,outcome_index=index,
            outcome_text=outcomes[index]['text'] if index>=0 else None,created_by=actor.user_id))
    db.flush();audit(db,actor,'COURSE_SKILLS_SAVED',course_version_id=version.id,details={'before':before,'after':mappings(db,version),'publication_revision':version.revision})
    # Keep the existing publication event stream and version contract.
    publishing.record_event(db,version,actor,'EDIT');db.commit()
    return publishing.detail(db,version,actor)


def candidate_data(db,record,flow):
    from .analysis_pipeline import current_result,latest_run
    result=current_result(db,record,flow);run=latest_run(db,record.id,completed=True)
    latest=latest_run(db,record.id)
    if latest and latest.status in ('PENDING','PROCESSING'):
        return {'candidates':[],'unmapped_needs':[],'explanation':'Güncel analiz tamamlandığında yetkinlik adayları gösterilir.'}
    needs=result.get('classification',{}).get('requirements',[])
    terms=list(db.execute(select(SkillTerm,Skill).join(Skill,Skill.id==SkillTerm.skill_id).where(Skill.status=='ACTIVE')))
    candidates={};unmatched=[]
    for need in needs:
        label=str(need.get('label',''));normalized=normalize(label);found=False
        for term,skill in terms:
            if re.search(r'(?<!\w)'+re.escape(term.normalized)+r'(?!\w)',normalized):
                found=True;candidates.setdefault(skill.id,{'skill_id':skill.id,'skill':skill.canonical_name,'source':'AI_SUGGESTED',
                    'analysis_run_id':run.id if run else None,'labels':[]})['labels'].append(label)
        if not found and label:unmatched.append(label)
    return {'candidates':list(candidates.values()),'unmapped_needs':unmatched,
        'explanation':'Mevcut analizdeki ihtiyaç metinleri tanımlı ad/eş adlarla eşleştirilir. İnsan doğrulaması beklenir; yeni yetkinlik otomatik oluşturulmaz.'}


def need_data(db,row):
    skill=get_skill(db,row.skill_id)
    return {'id':row.id,'skill_id':skill.id,'skill':skill.canonical_name,'skill_status':skill.status,'source':row.source,
        'human_verified':row.human_verified,'active':row.active,'version':row.version,'analysis_run_id':row.analysis_run_id,
        'verified_by':row.verified_by,'verified_at':utc_stamp(row.verified_at),'created_at':utc_stamp(row.created_at),
        'provenance':json_loads(row.provenance_json,{})}


def request_section(db,record,flow,role):
    rows=list(db.scalars(select(Need).where(Need.request_id==record.id).order_by(Need.id)))
    candidates=candidate_data(db,record,flow) if role=='NEEDS_ANALYST' else {}
    if candidates:
        withdrawn={(r.skill_id,r.analysis_run_id) for r in rows if not r.active}
        candidates['candidates']=[r for r in candidates['candidates'] if (r['skill_id'],r['analysis_run_id']) not in withdrawn]
    return {'items':[need_data(db,r) for r in rows],'can_verify':role=='NEEDS_ANALYST',
        **candidates}


def request_context(db,identifier,actor,mutation=False):
    from .operations import can_see
    person=db.get(PortalUser,actor.user_id)
    record=db.get(RequestRecord,identifier);flow=db.get(RequestWorkflow,identifier)
    if not record or not can_see(db,person,identifier):raise HTTPException(404,'Talep bulunamadı.')
    if mutation:
        require_steward(actor)
        # Metadata verification does not advance or version the request workflow.
        db.execute(update(RequestRecord).where(RequestRecord.id==identifier).values(topic=RequestRecord.topic))
    return record,flow


def add_need(db,record,flow,actor,payload,commit=True):
    require_steward(actor)
    if payload.dismiss and (payload.source!='AI_SUGGESTED' or payload.confirm):
        raise HTTPException(422,'Yalnızca doğrulanmamış analiz adayı çıkarılabilir.')
    get_skill(db,payload.skill_id,True)
    previous=db.scalar(select(Need).where(Need.request_id==record.id,Need.skill_id==payload.skill_id,Need.active.is_(True)))
    if previous:return need_data(db,previous)
    provenance={'origin':payload.source};analysis_id=None
    if payload.source=='AI_SUGGESTED':
        candidate=next((r for r in candidate_data(db,record,flow)['candidates'] if r['skill_id']==payload.skill_id),None)
        if not candidate or candidate['analysis_run_id']!=payload.analysis_run_id:raise HTTPException(409,'Aday güncel analizle eşleşmiyor; talebi yenileyin.')
        provenance.update(matched_needs=candidate['labels'],method='EXACT_KNOWN_TERM');analysis_id=candidate['analysis_run_id']
        if payload.dismiss:
            previous=db.scalar(select(Need).where(Need.request_id==record.id,Need.skill_id==payload.skill_id,
                Need.analysis_run_id==analysis_id,Need.active.is_(False)))
            if previous:return need_data(db,previous)
    confirmed=payload.source=='MANUAL' or payload.confirm
    source='HUMAN_CONFIRMED' if payload.source=='AI_SUGGESTED' and payload.confirm else payload.source
    row=Need(request_id=record.id,skill_id=payload.skill_id,source=source,human_verified=confirmed,active=not payload.dismiss,
        analysis_run_id=analysis_id,created_by=actor.user_id,verified_by=actor.user_id if confirmed else None,
        verified_at=utc_now() if confirmed else None,provenance_json=json_dumps(provenance))
    db.add(row);db.flush();audit(db,actor,'CANDIDATE_DISMISSED' if payload.dismiss else 'NEED_ADDED',skill_id=row.skill_id,request_need_id=row.id,details=need_data(db,row))
    if confirmed:
        from .skill_evidence import from_need
        from_need(db,row,flow)
    if commit:db.commit()
    return need_data(db,row)


def change_need(db,record,flow,actor,row,payload):
    require_steward(actor)
    if not row or row.request_id!=record.id:raise HTTPException(404,'Yetkinlik ihtiyacı bulunamadı.')
    if not row.active:raise HTTPException(409,'Bu ilişki daha önce çıkarılmış.')
    if payload.action=='CONFIRM':
        get_skill(db,row.skill_id,True)
        if row.human_verified:raise HTTPException(409,'Bu ihtiyaç zaten doğrulandı.')
        from .analysis_pipeline import latest_run
        latest=latest_run(db,record.id)
        if latest and latest.status in ('PENDING','PROCESSING'):raise HTTPException(409,'Güncel analiz tamamlanmadan aday doğrulanamaz.')
        latest=latest_run(db,record.id,completed=True)
        if row.analysis_run_id!=(latest.id if latest else None):raise HTTPException(409,'Analiz değişti; güncel adayı kullanın veya elle eşleştirin.')
    before=need_data(db,row)
    values={'version':Need.version+1}
    if payload.action=='CONFIRM':values.update(source='HUMAN_CONFIRMED',human_verified=True,verified_by=actor.user_id,verified_at=utc_now())
    else:values['active']=False
    changed=db.execute(update(Need).where(Need.id==row.id,Need.version==payload.expected_version,Need.active.is_(True)).values(**values))
    if changed.rowcount!=1:raise HTTPException(409,'Yetkinlik ihtiyacı başka bir işlemde değişti.')
    db.refresh(row);audit(db,actor,'NEED_'+payload.action,skill_id=row.skill_id,request_need_id=row.id,details={'before':before,'after':need_data(db,row)})
    if payload.action=='REPLACE':
        if not payload.replacement_skill_id or payload.replacement_skill_id==row.skill_id:raise HTTPException(422,'Başka mevcut bir yetkinlik seçin.')
        from .skill_schemas import NeedCreate
        add_need(db,record,flow,actor,NeedCreate(skill_id=payload.replacement_skill_id),commit=False)
    if payload.action=='CONFIRM':
        from .skill_evidence import from_need
        from_need(db,row,flow)
    db.commit();return request_section(db,record,flow,actor.role)
