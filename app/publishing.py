"""Explicit, atomic publication of reviewed development snapshots."""
from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from .models import (Course, CourseCatalog as Catalog, CourseVersion as Version, CourseVersionDocument as Document,
    PublicationEvent as Event, DevelopmentItem, DevelopmentEvent, RequestWorkflow, AnalysisRun, RequestDecision,
    PortalUser, DocumentIndex, Delegation)
from . import development, publishing_policy as policy
from .time_policy import utc_now, utc_stamp
from .utils import json_dumps, json_loads


def permission(db, item, principal):
    actor = (principal.delegation or {}).get('delegator_id', principal.user_id)
    if not development.visible(db, item, principal) or principal.role != item.responsible_unit:
        return False
    catalog = db.get(Catalog, item.source_course_id) if item.source_course_id else None
    return bool((item.assignee_id is None or item.assignee_id == actor) and
                (not catalog or catalog.responsible_unit in (None, principal.role)))


def source(db, item):
    ready = db.scalar(select(DevelopmentEvent).where(DevelopmentEvent.item_id == item.id,
        DevelopmentEvent.action == 'APPROVE').order_by(DevelopmentEvent.id.desc()).limit(1))
    review = db.scalar(select(DevelopmentEvent).where(DevelopmentEvent.item_id == item.id,
        DevelopmentEvent.action == 'SUBMIT_REVIEW').order_by(DevelopmentEvent.id.desc()).limit(1))
    if item.state != 'READY' or not ready or not review or ready.content_revision != item.content_revision or review.content_revision != item.content_revision:
        raise HTTPException(422, 'Yayın için güncel içeriği incelenmiş ve hazır olarak onaylanmış çalışma gerekir.')
    snapshot = json_loads(ready.snapshot_json, {})
    if snapshot != json_loads(review.snapshot_json, {}) or snapshot != development.artifacts(db, item):
        raise HTTPException(422, 'Tasarım içeriği onaylanan inceleme sürümüyle eşleşmiyor.')
    return ready, review, snapshot


def lock(db, row, expected):
    changed = db.execute(update(Version).where(Version.id == row.id, Version.revision == expected,
        Version.state.in_(('DRAFT','READY_FOR_PUBLISH'))).values(revision=Version.revision+1, updated_at=utc_now())
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Ders sürümü başka bir işlemde değişti. Taslağınız korunur; güncel kayıtla karşılaştırın.')
    db.refresh(row)


def load(db, identifier, principal, header=None, mutation=False):
    row = db.get(Version, identifier)
    if not row:
        raise HTTPException(404, 'Ders sürümü bulunamadı.')
    item = db.get(DevelopmentItem, row.source_development_id) if row.source_development_id else None
    if mutation and item:
        db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == item.source_request_id).values(version=RequestWorkflow.version))
        db.expire_all()
    actor = principal
    if row.state not in ('PUBLISHED','ARCHIVED') or mutation or header is not None:
        if not item:
            raise HTTPException(403, 'Önceki katalog sürümü doğrudan değiştirilemez.')
        if header is not None and not header.isdecimal():
            raise HTTPException(403, 'Geçersiz vekâlet.')
        actor = development.authorized_actor(db, item, principal, int(header) if header is not None else None)
        if mutation and not permission(db, item, actor):
            raise HTTPException(403, 'Bu dersin yayın işlemi için sorumlu birim veya kişi yetkiniz yok.')
    return row, actor


def record_event(db, row, actor, action):
    request_event = None
    if action in ('CREATED','PREPARE','PUBLISH') and row.source_request_id:
        from .process import add_process_event
        item = db.get(DevelopmentItem, row.source_development_id)
        flow = db.get(RequestWorkflow, row.source_request_id)
        request_event = add_process_event(db, request_id=row.source_request_id, status=flow.status,
            actor=actor.role, principal=actor, note=f'{policy.EVENTS[action]}: {row.title}, sürüm {row.version_number}.',
            action='PUB_'+action, details={'development_id': item.id, 'development_scope': item.responsible_unit,
                'assignee_id': item.assignee_id, 'publication_id': row.id})
        db.flush()
    db.add(Event(version_id=row.id, revision=row.revision, action=action, actor_id=actor.user_id,
        actor_name=actor.display_name, request_event_id=request_event.id if request_event else None,
        details_json=json_dumps({'delegation': actor.delegation, 'source_review_id': row.source_review_id,
                                'source_ready_id': row.source_ready_id})))


