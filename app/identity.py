"""Identity, directory-sync and organisation integration services.

This module intentionally contains only provider-neutral boundaries.  A real
LDAP/OIDC/Entra connector is selected by configuration; with the default local
configuration no network call is made and the local named-account login stays
available.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable, Protocol
from urllib.parse import urlencode, urlparse

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .identity_models import (
    APPLICATION_ROLES,
    CONFLICT_STATUSES,
    ExternalIdentityLink,
    ExternalPositionMapping,
    ExternalRoleMapping,
    Identity,
    IdentityConflict,
    IntegrationAuditEvent,
    OrganizationMembership,
    OrganizationUnit,
    SyncRun,
    UserManagerRelation,
)
from .models import AccountSession, PortalUser, UserOrganization
from .portal_auth import password_digest
from .time_policy import as_utc, utc_now, utc_stamp
from .utils import json_dumps, json_loads


class ProviderNotConfigured(RuntimeError):
    """Raised when a disabled provider would otherwise make an external call."""


class IdentityProvider(Protocol):
    name: str

    def configured(self) -> bool: ...

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]: ...

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def resolve_profile(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def sync_membership(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class DirectoryProvider(IdentityProvider, Protocol):
    def users(self) -> Iterable["DirectoryUser"]: ...


@dataclass(frozen=True)
class DirectoryUser:
    """Canonical directory record independent of a vendor's attribute names."""

    external_subject_id: str
    username: str
    display_name: str
    email: str = ""
    active: bool = True
    organization: str | None = None
    unit: str | None = None
    organization_external_id: str | None = None
    organization_parent_external_id: str | None = None
    organization_name: str | None = None
    manager_external_id: str | None = None
    position_key: str | None = None
    groups: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: "DirectoryUser | dict[str, Any]") -> "DirectoryUser":
        if isinstance(value, cls):
            return value
        data = dict(value)
        try:
            configured_map = json.loads(settings.directory_attribute_map_json or "{}")
            if isinstance(configured_map, dict):
                for canonical, source in configured_map.items():
                    if canonical not in data and isinstance(source, str) and source in data:
                        data[canonical] = data[source]
        except (TypeError, ValueError, json.JSONDecodeError):
            # A malformed optional mapping cannot make the local POC crash;
            # canonical field names and documented aliases remain available.
            pass
        subject = data.get("external_subject_id") or data.get("external_id") or data.get("employee_id") or data.get("id")
        username = data.get("username") or data.get("user_name") or data.get("account_name") or ""
        display_name = data.get("display_name") or data.get("name") or username
        if not subject or not username or not display_name:
            raise ValueError("Dizin kaydında external subject, kullanıcı adı ve görünen ad zorunludur.")
        groups = data.get("groups") or data.get("claims") or ()
        if isinstance(groups, str):
            groups = tuple(item.strip() for item in groups.split(",") if item.strip())
        else:
            groups = tuple(str(item).strip() for item in groups if str(item).strip())
        reserved = {
            "external_subject_id", "external_id", "employee_id", "id", "username", "user_name", "account_name",
            "display_name", "name", "email", "active", "organization", "unit", "organization_external_id",
            "organization_parent_external_id", "organization_name", "manager_external_id", "manager_id",
            "position_key", "job_code", "groups", "claims", "metadata",
        }
        active_value = data.get("active", True)
        if isinstance(active_value, str):
            active_value = active_value.strip().lower() not in {"0", "false", "no", "off", "inactive", "disabled"}
        return cls(
            external_subject_id=str(subject).strip(),
            username=str(username).strip().lower(),
            display_name=str(display_name).strip(),
            email=str(data.get("email") or "").strip().lower(),
            active=bool(active_value),
            organization=(str(data["organization"]).strip() if data.get("organization") else None),
            unit=(str(data["unit"]).strip() if data.get("unit") else None),
            organization_external_id=(str(data["organization_external_id"]).strip() if data.get("organization_external_id") else None),
            organization_parent_external_id=(str(data["organization_parent_external_id"]).strip() if data.get("organization_parent_external_id") else None),
            organization_name=(str(data["organization_name"]).strip() if data.get("organization_name") else None),
            manager_external_id=(str(data.get("manager_external_id") or data.get("manager_id") or "").strip() or None),
            position_key=(str(data["position_key"] or data["job_code"]).strip() if data.get("position_key") or data.get("job_code") else None),
            groups=groups,
            metadata=dict(data.get("metadata") or {key: value for key, value in data.items() if key not in reserved}),
        )


class DisabledDirectoryProvider:
    name = "directory"

    def configured(self) -> bool:
        return False

    def users(self) -> Iterable[DirectoryUser]:
        raise ProviderNotConfigured("Directory sağlayıcısı yapılandırılmadı.")

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        raise ProviderNotConfigured("Directory sağlayıcısı yapılandırılmadı.")

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ProviderNotConfigured("Directory sağlayıcısı yapılandırılmadı.")

    def resolve_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ProviderNotConfigured("Directory sağlayıcısı yapılandırılmadı.")

    def sync_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ProviderNotConfigured("Directory sağlayıcısı yapılandırılmadı.")


class ConfiguredDirectoryProvider:
    """Boundary for a future LDAP/AD connector; it never guesses a schema."""

    name = settings.directory_provider or "directory"

    def configured(self) -> bool:
        return settings.directory_configured

    def users(self) -> Iterable[DirectoryUser]:
        # A concrete LDAP implementation must be deliberately supplied.  This
        # prevents a local POC from making an unexpected network call merely
        # because an incomplete environment variable exists.
        raise ProviderNotConfigured("Directory bağlantı adaptörü bu ortamda etkin değil.")

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        raise ProviderNotConfigured("Directory bağlantı adaptörü bu ortamda etkin değil.")

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"external_subject_id": payload.get("external_subject_id") or payload.get("external_id"),
                "username": payload.get("username"), "email": payload.get("email")}

    def resolve_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"position_key": payload.get("position_key") or payload.get("job_code"),
                "organization": payload.get("organization"), "unit": payload.get("unit")}

    def sync_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"organization": payload.get("organization"), "unit": payload.get("unit"),
                "manager_external_id": payload.get("manager_external_id")}


class FakeDirectoryProvider:
    """Small in-memory provider for tests and development-only dry runs."""

    name = "fake"

    def __init__(self, records: Iterable[DirectoryUser | dict[str, Any]] = ()):
        self.records = tuple(DirectoryUser.from_mapping(item) for item in records)

    def configured(self) -> bool:
        return True

    def users(self) -> Iterable[DirectoryUser]:
        return self.records

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return self.resolve_identity(credentials)

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = DirectoryUser.from_mapping(payload)
        return {"external_subject_id": record.external_subject_id, "username": record.username,
                "display_name": record.display_name, "email": record.email}

    def resolve_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = DirectoryUser.from_mapping(payload)
        return {"position_key": record.position_key, "organization": record.organization, "unit": record.unit}

    def sync_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = DirectoryUser.from_mapping(payload)
        return {"organization": record.organization, "unit": record.unit,
                "manager_external_id": record.manager_external_id}


def directory_provider(records: Iterable[DirectoryUser | dict[str, Any]] | None = None) -> DirectoryProvider:
    if records is not None:
        return FakeDirectoryProvider(records)
    if settings.directory_configured:
        return ConfiguredDirectoryProvider()
    return DisabledDirectoryProvider()


