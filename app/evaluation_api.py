from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.orm import Session
from .database import get_db
from .development_api import session
from .evaluation_schemas import EvaluationCreate, EvaluationSubmit
from .models import Enrollment, TrainingSession
from . import evaluation, training, evaluation_policy

router=APIRouter(prefix='/api/evaluations')

@router.get('')
def listing(status:str=Query('',pattern='^(|PENDING|COMPLETED)$'),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db:Session=Depends(get_db)):
    return evaluation.list_evaluations(db,actor,status,offset,limit)

@router.get('/report')
def report(actor=Depends(session),db:Session=Depends(get_db)):
    if actor.role=='EMPLOYEE': raise HTTPException(403,'Rapor için operasyon yetkisi gerekir.')
    return evaluation.aggregate(db,actor)

@router.post('',status_code=201)
def create(payload:EvaluationCreate,request:Request,actor=Depends(session),db:Session=Depends(get_db)):
    entry=db.get(Enrollment,payload.enrollment_id)
    if not entry: raise HTTPException(404,'Katılım bulunamadı.')
    db.execute(update(TrainingSession).where(TrainingSession.id==entry.session_id).values(version=TrainingSession.version))
    row,actor=training.load(db,entry.session_id,actor,request.headers.get('X-Delegation-ID'))
    if not training.can_act(db,row,actor): raise HTTPException(403,'Değerlendirme planlamak için oturum operasyon yetkisi gerekir.')
    value=evaluation.create(db,entry,payload.evaluation_type,actor,source=payload.evaluator_source,
        evaluator_id=payload.evaluator_id,available_at=payload.available_at,due_at=payload.due_at)
    db.commit()
    return evaluation.brief(db,value)

@router.get('/{identifier}')
def detail(identifier:int,actor=Depends(session),db:Session=Depends(get_db)):
    return evaluation.detail(db,evaluation.load(db,identifier,actor),actor)

@router.post('/{identifier}/submit')
def submit(identifier:int,payload:EvaluationSubmit,actor=Depends(session),db:Session=Depends(get_db)):
    return evaluation.submit(db,evaluation.load(db,identifier,actor),actor,payload)