def create(db, item, actor, payload):
    if not permission(db, item, actor):
        raise HTTPException(403, 'Ders taslağını çalışmanın sorumlu eğitim tasarım birimi oluşturabilir.')
    changed = db.execute(update(DevelopmentItem).where(DevelopmentItem.id == item.id,
        DevelopmentItem.version == payload.expected_development_version).values(version=DevelopmentItem.version))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Geliştirme çalışması güncellendi. Güncel kaydı açın.')
    db.refresh(item)
    ready, review, snapshot = source(db, item)
    existing = db.scalar(select(Version).where(Version.source_development_id == item.id))
    if existing:
        return detail(db, existing, actor)
    course = db.get(Course, item.source_course_id) if item.source_course_id else None
    catalog = db.get(Catalog,course.id) if course else None
    if course and not catalog:
        # A PDF imported after migration is a source, not an implicitly published lesson.
        catalog=Catalog(course_id=course.id,responsible_unit=item.responsible_unit)
        db.add(catalog);db.flush()
    if catalog:
        db.execute(update(Catalog).where(Catalog.course_id==course.id).values(revision=Catalog.revision))
    number = (db.scalar(select(func.max(Version.version_number)).where(Version.course_id == course.id)) or 0)+1 if course else 1
    context = json_loads(item.source_context_json, {})
    analysis_id, decision_id = context.get('analysis_run_id'), context.get('decision_id')
    row = Version(course_id=course.id if course else None, version_number=number,
        base_version_id=catalog.current_version_id if catalog else None, proposed_code=course.code if course else '',
        title=snapshot['title'], description=snapshot['summary'], outcomes_json=json_dumps(snapshot['outcomes']),
        outline_json=json_dumps(snapshot['modules']), source_development_id=item.id, source_review_id=review.id,
        source_ready_id=ready.id, source_request_id=item.source_request_id,
        source_analysis_id=analysis_id if analysis_id and db.get(AnalysisRun, analysis_id) else None,
        source_decision_id=decision_id if decision_id and db.get(RequestDecision, decision_id) else None, created_by=actor.user_id)
    db.add(row); db.flush(); record_event(db, row, actor, 'CREATED'); db.commit()
    return detail(db, row, actor)


def validate(db, row):
    item = db.get(DevelopmentItem, row.source_development_id)
    if not item:
        raise HTTPException(422, 'Yayın kaynağı olan geliştirme çalışması bulunamadı.')
    ready, review, snapshot = source(db, item)
    if (row.source_ready_id != ready.id or row.source_review_id != review.id or row.source_request_id != item.source_request_id or
        json_loads(row.outcomes_json, []) != snapshot['outcomes'] or json_loads(row.outline_json, []) != snapshot['modules']):
        raise HTTPException(422, 'Yayın taslağı onaylanan tasarım sürümüyle eşleşmiyor.')
    outlines = snapshot.get('modules', [])
    if not row.title.strip() or not row.description.strip() or not snapshot.get('outcomes') or not outlines or any(not module.get('topics') for module in outlines):
        raise HTTPException(422, 'Ders adı, açıklama, kazanımlar ve konu içeren modüller tamamlanmalıdır.')
    if not row.proposed_code.strip():
        raise HTTPException(422, 'Kurumun belirlediği ders kodunu girin; otomatik kod üretilmez.')
    other = db.scalar(select(Course).where(func.lower(Course.code) == row.proposed_code.casefold()))
    if other and other.id != row.course_id:
        raise HTTPException(422, 'Bu ders kodu başka bir katalog kaydına ait.')
    if row.course_id:
        course = db.get(Course, row.course_id)
        if row.proposed_code != course.code:
            raise HTTPException(422, 'Mevcut dersin kodu korunmalıdır.')
        catalog = db.get(Catalog, row.course_id)
        if not catalog or catalog.current_version_id != row.base_version_id:
            raise HTTPException(409, 'Bu dersin yayınlanmış sürümü değişti. Yeni kapsamı eğitim geliştirme sürecinde yeniden inceleyin.')


