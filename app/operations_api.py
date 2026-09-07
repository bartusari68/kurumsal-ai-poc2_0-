"""Authenticated operations routes; the event worker remains independently callable."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .database import get_db
from .portal_auth import owner_session
from .models import Delegation, Notification
from .schemas import DelegationRequest
from . import operations

router = APIRouter(prefix='/api/operations')


@router.get('/notifications/count')
def count_notifications(session=Depends(owner_session), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(Notification).where(Notification.recipient_id == session.user_id, Notification.read_at.is_(None)))
    return {'unread_count': count}


@router.get('/notifications')
def list_notifications(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.notifications(db, session, offset, limit)


@router.post('/notifications/read-all')
def read_all(session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.read_notification(db, session)


@router.post('/notifications/{notification_id}/read')
def read_one(notification_id: int, session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.read_notification(db, session, notification_id)


@router.get('/inbox')
def action_inbox(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.inbox(db, session, offset, limit)


@router.get('/delegations')
def delegations(session=Depends(owner_session), db: Session = Depends(get_db)):
    rows = db.scalars(select(Delegation).where(or_(Delegation.delegator_id == session.user_id,
        Delegation.delegate_id == session.user_id)).order_by(Delegation.id.desc()).limit(100))
    return {'items': [operations.delegation_payload(db, row) for row in rows],
        'options': operations.delegation_options(db, session), 'current_user_id': session.user_id}


@router.post('/delegations', status_code=201)
def add_delegation(payload: DelegationRequest, session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.create_delegation(db, session, payload)


@router.post('/delegations/{delegation_id}/revoke')
def revoke_delegation(delegation_id: int, session=Depends(owner_session), db: Session = Depends(get_db)):
    return operations.revoke_delegation(db, session, delegation_id)