def _safe_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    # Provider metadata is informational only; never retain values that look
    # like secrets or bearer tokens.
    blocked = ("secret", "token", "password", "access_key", "private_key", "nonce")
    def clean(item):
        if isinstance(item, dict):
            return {str(key): clean(child) for key, child in item.items()
                    if not any(part in str(key).lower() for part in blocked)}
        if isinstance(item, list):
            return [clean(child) for child in item]
        return item
    return clean(value)


def provider_status(db: Session) -> dict[str, Any]:
    """Return a UI-safe integration health summary with no credential values."""

    last_sync = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
    conflicts = db.scalar(select(func.count()).select_from(IdentityConflict).where(IdentityConflict.status == "OPEN")) or 0
    providers = [
        {"id": "local", "label": "Yerel hesap", "kind": "LOCAL", "enabled": bool(settings.local_login_enabled), "configured": True, "status": "active" if settings.local_login_enabled else "disabled"},
        {"id": "directory", "label": "Dizin / LDAP", "kind": "DIRECTORY", "enabled": bool(settings.directory_configured), "configured": bool(settings.directory_configured), "status": "configured" if settings.directory_configured else "not_configured"},
        {"id": "oidc", "label": "OIDC / SSO", "kind": "SSO", "enabled": bool(settings.oidc_configured), "configured": bool(settings.oidc_configured), "status": "configured" if settings.oidc_configured else "not_configured"},
        {"id": "email", "label": "E-posta", "kind": "EMAIL", "enabled": bool(settings.email_configured), "configured": bool(settings.email_configured), "status": "configured" if settings.email_configured else "not_configured"},
        {"id": "teams", "label": "Microsoft Teams", "kind": "TEAMS", "enabled": bool(settings.teams_configured), "configured": bool(settings.teams_configured), "status": "configured" if settings.teams_configured else "not_configured"},
    ]
    last_by_provider = {}
    for row in db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(100)):
        last_by_provider.setdefault(row.provider, sync_run_payload(row))
    for item in providers:
        aliases = {item["id"]}
        if item["id"] == "directory" and settings.directory_provider:
            aliases.add(settings.directory_provider)
        if item["id"] == "oidc" and settings.oidc_provider:
            aliases.add(settings.oidc_provider)
        item["last_sync"] = next((last_by_provider.get(alias) for alias in aliases if last_by_provider.get(alias)), None)
        item["last_result"] = (item["last_sync"] or {}).get("status") if item["last_sync"] else None
    return {
        "providers": providers,
        "last_sync": sync_run_payload(last_sync) if last_sync else None,
        "pending_conflicts": conflicts,
        "local_login_enabled": bool(settings.local_login_enabled),
    }


def sync_run_payload(row: SyncRun | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.id,
        "provider": row.provider,
        "started_at": utc_stamp(row.started_at),
        "completed_at": utc_stamp(row.completed_at),
        "status": row.status,
        "users_seen": row.users_seen,
        "created": row.created,
        "updated": row.updated,
        "deactivated": row.deactivated,
        "organization_changes": row.organization_changes,
        "errors": json_loads(row.errors_json, []),
        "triggered_by": row.triggered_by,
        "dry_run": bool(row.dry_run),
    }


def _audit(db: Session, action: str, *, provider: str | None = None, user_id: int | None = None,
           sync_run_id: int | None = None, actor_id: int | None = None, **details: Any) -> None:
    db.add(IntegrationAuditEvent(action=action, provider=provider, user_id=user_id,
                                 sync_run_id=sync_run_id, actor_id=actor_id,
                                 details_json=json_dumps(_safe_json(details))))


def _find_identity(db: Session, user_id: int, identity_type: str, provider: str) -> Identity | None:
    return db.scalar(select(Identity).where(Identity.user_id == user_id,
                                             Identity.identity_type == identity_type,
                                             Identity.provider == provider))


def ensure_local_identity(db: Session, user: PortalUser) -> Identity:
    row = _find_identity(db, user.id, "LOCAL", "local")
    if row:
        if row.status != "ACTIVE":
            row.status = "ACTIVE"
        return row
    row = Identity(user_id=user.id, identity_type="LOCAL", provider="local", status="ACTIVE")
    db.add(row)
    db.flush()
    return row


def ensure_external_identity(db: Session, user: PortalUser, provider: str, *, metadata: dict[str, Any] | None = None) -> Identity:
    row = _find_identity(db, user.id, "DIRECTORY", provider)
    if row:
        if row.status != "ACTIVE":
            row.status = "ACTIVE"
        return row
    row = Identity(user_id=user.id, identity_type="DIRECTORY", provider=provider,
                   status="ACTIVE", metadata_json=json_dumps(_safe_json(metadata or {})))
    db.add(row)
    db.flush()
    return row


def authentication_allowed(db: Session, user: PortalUser) -> bool:
    """Keep local fallback alive while denying fully deactivated externals."""

    if not user or not user.active or not settings.local_login_enabled and not db.scalar(
        select(Identity.id).where(Identity.user_id == user.id, Identity.identity_type == "LOCAL", Identity.status == "ACTIVE")
    ):
        return False
    rows = list(db.scalars(select(Identity).where(Identity.user_id == user.id, Identity.status == "ACTIVE")))
    if not rows:
        # Legacy rows created before the additive identity table remain usable.
        return True
    return any(row.identity_type == "LOCAL" and settings.local_login_enabled for row in rows) or any(
        row.identity_type in {"DIRECTORY", "SSO"} for row in rows
    )


def _walk_parent(db: Session, child_id: int, parent_id: int | None) -> None:
    if parent_id is None:
        return
    if child_id == parent_id:
        raise HTTPException(422, "Organizasyon ağacında döngü oluşturulamaz.")
    seen: set[int] = set()
    current = parent_id
    while current is not None:
        if current in seen or current == child_id:
            raise HTTPException(422, "Organizasyon ağacında döngü oluşturulamaz.")
        seen.add(current)
        node = db.get(OrganizationUnit, current)
        if not node:
            raise HTTPException(404, "Üst organizasyon birimi bulunamadı.")
        current = node.parent_id


def ensure_organization_unit(db: Session, *, name: str, external_id: str | None = None,
                             parent_external_id: str | None = None, source: str = "DIRECTORY") -> OrganizationUnit:
    name = (name or "").strip()
    if not name:
        raise ValueError("Organizasyon birimi adı boş olamaz.")
    row = db.scalar(select(OrganizationUnit).where(OrganizationUnit.external_id == external_id)) if external_id else None
    if row is None and external_id is None:
        row = db.scalar(select(OrganizationUnit).where(OrganizationUnit.name == name, OrganizationUnit.source == source))
    parent = None
    if parent_external_id:
        parent = db.scalar(select(OrganizationUnit).where(OrganizationUnit.external_id == parent_external_id))
        if not parent:
            # Parent may be encountered later; caller retries after all units
            # have been created rather than inventing a placeholder node.
            parent = None
    if row is None:
        row = OrganizationUnit(name=name, external_id=external_id, parent_id=parent.id if parent else None,
                               source=source, status="ACTIVE")
        db.add(row)
        db.flush()
    else:
        if parent and row.parent_id != parent.id:
            _walk_parent(db, row.id, parent.id)
            row.parent_id = parent.id
        if row.name != name:
            row.name = name
        row.status = "ACTIVE"
        row.source = source
    return row


