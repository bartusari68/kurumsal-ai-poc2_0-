from fastapi import APIRouter,Depends,Query,HTTPException
from .database import get_db
from .development_api import session
from .portfolio_schemas import ItemCreate,ItemAction,HandoffCreate
from . import portfolio as service,portfolio_query as reports,portfolio_policy as policy

router=APIRouter(prefix='/api/portfolio')

@router.get('')
def overview(signal:str=Query('',max_length=40),group_id:int|None=Query(None,gt=0),
             coverage:str=Query('',pattern='^(|PRESENT|MISSING)$'),open_only:bool=False,
             sort:str=Query('activity',pattern='^(activity|planned|observed|open|name)$'),
             offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    if signal and signal not in policy.SIGNALS:raise HTTPException(422,'Geçersiz sinyal türü.')
    return reports.overview(db,actor,signal,group_id,coverage,open_only,sort,offset,limit)

@router.get('/options')
def options(search:str=Query('',max_length=160),actor=Depends(session),db=Depends(get_db)):
    return service.options(db,actor,search)

@router.get('/skills/{skill_id}')
def skill(skill_id:int,actor=Depends(session),db=Depends(get_db)):
    return {**reports.skill(db,actor,skill_id),'portfolio_items':service.items(db,actor,skill_id)['items']}

@router.get('/items')
def items(skill_id:int|None=Query(None,gt=0),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),actor=Depends(session),db=Depends(get_db)):
    return service.items(db,actor,skill_id,offset,limit)

@router.post('/items',status_code=201)
def create(payload:ItemCreate,actor=Depends(session),db=Depends(get_db)):
    return service.create(db,actor,payload)

@router.get('/items/{identifier}')
def detail(identifier:int,actor=Depends(session),db=Depends(get_db)):
    return service.detail(db,actor,identifier)

@router.post('/items/{identifier}/actions')
def action(identifier:int,payload:ItemAction,actor=Depends(session),db=Depends(get_db)):
    return service.act(db,actor,identifier,payload)

@router.post('/items/{identifier}/handoffs',status_code=201)
def handoff(identifier:int,payload:HandoffCreate,actor=Depends(session),db=Depends(get_db)):
    return service.issue(db,actor,identifier,payload)

@router.get('/items/{identifier}/targets')
def targets(identifier:int,actor=Depends(session),db=Depends(get_db)):
    return service.targets(db,actor,identifier)

@router.get('/handoffs')
def handoffs(actor=Depends(session),db=Depends(get_db)):
    return {'items':service.handoffs(db,actor)}

@router.get('/handoffs/{identifier}')
def handoff_detail(identifier:int,actor=Depends(session),db=Depends(get_db)):
    from .portfolio_models import PortfolioHandoff
    h=db.get(PortfolioHandoff,identifier)
    if not h or h.recipient_id!=actor.user_id:raise HTTPException(404,'Planlama geçişi bulunamadı.')
    # Recheck current source authority when the recipient opens the actual flow.
    if h.kind!='REQUEST':
        item=db.get(service.Item,h.item_id);user=db.get(service.PortalUser,actor.user_id)
        service.target_context(db,item,user,h.target_key)
    return service.handoff_data(db,h,actor)
