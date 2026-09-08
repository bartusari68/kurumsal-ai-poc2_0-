from datetime import date
from fastapi import APIRouter, Depends, Query, Request
from .database import get_db
from .development_api import session
from .training_schemas import SessionCreate, SessionEdit, SessionAction, EnrollmentCreate, EnrollmentRemove, Results
from . import training as service

router = APIRouter(prefix='/api/training')


@router.get('/meta')
def meta(actor=Depends(session)):
    from . import training_policy as policy
    return {'states':policy.STATES,'modes':policy.MODES,'attendance':policy.ATTENDANCE,'completion':policy.COMPLETION}


@router.get('')
def queue(status: str = Query('', pattern='^(|DRAFT|SCHEDULED|IN_PROGRESS|COMPLETED|CANCELLED)$'),
          day: date | None = None, search: str = Query('', max_length=100),
          offset: int = Query(0,ge=0), limit: int = Query(20,ge=1,le=100), actor=Depends(session), db=Depends(get_db)):
    return service.queue(db,actor,status,day,search,offset,limit)


@router.get('/options')
def options(request: Request, course_version_id: int | None = None, session_id: int | None = None,
            actor=Depends(session), db=Depends(get_db)):
    return service.options(db,actor,course_version_id,session_id,request.headers.get('X-Delegation-ID'))


@router.post('',status_code=201)
def create(payload: SessionCreate, actor=Depends(session), db=Depends(get_db)):
    return service.create(db,actor,payload)


@router.get('/{identifier}')
def detail(identifier: int, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'))
    return service.detail(db,row,effective)


def context(db,request,identifier,actor,payload):
    return service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'),payload.expected_version)


@router.patch('/{identifier}')
def edit(identifier: int, payload: SessionEdit, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.edit(db,row,effective,payload)


@router.post('/{identifier}/actions')
def action(identifier: int, payload: SessionAction, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.act(db,row,effective,payload)


@router.post('/{identifier}/enrollments',status_code=201)
def enroll(identifier: int, payload: EnrollmentCreate, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.enroll(db,row,effective,payload)


@router.post('/{identifier}/enrollments/{enrollment_id}/remove')
def remove(identifier: int, enrollment_id: int, payload: EnrollmentRemove, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.remove(db,row,effective,enrollment_id,payload)


@router.post('/{identifier}/attendance')
def attendance(identifier: int, payload: Results, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.results(db,row,effective,payload,'attendance')


@router.post('/{identifier}/completion')
def completion(identifier: int, payload: Results, request: Request, actor=Depends(session), db=Depends(get_db)):
    row,effective=context(db,request,identifier,actor,payload)
    return service.results(db,row,effective,payload,'completion')