def edit(db, row, actor, payload):
    if row.state != 'DRAFT':
        raise HTTPException(422, 'Yalnızca ders taslağının katalog bilgileri düzenlenebilir.')
    lock(db, row, payload.expected_version)
    if row.course_id and payload.code != db.get(Course, row.course_id).code:
        raise HTTPException(422, 'Mevcut ders kodu değiştirilemez.')
    row.title, row.description, row.proposed_code = payload.title, payload.description, payload.code
    db.flush(); record_event(db, row, actor, 'EDIT'); db.commit()
    return detail(db, row, actor)


def action(db, row, actor, payload):
    rule = policy.ACTIONS[payload.action]
    if row.state != rule['source']:
        raise HTTPException(422, 'Bu aşamada seçilen yayın işlemi uygulanamaz.')
    lock(db, row, payload.expected_version)
    if payload.action != 'RETURN_DRAFT':
        validate(db, row)
    if payload.action == 'PUBLISH':
        try:
            if row.course_id is None:
                course = Course(code=row.proposed_code, name=row.title, description=row.description, pdf_path='')
                db.add(course); db.flush(); row.course_id=course.id
                catalog = Catalog(course_id=course.id, responsible_unit=actor.role)
                db.add(catalog); db.flush()
            else:
                catalog = db.get(Catalog, row.course_id)
                previous = db.get(Version, catalog.current_version_id) if catalog.current_version_id else None
                if previous:
                    previous.state, previous.revision, previous.updated_at = 'ARCHIVED', previous.revision+1, utc_now()
                    db.flush(); record_event(db, previous, actor, 'ARCHIVE')
            row.state, row.published_by, row.published_at = 'PUBLISHED', actor.user_id, utc_now()
            db.flush()
            catalog.current_version_id, catalog.responsible_unit = row.id, catalog.responsible_unit or actor.role
            catalog.revision += 1
            db.flush(); record_event(db, row, actor, 'PUBLISH'); db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, 'Ders kodu veya yayın sürümü eşzamanlı işlemde kullanıldı. Güncel kataloğu açın.')
    else:
        row.state = rule['target']; db.flush(); record_event(db, row, actor, payload.action); db.commit()
    return detail(db, row, actor)


def knowledge(db, row):
    document = db.get(Document, row.id)
    index = db.scalar(select(DocumentIndex).where(DocumentIndex.course_id == row.course_id)) if row.course_id else None
    from .indexing import source_path, fingerprint
    ready = bool(document and index and index.status == 'ready' and document.content_hash == index.content_hash)
    if ready:
        path = source_path(document.source_path)
        try:
            ready = path.is_file() and fingerprint(path) == document.content_hash
        except OSError:
            ready = False
    return {'status': 'indexed' if ready else 'source_changed' if document else 'no_document',
        'label': 'PDF indeks kaydıyla eşleşiyor' if ready else 'PDF değişmiş veya indeks hazır değil' if document else 'Bu sürüme PDF bağlanmamış',
        'fingerprint': document.content_hash if document else None,
        'file_name': Path(document.source_path).name if document else None,
        'catalog_published': row.state == 'PUBLISHED'}


def retrieval_allowed(db, course_id, digest):
    catalog = db.get(Catalog, course_id, populate_existing=True)
    if not catalog:
        return True
    doc = db.get(Document, catalog.current_version_id) if catalog.current_version_id else None
    return bool(doc and doc.content_hash == digest)