def organization_tree(db: Session, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    query = select(OrganizationUnit)
    if not include_inactive:
        query = query.where(OrganizationUnit.status == "ACTIVE")
    rows = db.scalars(query.order_by(OrganizationUnit.name, OrganizationUnit.id)).all()
    return [{"id": row.id, "external_id": row.external_id, "name": row.name, "parent_id": row.parent_id,
             "status": row.status, "source": row.source, "updated_at": utc_stamp(row.updated_at)} for row in rows]


def backfill_legacy_organizations(db: Session) -> int:
    """Create canonical snapshots for pre-Phase-15 nullable HR metadata.

    The migration is additive and idempotent: the legacy ``UserOrganization``
    row remains the compatibility surface, while a current canonical unit and
    (when present) manager relation are created only when one does not already
    exist.  No request, decision, or audit history is rewritten.
    """

    changed = 0
    for legacy in db.scalars(select(UserOrganization)):
        current = _current_membership(db, legacy.user_id)
        unit_name = (legacy.unit or legacy.organization or legacy.directorate or legacy.chiefdom or "").strip()
        if not current and unit_name:
            source = (legacy.source or "LOCAL").strip().upper()
            parent = None
            if legacy.unit and legacy.organization and legacy.unit.strip() != legacy.organization.strip():
                parent = ensure_organization_unit(db, name=legacy.organization, source=source)
            unit = ensure_organization_unit(db, name=unit_name, source=source)
            if parent and unit.parent_id != parent.id:
                _walk_parent(db, unit.id, parent.id)
                unit.parent_id = parent.id
            db.add(OrganizationMembership(
                user_id=legacy.user_id,
                organization_unit_id=unit.id,
                valid_from=as_utc(legacy.updated_at) or utc_now(),
                source=source,
                is_current=True,
            ))
            changed += 1
        if legacy.manager_user_id and legacy.manager_user_id != legacy.user_id:
            relation = db.scalar(select(UserManagerRelation).where(
                UserManagerRelation.user_id == legacy.user_id,
                UserManagerRelation.is_current.is_(True)))
            if relation is None and db.get(PortalUser, legacy.manager_user_id):
                db.add(UserManagerRelation(
                    user_id=legacy.user_id,
                    manager_user_id=legacy.manager_user_id,
                    valid_from=as_utc(legacy.updated_at) or utc_now(),
                    source=(legacy.source or "LOCAL").strip().upper(),
                    is_current=True,
                ))
                changed += 1
    if changed:
        db.commit()
    return changed


def create_organization_unit(db: Session, actor: Any, *, name: str, external_id: str | None = None,
                             parent_id: int | None = None, source: str = "LOCAL") -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise HTTPException(422, "Organizasyon birimi adı boş olamaz.")
    if external_id and db.scalar(select(OrganizationUnit.id).where(OrganizationUnit.external_id == external_id)):
        raise HTTPException(409, "Bu dış organizasyon kimliği zaten kayıtlı.")
    _walk_parent(db, 0, parent_id) if parent_id else None
    row = OrganizationUnit(name=name, external_id=external_id, parent_id=parent_id,
                           source=(source or "LOCAL").strip().upper(), status="ACTIVE")
    db.add(row)
    db.commit()
    return {"id": row.id, "external_id": row.external_id, "name": row.name, "parent_id": row.parent_id,
            "status": row.status, "source": row.source}


_UNSET = object()


def update_organization_unit(db: Session, actor: Any, unit_id: int, *, name: str | None = None,
                             parent_id: int | None | object = _UNSET, status: str | None = None) -> dict[str, Any]:
    row = db.get(OrganizationUnit, unit_id)
    if not row:
        raise HTTPException(404, "Organizasyon birimi bulunamadı.")
    # ``None`` is a meaningful explicit value here: it moves a unit to the
    # root.  The sentinel keeps an omitted PATCH field unchanged.
    if parent_id is not _UNSET:
        if parent_id is not None:
            _walk_parent(db, unit_id, parent_id)
        row.parent_id = parent_id
    if name is not None:
        if not name.strip():
            raise HTTPException(422, "Organizasyon birimi adı boş olamaz.")
        row.name = name.strip()
    if status is not None:
        status = status.strip().upper()
        if status not in {"ACTIVE", "INACTIVE"}:
            raise HTTPException(422, "Geçersiz organizasyon birimi durumu.")
        row.status = status
    row.updated_at = utc_now()
    db.commit()
    return {"id": row.id, "external_id": row.external_id, "name": row.name, "parent_id": row.parent_id,
            "status": row.status, "source": row.source}


def _role_for_groups(db: Session, provider: str, groups: Iterable[str]) -> tuple[str, str | None]:
    for group in groups:
        key = str(group).strip()
        mapping = db.scalar(select(ExternalRoleMapping).where(ExternalRoleMapping.provider == provider,
                                                               ExternalRoleMapping.external_key == key,
                                                               ExternalRoleMapping.enabled.is_(True)))
        if mapping and mapping.application_role in APPLICATION_ROLES:
            return mapping.application_role, key
    return "EMPLOYEE", None


def _position_mapping(db: Session, provider: str, key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    row = db.scalar(select(ExternalPositionMapping).where(ExternalPositionMapping.provider == provider,
                                                          ExternalPositionMapping.external_position_key == key))
    if not row:
        return {"external_position_key": key, "status": "PENDING", "position_profile_id": None}
    return {"id": row.id, "external_position_key": row.external_position_key, "status": row.status,
            "position_profile_id": row.position_profile_id}


def _apply_position_mapping(db: Session, user: PortalUser, provider: str, key: str | None,
                            *, actor_id: int | None) -> bool:
    """Apply only an explicit mapping to an existing active profile."""

    if not key:
        return False
    mapping = db.scalar(select(ExternalPositionMapping).where(
        ExternalPositionMapping.provider == provider,
        ExternalPositionMapping.external_position_key == key))
    if not mapping:
        mapping = ExternalPositionMapping(provider=provider, external_position_key=key, status="PENDING")
        db.add(mapping)
        db.flush()
        return False
    if mapping.status != "MAPPED" or not mapping.position_profile_id:
        return False
    from .position_models import PositionAudit, PositionProfile, UserPosition
    profile = db.get(PositionProfile, mapping.position_profile_id)
    if not profile or profile.status != "ACTIVE":
        mapping.status = "PENDING"
        mapping.position_profile_id = None
        return False
    link = db.get(UserPosition, user.id)
    if link and link.profile_id == profile.id:
        return False
    before = {"profile_id": link.profile_id, "version": link.version} if link else {"profile_id": None, "version": 0}
    if link:
        link.profile_id = profile.id
        link.version += 1
        link.assigned_by = actor_id or user.id
        link.updated_at = utc_now()
    else:
        link = UserPosition(user_id=user.id, profile_id=profile.id, version=1, assigned_by=actor_id or user.id)
        db.add(link)
    db.add(PositionAudit(profile_id=profile.id, user_id=user.id, actor_id=actor_id or user.id,
                          actor_name=user.display_name, action="POSITION_SYNCED",
                          details_json=json_dumps({"provider": provider, "external_position_key": key,
                                                   "before": before, "after": {"profile_id": profile.id, "version": link.version}})))
    return True


def _legacy_org(db: Session, user_id: int) -> UserOrganization | None:
    return db.get(UserOrganization, user_id)


def _org_values(record: DirectoryUser) -> tuple[str | None, str | None]:
    return record.organization, record.unit


def _current_membership(db: Session, user_id: int) -> OrganizationMembership | None:
    return db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user_id,
                                                            OrganizationMembership.is_current.is_(True)))


def _close_directory_membership(db: Session, user_id: int, now) -> None:
    current = _current_membership(db, user_id)
    if current and current.source == "DIRECTORY":
        current.is_current = False
        current.valid_to = now


