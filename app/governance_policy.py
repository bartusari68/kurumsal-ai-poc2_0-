"""Server-side authorization and labels for learning governance."""
from fastapi import HTTPException

MANAGE_ROLES = {"NEEDS_ANALYST"}
READ_ROLES = {"NEEDS_ANALYST", "TECHNICAL_DESIGN", "ENGINEERING_DESIGN"}
POLICY_STATUSES = {"ACTIVE": "Aktif", "INACTIVE": "Pasif"}
GOVERNANCE_STATUSES = {"CURRENT": "Güncel", "REVIEW_DUE": "İnceleme zamanı geldi", "UNDER_REVIEW": "İncelemede"}
LIFECYCLE = {"ACTIVE": "Aktif", "RETIRED": "Emekli"}
REVIEW_DECISIONS = {"KEEP_CURRENT": "Mevcut sürümü koru", "UPDATE_REQUIRED": "Güncelleme gerekli", "RETIREMENT_REVIEW": "Emeklilik değerlendirmesi"}
REQUIREMENT_STATUSES = {"PENDING": "Bekliyor", "FULFILLED": "Tamamlandı", "WAIVED": "Muaf", "EXPIRED": "Süresi geçti"}


def require_manager(actor):
    if not actor or actor.role not in MANAGE_ROLES:
        raise HTTPException(403, "Bu işlem yalnızca ihtiyaç analizi yöneticisine aittir.")


def can_read(actor):
    return bool(actor and actor.role in READ_ROLES)


def require_read(actor):
    if not can_read(actor):
        raise HTTPException(403, "Bu yönetişim görünümü için yönetici yetkisi gerekir.")