def link_document(db, row, actor, payload):
    if row.state != 'PUBLISHED' or row.revision != payload.expected_version:
        raise HTTPException(409, 'Yalnızca güncel yayımlanmış sürüme kaynak bağlanabilir.')
    catalog = db.get(Catalog, row.course_id)
    if not catalog or catalog.current_version_id != row.id:
        raise HTTPException(409, 'Kaynak bağlanacak yayın sürümü güncel değil.')
    if db.get(Document, row.id):
        raise HTTPException(422, 'Bu sürümün PDF parmak izi korunur; değişiklik için yeni ders sürümü gerekir.')
    index = db.scalar(select(DocumentIndex).where(DocumentIndex.course_id == row.course_id))
    course = db.get(Course, row.course_id)
    from .indexing import source_path, fingerprint
    if not index or index.status != 'ready' or index.content_hash != payload.content_hash or not source_path(course.pdf_path).is_file() or fingerprint(source_path(course.pdf_path)) != payload.content_hash:
        raise HTTPException(422, 'Bu ders için eşleşen ve indekslenmiş PDF kaynağı bulunamadı.')
    db.add(Document(version_id=row.id, source_path=course.pdf_path, content_hash=payload.content_hash, linked_by=actor.user_id))
    # Attachment has its own immutable record; published metadata/revision stays unchanged.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Bu sürüme başka bir işlemde PDF kaynağı bağlandı.')
    return detail(db, row, actor)


def brief(row):
    return {'id': row.id, 'course_id': row.course_id, 'version_number': row.version_number, 'title': row.title,
        'code': row.proposed_code, 'state': row.state, 'state_label': policy.STATES[row.state], 'revision': row.revision,
        'legacy': row.legacy, 'published_at': utc_stamp(row.published_at)}


def detail(db, row, actor):
    from .training import catalog_action
    item = db.get(DevelopmentItem, row.source_development_id) if row.source_development_id else None
    authorized = bool(item and development.visible(db, item, actor))
    allowed = bool(item and permission(db, item, actor))
    publisher = db.get(PortalUser, row.published_by) if row.published_by else None
    index = db.scalar(select(DocumentIndex).where(DocumentIndex.course_id==row.course_id)) if allowed and row.course_id else None
    candidate = {'file_name': Path(db.get(Course,row.course_id).pdf_path).name, 'content_hash': index.content_hash} if index and index.status=='ready' else None
    from .evaluation import aggregate
    from .skills import mappings,mapping_editable
    return {'skills': mappings(db,row), 'can_edit_skills': mapping_editable(db,row,actor), 'effectiveness': aggregate(db,actor,course_version_id=row.id) if actor.role != 'EMPLOYEE' else None, **brief(row), 'can_plan_training': catalog_action(db,row,actor), 'description': row.description, 'outcomes': json_loads(row.outcomes_json, []),
        'modules': json_loads(row.outline_json, []), 'knowledge': knowledge(db, row),
        'publisher': publisher.display_name if publisher else None, 'created_at': utc_stamp(row.created_at),
        'can_edit': allowed and row.state == 'DRAFT',
        'actions': [dict(code=key, **rule) for key, rule in policy.ACTIONS.items() if allowed and row.state == rule['source']],
        'can_link_document': allowed and row.state == 'PUBLISHED' and not db.get(Document, row.id) and bool(candidate),
        'document_candidate': candidate,
        'trace': {'development_id': item.id, 'request_id': row.source_request_id, 'review_id': row.source_review_id,
                  'ready_id': row.source_ready_id, 'analysis_id': row.source_analysis_id, 'decision_id': row.source_decision_id} if authorized else None,
        'base_version_id': row.base_version_id, 'acting_delegation': actor.delegation,
        'history': [{'label': policy.EVENTS[event.action], 'actor': event.actor_name, 'at': utc_stamp(event.created_at),
                     'delegation': json_loads(event.details_json, {}).get('delegation')}
                    for event in db.scalars(select(Event).where(Event.version_id == row.id).order_by(Event.id))]}


def development_link(db, item, actor):
    row = db.scalar(select(Version).where(Version.source_development_id == item.id))
    return {'version': brief(row) if row else None, 'can_create': not row and item.state == 'READY' and permission(db, item, actor)}


def catalog_list(db, search='', offset=0, limit=20):
    stmt = select(Course, Version, Catalog).join(Catalog, Catalog.course_id == Course.id).join(Version, Version.id == Catalog.current_version_id)
    if search:
        escaped=search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        stmt=stmt.where(or_(Course.code.ilike('%'+escaped+'%',escape='\\'),Version.title.ilike('%'+escaped+'%',escape='\\')))
    return {'items': [{**brief(row), 'course_id': course.id, 'code': course.code, 'knowledge': knowledge(db,row),
            'responsible_unit': policy.DEPARTMENTS.get(catalog.responsible_unit,'Birim bilgisi kayıtlı değil')}
            for course,row,catalog in db.execute(stmt.order_by(Course.code).offset(offset).limit(limit))],
        'total': db.scalar(select(func.count()).select_from(stmt.subquery())), 'offset':offset,'limit':limit}