def _membership_name(db: Session, membership: OrganizationMembership | None) -> str | None:
    unit = db.get(OrganizationUnit, membership.organization_unit_id) if membership else None
    return unit.name if unit else None


def _set_membership(db: Session, user: PortalUser, record: DirectoryUser, provider: str, now) -> tuple[bool, OrganizationUnit | None]:
    org_name = record.organization_name or record.unit or record.organization
    if not org_name:
        return False, None
    unit = ensure_organization_unit(db, name=org_name, external_id=record.organization_external_id,
                                    parent_external_id=record.organization_parent_external_id, source="DIRECTORY")
    current = _current_membership(db, user.id)
    if current and current.organization_unit_id == unit.id and current.source == "DIRECTORY":
        return False, unit
    legacy = _legacy_org(db, user.id)
    if legacy and legacy.source and legacy.source.upper() in {"LOCAL", "MANUAL", "OVERRIDE"}:
        old = ", ".join(filter(None, (legacy.organization, legacy.unit)))
        new = ", ".join(filter(None, (record.organization, record.unit, org_name)))
        if old != new:
            raise IdentityConflictError("organization", old, new)
    if current:
        current.is_current = False
        current.valid_to = now
    db.add(OrganizationMembership(user_id=user.id, organization_unit_id=unit.id,
                                  valid_from=now, source="DIRECTORY", is_current=True))
    if legacy is None:
        legacy = UserOrganization(user_id=user.id)
        db.add(legacy)
    legacy.organization = record.organization or org_name
    legacy.unit = record.unit or (record.organization if record.organization else org_name)
    legacy.source = "DIRECTORY"
    legacy.updated_at = now
    return True, unit


def _validate_record_org_graph(records: list[DirectoryUser]) -> None:
    """Validate external parent references without writing during dry-run."""

    parents = {record.organization_external_id: record.organization_parent_external_id
               for record in records if record.organization_external_id}
    for start in parents:
        seen: set[str] = set()
        current = start
        while current:
            if current in seen:
                raise HTTPException(422, "Organizasyon ağacında döngü oluşturulamaz.")
            seen.add(current)
            current = parents.get(current)


def _prepare_organization_units(db: Session, records: list[DirectoryUser]) -> None:
    """Create/update all nodes first, then resolve parent links in a second pass."""

    for record in records:
        name = record.organization_name or record.unit or record.organization
        if name:
            ensure_organization_unit(db, name=name, external_id=record.organization_external_id,
                                     source="DIRECTORY")
    for record in records:
        if not record.organization_parent_external_id or not record.organization_external_id:
            continue
        child = db.scalar(select(OrganizationUnit).where(OrganizationUnit.external_id == record.organization_external_id))
        parent = db.scalar(select(OrganizationUnit).where(OrganizationUnit.external_id == record.organization_parent_external_id))
        if child and parent and child.parent_id != parent.id:
            _walk_parent(db, child.id, parent.id)
            child.parent_id = parent.id
            child.updated_at = utc_now()


class IdentityConflictError(Exception):
    def __init__(self, field: str, local_value: str, external_value: str):
        self.field, self.local_value, self.external_value = field, local_value, external_value
        super().__init__(f"{field} çatışması")


def _record_conflict(db: Session, provider: str, record: DirectoryUser, user_id: int | None,
                     field: str, local_value: str, external_value: str) -> IdentityConflict:
    existing = db.scalar(select(IdentityConflict).where(IdentityConflict.provider == provider,
        IdentityConflict.external_subject_id == record.external_subject_id, IdentityConflict.field == field,
        IdentityConflict.status == "OPEN"))
    if existing:
        return existing
    # A resolved/ignored decision for the exact same values remains stable on
    # subsequent full snapshots.  A genuinely changed value still creates a
    # fresh reviewable conflict.
    prior = db.scalar(select(IdentityConflict).where(
        IdentityConflict.provider == provider,
        IdentityConflict.external_subject_id == record.external_subject_id,
        IdentityConflict.field == field,
        IdentityConflict.local_value == (local_value or ""),
        IdentityConflict.external_value == (external_value or ""),
    ).order_by(IdentityConflict.id.desc()))
    if prior:
        return prior
    row = IdentityConflict(provider=provider, user_id=user_id, external_subject_id=record.external_subject_id,
                           field=field, local_value=local_value or "", external_value=external_value or "", status="OPEN")
    db.add(row)
    return row


def _user_by_username(db: Session, username: str) -> PortalUser | None:
    return db.scalar(select(PortalUser).where(func.lower(PortalUser.username) == username.lower()))


def _new_external_user(db: Session, record: DirectoryUser, role: str) -> PortalUser:
    # Random password means the new directory account cannot be entered through
    # the local fallback until an explicit local identity is provisioned.
    salt = secrets.token_hex(16)
    random_password = secrets.token_urlsafe(32)
    user = PortalUser(username=record.username, display_name=record.display_name, role=role,
                      password_salt=salt, password_hash=password_digest(random_password, salt), active=record.active)
    db.add(user)
    db.flush()
    return user


def _email_conflict(db: Session, link: ExternalIdentityLink, record: DirectoryUser) -> bool:
    if link.email_snapshot and record.email and link.email_snapshot.lower() != record.email.lower():
        return True
    return False


