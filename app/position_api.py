from fastapi import APIRouter, Depends, Query
from .database import get_db
from .development_api import session
from .position_schemas import PositionWrite, PositionAssignment
from . import positions, position_gap

router = APIRouter(prefix='/api/positions')

@router.get('/mine')
def mine(actor=Depends(session), db=Depends(get_db)):
    return position_gap.mine(db, actor)

@router.get('/planning')
def planning(search: str = Query('', max_length=160), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor=Depends(session), db=Depends(get_db)):
    return position_gap.planning(db, actor, search, offset, limit)

@router.get('/users')
def users(search: str = Query('', max_length=160), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor=Depends(session), db=Depends(get_db)):
    return positions.users(db, actor, search, offset, limit)

@router.put('/users/{user_id}')
def assign(user_id: int, payload: PositionAssignment, actor=Depends(session), db=Depends(get_db)):
    return positions.assign(db, actor, user_id, payload)

@router.get('')
def catalog(search: str = Query('', max_length=160), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor=Depends(session), db=Depends(get_db)):
    return positions.catalog(db, actor, search, offset, limit)

@router.post('', status_code=201)
def create(payload: PositionWrite, actor=Depends(session), db=Depends(get_db)):
    return positions.write(db, actor, payload)

@router.get('/{profile_id}/aggregate')
def aggregate(profile_id: int, actor=Depends(session), db=Depends(get_db)):
    return position_gap.aggregate(db, actor, profile_id)

@router.get('/{profile_id}')
def detail(profile_id: int, version: int | None = Query(None, ge=1), actor=Depends(session), db=Depends(get_db)):
    return positions.detail(db, actor, profile_id, version)

@router.put('/{profile_id}')
def edit(profile_id: int, payload: PositionWrite, actor=Depends(session), db=Depends(get_db)):
    return positions.write(db, actor, payload, profile_id)
