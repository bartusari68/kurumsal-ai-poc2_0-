"""Safe, actionable provider errors. Never expose provider bodies or account IDs."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx


class AIServiceError(RuntimeError):
    def __init__(self, detail: str, *, code: str, component: str,
                 status_code: int = 502, ai_status: str = "error",
                 retry_at: str | None = None, quota_limit: int | None = None,
                 quota_remaining: int | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.payload = {"detail": detail, "error_code": code, "component": component,
                        "ai_status": ai_status, "retry_at": retry_at,
                        "quota_limit": quota_limit, "quota_remaining": quota_remaining}


def _integer(value) -> int | None:
    try:
        number = int(value)
        return number if number >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _retry_at(headers: dict) -> str | None:
    try:
        raw = headers.get("x-ratelimit-reset")
        if raw is not None:
            timestamp = float(raw)
            if timestamp > 100_000_000_000:  # OpenRouter may supply milliseconds.
                timestamp /= 1000
        else:
            raw = headers.get("retry-after")
            if raw is None:
                return None
            try:
                timestamp = datetime.now(timezone.utc).timestamp() + max(0, float(raw))
            except ValueError:
                timestamp = parsedate_to_datetime(raw).timestamp()
        if not math.isfinite(timestamp):
            return None
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def provider_error(error: httpx.HTTPError, component: str) -> AIServiceError:
    labels = {"analysis": "Talep analizi", "embedding": "PDF araması", "rerank": "Sonuç sıralama", "chat": "Ders asistanı"}
    label = labels.get(component, "Yapay zekâ")
    if isinstance(error, httpx.TimeoutException):
        return AIServiceError(f"{label} hizmeti zamanında yanıt vermedi. Uygulama sunucusu çalışıyor; daha sonra tekrar deneyin.",
                              code="AI_TIMEOUT", component=component, status_code=504)
    if not isinstance(error, httpx.HTTPStatusError):
        return AIServiceError(f"{label} sağlayıcısına bağlantı kurulamadı. Uygulama sunucusu çalışıyor; daha sonra tekrar deneyin.",
                              code="AI_PROVIDER_UNAVAILABLE", component=component)
    response = error.response
    try:
        body = response.json().get("error", {})
        body = body if isinstance(body, dict) else {}
        metadata = body.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
    except (ValueError, AttributeError):
        body, metadata = {}, {}
    extra_headers = metadata.get("headers", {})
    headers = {str(k).lower(): str(v) for k, v in extra_headers.items()} if isinstance(extra_headers, dict) else {}
    headers.update({k.lower(): v for k, v in response.headers.items()})
    if response.status_code == 429:
        daily = metadata.get("limit_source") == "openrouter_free_tier_daily" or "free-models-per-day" in str(body.get("message", ""))
        return AIServiceError(
            "OpenRouter günlük ücretsiz analiz kotası doldu. Kota yenilenene veya hesap limiti güncellenene kadar yeni analiz yapılamaz."
            if daily else f"{label} hizmetinin istek sınırına ulaşıldı. Bekleyip yeniden deneyin.",
            code="AI_DAILY_QUOTA_EXCEEDED" if daily else "AI_RATE_LIMITED", component=component,
            status_code=429, ai_status="quota", retry_at=_retry_at(headers),
            quota_limit=_integer(headers.get("x-ratelimit-limit")),
            quota_remaining=_integer(headers.get("x-ratelimit-remaining")))
    if response.status_code == 402:
        return AIServiceError("Yapay zekâ hesabının kredi/bütçe limiti yetersiz. Hesap yöneticisinin limiti kontrol etmesi gerekiyor.",
                              code="AI_CREDIT_REQUIRED", component=component, status_code=503, ai_status="credit")
    if response.status_code in (401, 403):
        return AIServiceError("Yapay zekâ anahtarının yetkisi doğrulanamadı. Sunucudaki bağlantı ayarlarını kontrol edin.",
                              code="AI_AUTH_ERROR", component=component, status_code=503)
    return AIServiceError(f"{label} hizmeti isteği tamamlayamadı. Daha sonra tekrar deneyin.",
                          code="AI_PROVIDER_ERROR", component=component)
