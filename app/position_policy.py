"""Position stewardship is separate from authentication roles and skill levels."""
from fastapi import HTTPException

MANAGEMENT_ROLES = frozenset({'NEEDS_ANALYST'})
# Disclosure protection, not a proficiency or employee assessment threshold.
MIN_AGGREGATE_USERS = 5
STATES = {
    'NO_EVIDENCE': 'Kanıt bulunamadı',
    'EVIDENCE_PRESENT': 'Kanıt kaydı mevcut',
    'DEVELOPMENT_EVIDENCE': 'Gelişim kanıtı mevcut',
    'OUTCOME_EVIDENCE': 'Sonuç kanıtı mevcut',
}
TYPES = {'REQUIRED': 'Gerekli', 'RECOMMENDED': 'Önerilen'}

def can_manage(actor):
    return bool(actor and actor.role in MANAGEMENT_ROLES)

def require_manager(actor):
    if not can_manage(actor):
        raise HTTPException(403, 'Pozisyon profillerini ihtiyaç analizi yöneticisi yönetir.')