def course_detail(db, identifier, actor):
    course=db.get(Course,identifier);catalog=db.get(Catalog,identifier)
    if not course or not catalog or not catalog.current_version_id:
        raise HTTPException(404,'Katalog dersi bulunamadı.')
    row=db.get(Version,catalog.current_version_id)
    history=[]
    for value in db.scalars(select(Version).where(Version.course_id==identifier).order_by(Version.version_number.desc())):
        if value.state not in ('PUBLISHED','ARCHIVED'):
            item=db.get(DevelopmentItem,value.source_development_id)
            if not item or not development.visible(db,item,actor):continue
        publisher=db.get(PortalUser,value.published_by) if value.published_by else None
        history.append({**brief(value),'publisher':publisher.display_name if publisher else None})
    return {'course_id':identifier,'code':course.code,'current':detail(db,row,actor),'versions':history}


def compare(a,b):
    """Small ordered comparison; original IDs may differ across development items."""
    from difflib import SequenceMatcher
    def delta(left,right):
        result={'added':[],'removed':[],'changed':[]}
        matcher=SequenceMatcher(a=left,b=right,autojunk=False)
        for tag,i,j,k,l in matcher.get_opcodes():
            if tag=='insert':result['added'].extend(right[k:l])
            elif tag=='delete':result['removed'].extend(left[i:j])
            elif tag=='replace':
                overlap=min(j-i,l-k)
                result['changed'].extend({'before':left[i+n],'after':right[k+n]} for n in range(overlap))
                result['removed'].extend(left[i+overlap:j]);result['added'].extend(right[k+overlap:l])
        return result
    flatten=lambda row: [module['title']+' — '+module.get('description','') for module in json_loads(row.outline_json,[])]
    topics=lambda row:[module['title']+' / '+topic['title']+' — '+topic.get('description','')
        for module in json_loads(row.outline_json,[]) for topic in module.get('topics',[])]
    return {'from':brief(a),'to':brief(b),'metadata':delta([a.title,a.description],[b.title,b.description]),
        'outcomes':delta([x['text'] for x in json_loads(a.outcomes_json,[])],[x['text'] for x in json_loads(b.outcomes_json,[])]),
        'modules':delta(flatten(a),flatten(b)), 'topics':delta(topics(a),topics(b))}


def inbox_items(db, principal, identifiers=None):
    rows=db.scalars(select(Version).where(Version.state.in_(('DRAFT','READY_FOR_PUBLISH'))).where(Version.id.in_(identifiers)) if identifiers is not None else select(Version).where(Version.state.in_(('DRAFT','READY_FOR_PUBLISH'))))
    items=[]
    from .operations import valid_delegation
    for row in rows:
        item=db.get(DevelopmentItem,row.source_development_id)
        if not item or not development.visible(db,item,principal):continue
        actor=principal
        if not permission(db,item,actor):
            delegation=next((value for value in db.scalars(select(Delegation).where(Delegation.delegator_id==item.assignee_id,
                Delegation.delegate_id==principal.user_id)) if valid_delegation(db,value,principal.user_id)),None)
            if not delegation:continue
            actor=development.authorized_actor(db,item,principal,delegation.id)
        if not permission(db,item,actor):continue
        items.append({'kind':'publication','publication_id':row.id,'request_id':item.source_request_id,'topic':row.title,
            'title':row.title,'state':row.state,'state_label':policy.STATES[row.state],'work_type_label':'Ders yayını',
            'action_required':'Ders sürümünü yayınla' if row.state=='READY_FOR_PUBLISH' else 'Ders sürümünü yayınlamaya hazırla',
            'updated_at':utc_stamp(row.updated_at),'responsible_unit_label':policy.DEPARTMENTS[item.responsible_unit],
            'aging':{'current_stage_seconds':max(0,int((utc_now()-row.updated_at).total_seconds()))},'delegation':actor.delegation,
            'assignee':development.summary(db,item)['assignee'],'unread':False,'fit_percent':None})
    return items
