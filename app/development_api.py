from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import update
from .database import get_db
from .portal_auth import current_account
from .models import DevelopmentItem, DevelopmentEvent, RequestWorkflow
from .schemas import DevelopmentCreate, DevelopmentEdit, DevelopmentAction
from .utils import json_loads
from . import development as service

router = APIRouter(prefix='/api/development')


def session(account=Depends(current_account)):
    if not account:
        raise HTTPException(401, 'Devam etmek için giriş yapın.')
    return account


def item_context(db, request, identifier, principal, mutation=False):
    if mutation:
        item = db.get(DevelopmentItem, identifier)
        if item:
            # Serialize authority changes in the source request with design mutations.
            db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == item.source_request_id).values(version=RequestWorkflow.version))
            db.expire_all()
    header = request.headers.get('X-Delegation-ID')
    if header is not None and not header.isdecimal():
        raise HTTPException(403, 'Geçersiz vekâlet.')
    return service.load(db, identifier, principal, int(header) if header is not None else None)


@router.get('')
def queue(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), principal=Depends(session), db=Depends(get_db)):
    return service.queue(db, principal, offset, limit)


@router.post('', status_code=201)
def create(payload: DevelopmentCreate, request: Request, principal=Depends(session), db=Depends(get_db)):
    if request.headers.get('X-Delegation-ID'):
        raise HTTPException(403, 'Yeni geliştirme işini kaynak talebin asıl sorumlusu başlatmalıdır.')
    return service.create(db, principal, payload)


@router.get('/{identifier}')
def detail(identifier: int, request: Request, principal=Depends(session), db=Depends(get_db)):
    item, actor = item_context(db, request, identifier, principal)
    return service.detail(db, item, actor)


@router.patch('/{identifier}')
def edit(identifier: int, payload: DevelopmentEdit, request: Request, principal=Depends(session), db=Depends(get_db)):
    item, actor = item_context(db, request, identifier, principal, mutation=True)
    return service.edit(db, item, actor, payload)


@router.post('/{identifier}/actions')
def action(identifier: int, payload: DevelopmentAction, request: Request, principal=Depends(session), db=Depends(get_db)):
    item, actor = item_context(db, request, identifier, principal, mutation=True)
    return service.act(db, item, actor, payload)


@router.get('/{identifier}/history/{event_id}')
def snapshot(identifier: int, event_id: int, request: Request, principal=Depends(session), db=Depends(get_db)):
    item_context(db, request, identifier, principal)
    event = db.get(DevelopmentEvent, event_id)
    if not event or event.item_id != identifier or event.snapshot_json == '{}':
        raise HTTPException(404, 'Tasarım sürümü bulunamadı.')
    return {'content_revision': event.content_revision, 'snapshot': json_loads(event.snapshot_json, {})}
