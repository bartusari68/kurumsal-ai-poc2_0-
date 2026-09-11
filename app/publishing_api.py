from fastapi import APIRouter, Depends, HTTPException, Query, Request
from .database import get_db
from .development_api import session, item_context
from .schemas import PublicationCreate, PublicationEdit, PublicationAction, PublicationDocument
from . import publishing as service
router=APIRouter(prefix='/api/catalog')

@router.get('')
def catalog(search:str=Query('',max_length=100),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    return service.catalog_list(db,search,offset,limit,actor)

@router.get('/courses/{identifier}')
def course(identifier:int,actor=Depends(session),db=Depends(get_db)):
    return service.course_detail(db,identifier,actor)

@router.post('/versions',status_code=201)
def create(payload:PublicationCreate,request:Request,actor=Depends(session),db=Depends(get_db)):
    item,principal=item_context(db,request,payload.development_id,actor,mutation=True)
    return service.create(db,item,principal,payload)

@router.get('/versions/{identifier}')
def version(identifier:int,request:Request,actor=Depends(session),db=Depends(get_db)):
    row,principal=service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'))
    return service.detail(db,row,principal)

@router.patch('/versions/{identifier}')
def edit(identifier:int,payload:PublicationEdit,request:Request,actor=Depends(session),db=Depends(get_db)):
    row,principal=service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'),mutation=True)
    return service.edit(db,row,principal,payload)

@router.post('/versions/{identifier}/actions')
def action(identifier:int,payload:PublicationAction,request:Request,actor=Depends(session),db=Depends(get_db)):
    row,principal=service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'),mutation=True)
    return service.action(db,row,principal,payload)

@router.post('/versions/{identifier}/document')
def document(identifier:int,payload:PublicationDocument,request:Request,actor=Depends(session),db=Depends(get_db)):
    row,principal=service.load(db,identifier,actor,request.headers.get('X-Delegation-ID'),mutation=True)
    return service.link_document(db,row,principal,payload)

@router.get('/versions/{identifier}/compare/{other_id}')
def compare(identifier:int,other_id:int,actor=Depends(session),db=Depends(get_db)):
    left,_=service.load(db,other_id,actor);right,_=service.load(db,identifier,actor)
    if not left.course_id or left.course_id!=right.course_id:
        raise HTTPException(422,'Yalnızca aynı dersin sürümleri karşılaştırılabilir.')
    return service.compare(left,right)
