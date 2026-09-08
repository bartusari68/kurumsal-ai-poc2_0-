from fastapi import APIRouter,Depends,Query,Request,HTTPException
from sqlalchemy import select
from .database import get_db
from .development_api import session
from .skill_schemas import SkillWrite,CourseSkillWrite,NeedCreate,NeedAction
from .skill_models import SkillGroup,RequestSkillNeed
from . import skills,skill_evidence,skill_reporting,publishing

router=APIRouter(prefix='/api/skills')

@router.get('/mine')
def mine(offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    return skill_evidence.profile(db,actor,offset=offset,limit=limit)

@router.get('/mine/{skill_id}')
def mine_skill(skill_id:int,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    profile=skill_evidence.profile(db,actor,skill_id=skill_id)
    if not profile['items']:raise HTTPException(404,'Kendi hesabınızda bu yetkinliğe ait kanıt bulunamadı.')
    return {**profile['items'][0],'evidence':skill_evidence.own_evidence(db,actor,skill_id,offset,limit),'meaning':profile['meaning']}

@router.get('/options')
def options(search:str=Query('',max_length=160),actor=Depends(session),db=Depends(get_db)):
    skills.require_manager(actor)
    return {'items':skills.options(db,search),'groups':[{'id':g.id,'name':g.name} for g in db.scalars(select(SkillGroup).order_by(SkillGroup.id))],'can_manage':actor.role=='NEEDS_ANALYST'}

@router.get('')
def catalog(search:str=Query('',max_length=160),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    return skill_reporting.catalog(db,actor,search,offset,limit)

@router.post('',status_code=201)
def create(payload:SkillWrite,actor=Depends(session),db=Depends(get_db)):
    return skills.write_skill(db,actor,payload)

@router.get('/requests/{request_id}')
def request_skills(request_id:int,actor=Depends(session),db=Depends(get_db)):
    record,flow=skills.request_context(db,request_id,actor)
    return skills.request_section(db,record,flow,actor.role)

@router.post('/requests/{request_id}',status_code=201)
def need_add(request_id:int,payload:NeedCreate,actor=Depends(session),db=Depends(get_db)):
    record,flow=skills.request_context(db,request_id,actor,True)
    return skills.add_need(db,record,flow,actor,payload)

@router.post('/requests/{request_id}/{need_id}')
def need_action(request_id:int,need_id:int,payload:NeedAction,actor=Depends(session),db=Depends(get_db)):
    record,flow=skills.request_context(db,request_id,actor,True)
    return skills.change_need(db,record,flow,actor,db.get(RequestSkillNeed,need_id),payload)

@router.put('/versions/{version_id}')
def mapping(version_id:int,payload:CourseSkillWrite,request:Request,actor=Depends(session),db=Depends(get_db)):
    version,actor=publishing.load(db,version_id,actor,request.headers.get('X-Delegation-ID'),mutation=True)
    return skills.save_mappings(db,version,actor,payload)

@router.get('/{skill_id}')
def detail(skill_id:int,actor=Depends(session),db=Depends(get_db)):
    return skill_reporting.detail(db,actor,skill_id)

@router.patch('/{skill_id}')
def edit(skill_id:int,payload:SkillWrite,actor=Depends(session),db=Depends(get_db)):
    return skills.write_skill(db,actor,payload,skill_id)
