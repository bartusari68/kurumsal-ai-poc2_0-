"""Authenticated enterprise identity and integration administration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .database import get_db
from .development_api import session
from .portal_auth import current_account, owner_session, require_admin
from .identity_schemas import (
    ConflictResolutionRequest,
    DirectorySyncRequest,
    NotificationPreferenceRequest,
    OIDCSimulationRequest,
    OrganizationUnitCreate,
    OrganizationUnitUpdate,
    PositionMappingRequest,
    RoleMappingRequest,
)
from . import communication, identity
from .identity_models import IntegrationAuditEvent, NotificationPreference
from .time_policy import utc_stamp
from .utils import json_loads
from sqlalchemy import select


router = APIRouter(prefix="/api/integrations")
auth_router = APIRouter(prefix="/api/auth")
communications_router = APIRouter(prefix="/api/communications")


@router.get("")
def integrations_dashboard(actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.provider_status(db) | {"communication": communication.delivery_status(db, limit=20)}


@router.get("/providers")
def providers(actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.provider_status(db)


@router.get("/health")
def integrations_health(actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.provider_status(db)


@router.get("/sync-runs")
def sync_runs(limit: int = Query(20, ge=1, le=100), actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.list_sync_runs(db, limit)}


@router.post("/directory/sync")
def directory_sync(payload: DirectorySyncRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    records = [item.model_dump() for item in payload.records] if payload.records is not None else None
    # An explicit apply flag is required.  Omitting it always remains a dry
    # run, even if a caller sends dry_run=false by mistake.
    return identity.sync_directory(db, records, provider=payload.provider, dry_run=payload.dry_run,
                                   apply=payload.apply, actor=actor)


@router.post("/sync")
def directory_sync_alias(payload: DirectorySyncRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return directory_sync(payload, actor, db)


@router.get("/conflicts")
def conflicts(status: str = Query("OPEN", max_length=16), limit: int = Query(100, ge=1, le=500),
              actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.list_conflicts(db, status, limit), "status": status}


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, payload: ConflictResolutionRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.resolve_conflict(db, actor, conflict_id, payload.resolution)


@router.get("/organization/tree")
def organization_tree(include_inactive: bool = False, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.organization_tree(db, include_inactive=include_inactive)}


@router.post("/organization/units", status_code=201)
def create_organization_unit(payload: OrganizationUnitCreate, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.create_organization_unit(db, actor, name=payload.name, external_id=payload.external_id,
                                              parent_id=payload.parent_id, source=payload.source)


@router.patch("/organization/units/{unit_id}")
def update_organization_unit(unit_id: int, payload: OrganizationUnitUpdate, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.update_organization_unit(db, actor, unit_id, **payload.model_dump(exclude_unset=True))


@router.get("/users/{user_id}/identity")
def user_identity(user_id: int, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.identity_detail(db, actor, user_id)


@router.get("/users")
def identity_users(search: str = Query("", max_length=160), limit: int = Query(100, ge=1, le=500),
                   actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.identity_users(db, search, limit)}


@router.get("/identity/users/{user_id}")
def user_identity_alias(user_id: int, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.identity_detail(db, actor, user_id)


@router.get("/role-mappings")
def role_mappings(provider: str | None = Query(None, max_length=80), actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.role_mappings(db, provider)}


@router.post("/role-mappings", status_code=201)
def add_role_mapping(payload: RoleMappingRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.add_role_mapping(db, actor, payload.provider, payload.external_key,
                                     payload.application_role, payload.enabled)


@router.get("/position-mappings")
def position_mappings(provider: str | None = Query(None, max_length=80), actor=Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": identity.position_mappings(db, provider)}


@router.post("/position-mappings", status_code=201)
def add_position_mapping(payload: PositionMappingRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return identity.add_position_mapping(db, actor, payload.provider, payload.external_position_key,
                                         payload.position_profile_id)


@router.get("/deliveries")
def deliveries(limit: int = Query(50, ge=1, le=200), actor=Depends(require_admin), db: Session = Depends(get_db)):
    return communication.delivery_status(db, limit)


@router.get("/audit")
def integration_audit(limit: int = Query(100, ge=1, le=500), actor=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(IntegrationAuditEvent).order_by(IntegrationAuditEvent.id.desc()).limit(limit))
    return {"items": [{"id": row.id, "action": row.action, "provider": row.provider, "user_id": row.user_id,
                        "sync_run_id": row.sync_run_id, "actor_id": row.actor_id,
                        "details": json_loads(row.details_json, {}), "created_at": utc_stamp(row.created_at)} for row in rows]}


@router.get("/oidc/start")
def oidc_start():
    # This endpoint is intentionally unauthenticated: it is the optional
    # second action on the login screen.  It returns 404 while unconfigured,
    # so a non-working SSO button can never be rendered.
    return identity.oidc_authorization()


@router.get("/oidc/callback")
def oidc_callback(state: str = Query(""), nonce: str = Query(""), code: str = Query("")):
    if not identity.oidc_state_store.consume(state, nonce):
        raise HTTPException(400, "SSO state veya nonce doğrulanamadı.")
    if not code.strip():
        raise HTTPException(400, "SSO authorization code bulunamadı.")
    # Token exchange is provider-specific and deliberately not faked in the
    # local POC.  A configured connector can call resolve_oidc_identity after
    # validating issuer, audience and expiry server-side.
    raise HTTPException(501, "SSO token doğrulama adaptörü bu ortamda uygulanmadı.")


@auth_router.get("/oidc/start")
def auth_oidc_start():
    return identity.oidc_authorization()


@auth_router.get("/oidc/callback")
def auth_oidc_callback(state: str = Query(""), nonce: str = Query(""), code: str = Query("")):
    return oidc_callback(state=state, nonce=nonce, code=code)


@router.post("/oidc/simulate")
def oidc_simulate(payload: OIDCSimulationRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    if not identity.settings.oidc_configured:
        raise HTTPException(404, "SSO sağlayıcısı yapılandırılmadı.")
    user = identity.resolve_oidc_identity(db, subject=payload.subject, claims=payload.claims, provider=payload.provider)
    return identity.identity_detail(db, actor, user.id)


@router.get("/preferences")
def preferences(actor=Depends(owner_session), db: Session = Depends(get_db)):
    return communication.preference_payload(db.get(NotificationPreference, actor.user_id), actor.user_id)


@router.patch("/preferences")
def update_preferences(payload: NotificationPreferenceRequest, actor=Depends(owner_session), db: Session = Depends(get_db)):
    return communication.update_preferences(db, actor.user_id, payload.model_dump(exclude_unset=True))


@communications_router.get("/status")
def communications_status(actor=Depends(require_admin), db: Session = Depends(get_db)):
    return communication.delivery_status(db)


@communications_router.get("/preferences")
def communications_preferences(actor=Depends(owner_session), db: Session = Depends(get_db)):
    return communication.preference_payload(db.get(NotificationPreference, actor.user_id), actor.user_id)


@communications_router.patch("/preferences")
def communications_update_preferences(payload: NotificationPreferenceRequest, actor=Depends(owner_session), db: Session = Depends(get_db)):
    return communication.update_preferences(db, actor.user_id, payload.model_dump(exclude_unset=True))