def _apply_record(db: Session, provider: str, record: DirectoryUser, *, actor_id: int | None,
                  run_id: int, now, links_by_subject: dict[str, ExternalIdentityLink],
                  records_by_subject: dict[str, DirectoryUser]) -> tuple[int, int, int]:
    """Apply a single record and return (created, updated, org_changes)."""

    created = updated = org_changes = 0
    link = links_by_subject.get(record.external_subject_id)
    was_active_external = bool(link and link.status == "ACTIVE")
    user = db.get(PortalUser, link.user_id) if link else _user_by_username(db, record.username)
    previous_active = user.active if user is not None else None
    role, role_group = _role_for_groups(db, provider, record.groups)
    if link is None and user is None:
        user = _new_external_user(db, record, role)
        created = 1
        link = ExternalIdentityLink(user_id=user.id, provider=provider,
            external_subject_id=record.external_subject_id, username_snapshot=record.username,
            email_snapshot=record.email, status="ACTIVE" if record.active else "INACTIVE",
            linked_at=now, last_seen_at=now, provider_metadata_json=json_dumps(_safe_json(record.metadata)))
        db.add(link)
        ensure_external_identity(db, user, provider, metadata=record.metadata)
        _audit(db, "external_identity_linked", provider=provider, user_id=user.id, sync_run_id=run_id,
               actor_id=actor_id, external_subject_id=record.external_subject_id)
    elif link is None and user is not None:
        # A username collision is a reviewable conflict; do not silently attach
        # a second external subject to a local person.
        _record_conflict(db, provider, record, user.id, "username", user.username, record.username)
        return 0, 0, 0
    else:
        email_conflict = _email_conflict(db, link, record)
        if email_conflict:
            _record_conflict(db, provider, record, user.id, "email", link.email_snapshot, record.email)
        elif record.email:
            # An initially missing snapshot is safe to populate; a changed
            # non-empty value stays frozen until the conflict is resolved.
            link.email_snapshot = record.email
        if link.username_snapshot and link.username_snapshot.lower() != record.username.lower():
            _record_conflict(db, provider, record, user.id, "username", link.username_snapshot, record.username)
        elif record.username:
            link.username_snapshot = record.username
        link.status = "ACTIVE" if record.active else "INACTIVE"
        link.last_seen_at = now
        link.provider_metadata_json = json_dumps(_safe_json(record.metadata))
        ensure_external_identity(db, user, provider, metadata=record.metadata)
        before = (user.display_name, user.active, user.role)
        if user.display_name != record.display_name:
            user.display_name = record.display_name
        user.active = bool(record.active)
        if role_group and role != user.role:
            user.role = role
            _audit(db, "role_mapping_changed", provider=provider, user_id=user.id, sync_run_id=run_id,
                   actor_id=actor_id, external_group=role_group, role=role)
        elif not role_group and user.role != "EMPLOYEE":
            # An external-only account must not retain a previously elevated
            # role after its mapped group disappears or becomes unknown.  A
            # separately provisioned LOCAL identity is left untouched because
            # that role may be an intentional local/manual authorization.
            has_local_identity = bool(db.scalar(select(Identity.id).where(
                Identity.user_id == user.id, Identity.identity_type == "LOCAL", Identity.status == "ACTIVE")))
            if not has_local_identity:
                user.role = "EMPLOYEE"
                _audit(db, "role_mapping_changed", provider=provider, user_id=user.id, sync_run_id=run_id,
                       actor_id=actor_id, external_group=None, role="EMPLOYEE")
        if before != (user.display_name, user.active, user.role):
            updated = 1
    if user is None or link is None:
        return created, updated, org_changes
    local_identity_active = False
    if not record.active:
        db.execute(update(Identity).where(Identity.user_id == user.id,
                                          Identity.identity_type == "DIRECTORY",
                                          Identity.provider == provider).values(status="INACTIVE"))
        local_identity_active = bool(db.scalar(select(Identity.id).where(
            Identity.user_id == user.id, Identity.identity_type == "LOCAL", Identity.status == "ACTIVE")))
        if not local_identity_active:
            user.active = False
            db.execute(update(AccountSession).where(AccountSession.user_id == user.id).values(expires_at=now))
        elif previous_active is not None:
            # An explicit local identity is the documented emergency fallback;
            # an external deactivation must not revoke that separate account.
            user.active = bool(previous_active)
        if was_active_external:
            _audit(db, "identity_disabled", provider=provider, user_id=user.id, sync_run_id=run_id,
                   actor_id=actor_id, external_subject_id=record.external_subject_id)
    try:
        changed, unit = _set_membership(db, user, record, provider, now)
        if changed:
            org_changes += 1
            _audit(db, "organization_changed", provider=provider, user_id=user.id, sync_run_id=run_id,
                   actor_id=actor_id, organization_unit_id=unit.id if unit else None)
    except IdentityConflictError as error:
        _record_conflict(db, provider, record, user.id, error.field, error.local_value, error.external_value)
    if not record.active and not local_identity_active:
        _close_directory_membership(db, user.id, now)
    if record.position_key:
        mapping = _position_mapping(db, provider, record.position_key)
        if mapping and mapping.get("status") == "PENDING":
            _apply_position_mapping(db, user, provider, record.position_key, actor_id=actor_id)
            _record_conflict(db, provider, record, user.id, "position", "", record.position_key)
        elif mapping and mapping.get("status") == "MAPPED":
            if _apply_position_mapping(db, user, provider, record.position_key, actor_id=actor_id):
                updated = 1
    return created, updated, org_changes


def _apply_manager_relations(db: Session, provider: str, records: list[DirectoryUser], *, run_id: int, actor_id: int | None, now) -> None:
    links = {row.external_subject_id: row for row in db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider))}
    for record in records:
        link = links.get(record.external_subject_id)
        if not link:
            continue
        current = db.scalar(select(UserManagerRelation).where(UserManagerRelation.user_id == link.user_id,
                                                               UserManagerRelation.is_current.is_(True)))
        manager_link = links.get(record.manager_external_id) if record.manager_external_id else None
        if not manager_link or manager_link.status != "ACTIVE" or manager_link.user_id == link.user_id:
            # A full directory snapshot is authoritative.  Close a previous
            # directory relation when the manager is now absent, inactive, or
            # self-referential; never invent a placeholder person.
            if current and current.source == "DIRECTORY":
                current.is_current = False
                current.valid_to = now
                legacy = _legacy_org(db, link.user_id)
                if legacy and (not legacy.source or legacy.source.upper() not in {"LOCAL", "MANUAL", "OVERRIDE"}):
                    legacy.manager_user_id = None
                    legacy.updated_at = now
                _audit(db, "manager_changed", provider=provider, user_id=link.user_id, sync_run_id=run_id,
                       actor_id=actor_id, manager_user_id=None)
            continue
        if current and current.manager_user_id == manager_link.user_id:
            continue
        if current:
            current.is_current = False
            current.valid_to = now
        db.add(UserManagerRelation(user_id=link.user_id, manager_user_id=manager_link.user_id,
                                   valid_from=now, source="DIRECTORY", is_current=True))
        legacy = _legacy_org(db, link.user_id)
        if legacy and (not legacy.source or legacy.source.upper() not in {"LOCAL", "MANUAL", "OVERRIDE"}):
            legacy.manager_user_id = manager_link.user_id
            legacy.updated_at = now
        _audit(db, "manager_changed", provider=provider, user_id=link.user_id, sync_run_id=run_id,
               actor_id=actor_id, manager_user_id=manager_link.user_id)


def _plan(db: Session, provider: str, records: list[DirectoryUser]) -> dict[str, Any]:
    if len({record.external_subject_id for record in records}) != len(records):
        raise HTTPException(422, "Aynı external identity bir senkronizasyonda birden fazla kez gelemez.")
    links = {row.external_subject_id: row for row in db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider))}
    existing = 0
    updates = 0
    org_changes = 0
    creates = 0
    conflicts: list[dict[str, Any]] = []
    subjects = set()
    for record in records:
        subjects.add(record.external_subject_id)
        link = links.get(record.external_subject_id)
        user = db.get(PortalUser, link.user_id) if link else _user_by_username(db, record.username)
        if link:
            existing += 1
            if user and (user.display_name != record.display_name or user.active != record.active):
                updates += 1
            if _email_conflict(db, link, record):
                conflicts.append({"field": "email", "external_subject_id": record.external_subject_id,
                                  "user_id": user.id if user else None})
        elif user:
            conflicts.append({"field": "username", "external_subject_id": record.external_subject_id, "user_id": user.id})
        else:
            creates += 1
        if record.organization or record.unit or record.organization_name:
            current = _current_membership(db, user.id) if user else None
            current_name = _membership_name(db, current)
            expected = record.organization_name or record.unit or record.organization
            if (user is None and expected) or (current_name and expected and current_name != expected):
                org_changes += 1
        mapping = _position_mapping(db, provider, record.position_key)
        if mapping and mapping["status"] == "PENDING":
            conflicts.append({"field": "position", "external_subject_id": record.external_subject_id, "user_id": user.id if user else None})
    deactivated = sum(1 for subject, link in links.items() if link.status == "ACTIVE" and subject not in subjects)
    return {"provider": provider, "users_seen": len(records), "created": creates, "updated": updates,
            "deactivated": deactivated, "organization_changes": org_changes, "conflicts": conflicts}


def sync_directory(db: Session, records: Iterable[DirectoryUser | dict[str, Any]] | None = None, *,
                   provider: str | DirectoryProvider | None = None, dry_run: bool = True,
                   apply: bool = False, actor_id: int | None = None, actor: Any = None) -> dict[str, Any]:
    """Run a safe directory sync.  ``dry_run`` never writes any database row."""

    if actor_id is None and actor is not None:
        actor_id = getattr(actor, "user_id", None)
    selected = provider
    requested_provider_name = provider.strip().lower() if isinstance(provider, str) else None
    inline_records = records is not None and not hasattr(provider, "users")
    if not hasattr(selected, "users"):
        if requested_provider_name == "fake" and records is None:
            # A development-only fake snapshot may intentionally be empty so
            # deactivation behavior can be tested without a network provider.
            selected = FakeDirectoryProvider(())
        else:
            selected = directory_provider(records) if records is not None else directory_provider()
    provider_name = requested_provider_name or getattr(selected, "name", None) or settings.directory_provider or "directory"
    if records is None:
        try:
            records = list(selected.users())
        except ProviderNotConfigured as error:
            if apply:
                raise HTTPException(409, "Directory sağlayıcısı etkin değil; gerçek veri değiştirilemedi.") from error
            return {"provider": provider_name, "configured": False, "dry_run": True,
                    "applied": False, "message": str(error), "summary": {"users_seen": 0, "created": 0,
                    "updated": 0, "deactivated": 0, "organization_changes": 0, "conflicts": []}}
    normalized = [DirectoryUser.from_mapping(item) for item in records]
    if provider_name == "fake" and settings.environment not in {"development", "test", "local"}:
        raise HTTPException(403, "Test directory sağlayıcısı yalnızca geliştirme ortamında kullanılabilir.")
    _validate_record_org_graph(normalized)
    plan = _plan(db, provider_name, normalized)
    # ``apply`` is the sole mutation switch.  A malformed request that sends
    # dry_run=false without explicit apply must remain a no-op.
    is_dry = not bool(apply)
    if is_dry:
        return {"provider": provider_name, "configured": True, "dry_run": True, "applied": False,
                "summary": plan, "sync_run": None}
    # Inline records are a test/dev convenience.  They may be previewed under
    # any label, but an apply operation labelled as a real provider still
    # requires that provider's explicit configuration.
    if inline_records and provider_name != "fake" and not settings.directory_configured:
        raise HTTPException(409, "Directory sağlayıcısı etkin değil; gerçek veri değiştirilemedi.")
    if provider_name != "fake" and not getattr(selected, "configured", lambda: False)():
        raise HTTPException(409, "Directory sağlayıcısı etkin değil; gerçek veri değiştirilemedi.")
    now = utc_now()
    run = SyncRun(provider=provider_name, started_at=now, status="RUNNING", triggered_by=actor_id, dry_run=False)
    db.add(run)
    db.flush()
    links = {row.external_subject_id: row for row in db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider_name))}
    created = updated = org_changes = 0
    errors: list[str] = []
    explicit_deactivations = sum(
        1 for record in normalized
        if (links.get(record.external_subject_id) is not None
            and links[record.external_subject_id].status == "ACTIVE"
            and not record.active)
    )
    try:
        _prepare_organization_units(db, normalized)
        for record in normalized:
            try:
                # A savepoint isolates one malformed directory row without
                # rolling back the successful rows already applied in this run.
                with db.begin_nested():
                    c, u, o = _apply_record(db, provider_name, record, actor_id=actor_id, run_id=run.id,
                                             now=now, links_by_subject=links,
                                             records_by_subject={r.external_subject_id: r for r in normalized})
                created += c
                updated += u
                org_changes += o
            except (HTTPException, ValueError, IntegrityError) as error:
                errors.append(type(error).__name__)
        if not errors:
            # Absence is authoritative only for a complete provider snapshot.
            # A partially failed run must not mass-deactivate users or close
            # manager relations based on rows that may never have arrived.
            current_links = {row.external_subject_id: row for row in db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider_name))}
            seen_subjects = {item.external_subject_id for item in normalized}
            for subject, link in current_links.items():
                if link.status == "ACTIVE" and subject not in seen_subjects:
                    link.status = "INACTIVE"
                    db.execute(update(Identity).where(Identity.user_id == link.user_id,
                                                      Identity.identity_type == "DIRECTORY",
                                                      Identity.provider == provider_name).values(status="INACTIVE"))
                    user = db.get(PortalUser, link.user_id)
                    other_external = db.scalar(select(ExternalIdentityLink.id).where(
                        ExternalIdentityLink.user_id == link.user_id,
                        ExternalIdentityLink.status == "ACTIVE",
                        ExternalIdentityLink.id != link.id))
                    if user and not db.scalar(select(Identity.id).where(Identity.user_id == user.id, Identity.identity_type == "LOCAL", Identity.status == "ACTIVE")) and not other_external:
                        user.active = False
                        db.execute(update(AccountSession).where(AccountSession.user_id == user.id).values(expires_at=now))
                    if user:
                        _close_directory_membership(db, user.id, now)
                    _audit(db, "identity_disabled", provider=provider_name, user_id=link.user_id, sync_run_id=run.id, actor_id=actor_id,
                           external_subject_id=subject)
            _apply_manager_relations(db, provider_name, normalized, run_id=run.id, actor_id=actor_id, now=now)
        run.users_seen = len(normalized)
        run.created = created
        run.updated = updated
        deactivated = explicit_deactivations + (plan["deactivated"] if not errors else 0)
        run.deactivated = deactivated
        run.organization_changes = org_changes
        run.errors_json = json_dumps(errors)
        run.status = "COMPLETED" if not errors else "FAILED"
        run.completed_at = utc_now()
        _audit(db, "sync_applied", provider=provider_name, sync_run_id=run.id, actor_id=actor_id,
               users_seen=len(normalized), created=created, updated=updated, deactivated=deactivated, errors=len(errors))
        db.commit()
        # Reconcile existing mandatory policies only after the sync is safely
        # committed.  The governance engine creates requirement snapshots, not
        # enrollments, and a reconciliation error cannot undo the sync run.
        try:
            from .governance import sync_requirements
            for link in db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider_name,
                                                                       ExternalIdentityLink.status == "ACTIVE")):
                sync_requirements(db, link.user_id)
        except Exception:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    return {"provider": provider_name, "configured": True, "dry_run": False, "applied": True,
            "summary": {**plan, "created": created, "updated": updated, "deactivated": deactivated,
                         "organization_changes": org_changes,
                         "errors": errors}, "sync_run": sync_run_payload(run)}


def list_sync_runs(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    return [sync_run_payload(row) for row in db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit))]


def list_conflicts(db: Session, status: str = "OPEN", limit: int = 100) -> list[dict[str, Any]]:
    if status not in CONFLICT_STATUSES:
        raise HTTPException(422, "Geçersiz çatışma durumu.")
    rows = db.scalars(select(IdentityConflict).where(IdentityConflict.status == status).order_by(IdentityConflict.id.desc()).limit(limit))
    return [{"id": row.id, "provider": row.provider, "user_id": row.user_id, "external_subject_id": row.external_subject_id,
             "field": row.field, "local_value": row.local_value, "external_value": row.external_value,
             "status": row.status, "resolution": row.resolution, "created_at": utc_stamp(row.created_at),
             "resolved_at": utc_stamp(row.resolved_at)} for row in rows]


def resolve_conflict(db: Session, actor: Any, conflict_id: int, resolution: str) -> dict[str, Any]:
    row = db.get(IdentityConflict, conflict_id)
    if not row:
        raise HTTPException(404, "Kimlik çatışması bulunamadı.")
    resolution = resolution.strip().upper()
    if resolution not in {"ACCEPT_EXTERNAL", "KEEP_LOCAL", "IGNORE"}:
        raise HTTPException(422, "Geçersiz çatışma kararı.")
    row.status = "IGNORED" if resolution == "IGNORE" else "RESOLVED"
    row.resolution = resolution
    row.resolved_by = getattr(actor, "user_id", None)
    row.resolved_at = utc_now()
    if resolution == "ACCEPT_EXTERNAL" and row.field == "email" and row.user_id:
        link = db.scalar(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == row.provider,
            ExternalIdentityLink.user_id == row.user_id))
        if link:
            link.email_snapshot = row.external_value
    _audit(db, "conflict_resolved", provider=row.provider, user_id=row.user_id, actor_id=getattr(actor, "user_id", None),
           conflict_id=row.id, resolution=resolution)
    db.commit()
    return {"id": row.id, "status": row.status, "resolution": row.resolution, "resolved_at": utc_stamp(row.resolved_at)}


def identity_detail(db: Session, actor: Any, user_id: int) -> dict[str, Any]:
    user = db.get(PortalUser, user_id)
    if not user:
        raise HTTPException(404, "Kullanıcı bulunamadı.")
    identities = list(db.scalars(select(Identity).where(Identity.user_id == user.id).order_by(Identity.id)))
    links = list(db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.user_id == user.id).order_by(ExternalIdentityLink.id)))
    legacy = _legacy_org(db, user.id)
    membership = _current_membership(db, user.id)
    manager = db.get(PortalUser, legacy.manager_user_id) if legacy and legacy.manager_user_id else None
    if manager is None:
        relation = db.scalar(select(UserManagerRelation).where(UserManagerRelation.user_id == user.id, UserManagerRelation.is_current.is_(True)))
        manager = db.get(PortalUser, relation.manager_user_id) if relation else None
    authentication_source = [row.identity_type for row in identities]
    if not authentication_source:
        authentication_source = ["SSO" if link.provider == settings.oidc_provider else "DIRECTORY" for link in links] or ["LOCAL"]
    return {
        "id": user.id, "username": user.username, "display_name": user.display_name, "active": bool(user.active),
        "authentication_source": authentication_source,
        "identities": [{"type": row.identity_type, "provider": row.provider, "status": row.status,
                        "last_authenticated_at": utc_stamp(row.last_authenticated_at)} for row in identities],
        "external_identity_linked": bool(links),
        "external_identities": [{"provider": row.provider, "external_subject_id": row.external_subject_id,
                                  "username": row.username_snapshot, "email": row.email_snapshot,
                                  "status": row.status, "linked_at": utc_stamp(row.linked_at),
                                  "last_seen_at": utc_stamp(row.last_seen_at)} for row in links],
        "organization": {"id": membership.organization_unit_id, "name": _membership_name(db, membership),
                          "source": membership.source} if membership else {"name": legacy.organization if legacy else None,
                                                                               "unit": legacy.unit if legacy else None,
                                                                               "source": legacy.source if legacy else None},
        "manager": {"id": manager.id, "display_name": manager.display_name} if manager else None,
        "sync_status": {"active_external_links": sum(row.status == "ACTIVE" for row in links),
                         "last_seen_at": utc_stamp(max((row.last_seen_at for row in links if row.last_seen_at), default=None))},
    }


def identity_users(db: Session, search: str = "", limit: int = 100) -> list[dict[str, Any]]:
    query = select(PortalUser)
    if search:
        term = search.strip()
        query = query.where(or_(PortalUser.username.icontains(term, autoescape=True),
                                PortalUser.display_name.icontains(term, autoescape=True)))
    rows = db.scalars(query.order_by(PortalUser.username).limit(limit))
    out = []
    for user in rows:
        links = list(db.scalars(select(ExternalIdentityLink).where(ExternalIdentityLink.user_id == user.id)))
        legacy = _legacy_org(db, user.id)
        identity_types = sorted({row.identity_type for row in db.scalars(
            select(Identity).where(Identity.user_id == user.id))})
        if not identity_types:
            identity_types = sorted({"SSO" if link.provider == settings.oidc_provider else "DIRECTORY" for link in links}) or ["LOCAL"]
        out.append({"id": user.id, "username": user.username, "display_name": user.display_name,
                    "active": bool(user.active), "authentication_source": identity_types,
                    "external_identity_linked": bool(links),
                    "organization": legacy.organization if legacy else None,
                    "unit": legacy.unit if legacy else None,
                    "sync_status": "ACTIVE" if any(row.status == "ACTIVE" for row in links) else "INACTIVE" if links else "LOCAL"})
    return out


def add_role_mapping(db: Session, actor: Any, provider: str, external_key: str, application_role: str, enabled: bool = True) -> dict[str, Any]:
    provider, external_key, application_role = provider.strip().lower(), external_key.strip(), application_role.strip().upper()
    if not provider or not external_key or application_role not in APPLICATION_ROLES:
        raise HTTPException(422, "Sağlayıcı, dış grup ve mevcut uygulama rolü geçerli olmalıdır.")
    row = db.scalar(select(ExternalRoleMapping).where(ExternalRoleMapping.provider == provider,
                                                       ExternalRoleMapping.external_key == external_key))
    if row:
        row.application_role, row.enabled, row.updated_at = application_role, bool(enabled), utc_now()
    else:
        row = ExternalRoleMapping(provider=provider, external_key=external_key, application_role=application_role,
                                  enabled=bool(enabled), created_by=getattr(actor, "user_id", None))
        db.add(row)
    _audit(db, "role_mapping_changed", provider=provider, actor_id=getattr(actor, "user_id", None),
           external_group=external_key, role=application_role, enabled=bool(enabled))
    db.commit()
    return {"id": row.id, "provider": row.provider, "external_key": row.external_key,
            "application_role": row.application_role, "enabled": bool(row.enabled)}


def role_mappings(db: Session, provider: str | None = None) -> list[dict[str, Any]]:
    query = select(ExternalRoleMapping)
    if provider:
        query = query.where(ExternalRoleMapping.provider == provider.strip().lower())
    rows = db.scalars(query.order_by(ExternalRoleMapping.provider, ExternalRoleMapping.external_key))
    return [{"id": row.id, "provider": row.provider, "external_key": row.external_key,
             "application_role": row.application_role, "enabled": bool(row.enabled)} for row in rows]


def add_position_mapping(db: Session, actor: Any, provider: str, external_position_key: str,
                         position_profile_id: int | None = None) -> dict[str, Any]:
    from .position_models import PositionProfile
    provider, external_position_key = provider.strip().lower(), external_position_key.strip()
    if not provider or not external_position_key:
        raise HTTPException(422, "Sağlayıcı ve dış pozisyon anahtarı zorunludur.")
    if position_profile_id is not None:
        profile = db.get(PositionProfile, position_profile_id)
        if not profile or profile.status != "ACTIVE":
            raise HTTPException(404, "Eşleştirilecek aktif pozisyon profili bulunamadı.")
    row = db.scalar(select(ExternalPositionMapping).where(ExternalPositionMapping.provider == provider,
                                                           ExternalPositionMapping.external_position_key == external_position_key))
    if row:
        row.position_profile_id = position_profile_id
        row.status = "MAPPED" if position_profile_id else "PENDING"
        row.updated_at = utc_now()
    else:
        row = ExternalPositionMapping(provider=provider, external_position_key=external_position_key,
                                      position_profile_id=position_profile_id,
                                      status="MAPPED" if position_profile_id else "PENDING",
                                      created_by=getattr(actor, "user_id", None))
        db.add(row)
    db.commit()
    return {"id": row.id, "provider": row.provider, "external_position_key": row.external_position_key,
            "position_profile_id": row.position_profile_id, "status": row.status}


def position_mappings(db: Session, provider: str | None = None) -> list[dict[str, Any]]:
    query = select(ExternalPositionMapping)
    if provider:
        query = query.where(ExternalPositionMapping.provider == provider.strip().lower())
    rows = db.scalars(query.order_by(ExternalPositionMapping.provider, ExternalPositionMapping.external_position_key))
    return [{"id": row.id, "provider": row.provider, "external_position_key": row.external_position_key,
             "position_profile_id": row.position_profile_id, "status": row.status} for row in rows]


class OIDCStateStore:
    """Short-lived state/nonce store for an OIDC authorization round trip."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._states: dict[str, tuple[str, Any]] = {}

    def create(self) -> tuple[str, str]:
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._purge()
        self._states[state] = (nonce, utc_now())
        return state, nonce

    def consume(self, state: str, nonce: str) -> bool:
        self._purge()
        row = self._states.pop(str(state), None)
        if not row:
            return False
        expected, created = row
        return bool(hmac.compare_digest(expected, str(nonce)) and utc_now() - created <= self.ttl)

    def _purge(self) -> None:
        now = utc_now()
        self._states = {key: value for key, value in self._states.items() if now - value[1] <= self.ttl}


oidc_state_store = OIDCStateStore()


def validate_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri or "")
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"} and bool(parsed.netloc)


def validate_oidc_claims(claims: dict[str, Any], *, issuer: str | None = None,
                         audience: str | None = None, now: int | None = None) -> dict[str, Any]:
    """Validate the security-critical OIDC claims without exposing tokens."""

    claims = dict(claims or {})
    expected_issuer = (issuer or settings.oidc_issuer or "").rstrip("/")
    expected_audience = audience or settings.oidc_client_id
    if expected_issuer and str(claims.get("iss", "")).rstrip("/") != expected_issuer:
        raise HTTPException(401, "SSO issuer doğrulanamadı.")
    aud = claims.get("aud")
    if expected_audience and not (aud == expected_audience or isinstance(aud, list) and expected_audience in aud):
        raise HTTPException(401, "SSO audience doğrulanamadı.")
    expiry = claims.get("exp")
    if expiry is None:
        raise HTTPException(401, "SSO token süresi bulunamadı.")
    try:
        if float(expiry) <= float(now if now is not None else time.time()):
            raise HTTPException(401, "SSO token süresi dolmuş.")
    except (TypeError, ValueError):
        raise HTTPException(401, "SSO token süresi geçersiz.")
    return _safe_json(claims)


def oidc_authorization(db: Session | None = None) -> dict[str, Any]:
    if not settings.oidc_configured:
        raise HTTPException(404, "SSO sağlayıcısı yapılandırılmadı.")
    if not validate_redirect_uri(settings.oidc_redirect_uri):
        raise HTTPException(500, "SSO geri dönüş adresi güvenli değil.")
    state, nonce = oidc_state_store.create()
    query = urlencode({"client_id": settings.oidc_client_id, "response_type": "code", "redirect_uri": settings.oidc_redirect_uri,
                       "scope": settings.oidc_scopes, "state": state, "nonce": nonce})
    return {"provider": settings.oidc_provider, "authorization_url": f"{settings.oidc_issuer}/authorize?{query}",
            "state": state, "expires_in": int(oidc_state_store.ttl.total_seconds())}


def resolve_oidc_identity(db: Session, *, subject: str, claims: dict[str, Any], provider: str | None = None,
                          jit: bool | None = None) -> PortalUser:
    """Resolve a validated OIDC subject for tests or a future token adapter."""

    provider = (provider or settings.oidc_provider or "oidc").strip().lower()
    # Claims entering the identity resolver must have passed the same
    # issuer/audience/expiry checks as a real token adapter.  The caller may
    # still supply a provider-specific adapter; this function never accepts a
    # raw, unvalidated claim set merely because it is marked as a simulation.
    claims = validate_oidc_claims(claims)
    subject = str(subject or "").strip()
    if not subject:
        raise HTTPException(422, "OIDC subject zorunludur.")
    link = db.scalar(select(ExternalIdentityLink).where(ExternalIdentityLink.provider == provider,
                                                        ExternalIdentityLink.external_subject_id == subject))
    if link:
        user = db.get(PortalUser, link.user_id)
        if not user or not user.active or link.status != "ACTIVE":
            raise HTTPException(401, "SSO kimliği pasif durumda.")
        now = utc_now()
        link.last_seen_at = now
        identity_row = db.scalar(select(Identity).where(
            Identity.user_id == user.id, Identity.identity_type == "SSO", Identity.provider == provider))
        if identity_row:
            identity_row.last_authenticated_at = now
        db.commit()
        return user
    # A call-site flag may disable a configured JIT flow for a particular
    # adapter invocation, but it can never enable provisioning against the
    # provider policy.  Unknown identities therefore remain blocked unless
    # configuration explicitly opts in.
    allow_jit = bool(settings.oidc_jit_enabled and jit is not False)
    if not allow_jit:
        raise HTTPException(403, "Bu SSO kimliği için otomatik kullanıcı oluşturma etkin değil.")
    username = str(claims.get("preferred_username") or claims.get("email") or "").strip().lower()
    display_name = str(claims.get("name") or username).strip()
    if not username or not display_name:
        raise HTTPException(422, "SSO claims içinde kullanıcı adı ve görünen ad bulunamadı.")
    existing = _user_by_username(db, username)
    if existing:
        _record_conflict(db, provider, DirectoryUser(subject, username, display_name, str(claims.get("email") or "")),
                         existing.id, "username", existing.username, username)
        db.commit()
        raise HTTPException(409, "SSO kimliği mevcut kullanıcı adıyla çatışıyor; yönetici incelemesi gerekiyor.")
    now = utc_now()
    user = _new_external_user(db, DirectoryUser(subject, username, display_name, str(claims.get("email") or "")), "EMPLOYEE")
    db.add(ExternalIdentityLink(user_id=user.id, provider=provider, external_subject_id=subject,
                                username_snapshot=username, email_snapshot=str(claims.get("email") or ""),
                                status="ACTIVE", linked_at=now, last_seen_at=now,
                                provider_metadata_json=json_dumps(_safe_json(claims))))
    db.add(Identity(user_id=user.id, identity_type="SSO", provider=provider, status="ACTIVE",
                    metadata_json=json_dumps(_safe_json(claims)), last_authenticated_at=now))
    _audit(db, "external_identity_linked", provider=provider, user_id=user.id,
           external_subject_id=subject)
    db.commit()
    return user


class OIDCProvider:
    """Provider-neutral OIDC foundation; token exchange belongs to deployment."""

    name = settings.oidc_provider or "oidc"

    def configured(self) -> bool:
        return settings.oidc_configured

    def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        # A caller supplies already validated claims after its token adapter
        # has checked issuer, audience, nonce and expiry.
        claims = validate_oidc_claims(credentials.get("claims") or {})
        return self.resolve_identity(claims)

    def resolve_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject = payload.get("sub") or payload.get("subject")
        if not subject:
            raise HTTPException(422, "OIDC subject bulunamadı.")
        return {"external_subject_id": str(subject), "username": payload.get("preferred_username") or payload.get("email"),
                "display_name": payload.get("name") or payload.get("preferred_username") or payload.get("email")}

    def resolve_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"organization": payload.get("organization"), "unit": payload.get("unit"),
                "position_key": payload.get("position_key") or payload.get("job_code")}

    def sync_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.resolve_profile(payload)
