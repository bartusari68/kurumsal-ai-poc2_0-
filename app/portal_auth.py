"""Named local accounts with server-enforced roles. Not corporate SSO."""
from .time_policy import utc_now, as_utc, utc_stamp
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .config import PROJECT_ROOT
from .database import SessionLocal, get_db
from .models import AccountSession, PortalUser

COOKIE = "learning_account_session"
AUTH_PATH = PROJECT_ROOT / "data/admin-auth.json"
ACCESS_PATH = PROJECT_ROOT / "data/admin-access.txt"
ACCOUNTS_PATH = PROJECT_ROOT / "data/portal-accounts.txt"
ROLES = {
    "EMPLOYEE": "Çalışan",
    "NEEDS_ANALYST": "İhtiyaç Analizi Yöneticisi",
    "TECHNICAL_DESIGN": "Teknik Eğitim Tasarım Yöneticisi",
    "ENGINEERING_DESIGN": "Mühendislik Eğitim Tasarım Yöneticisi",
}
MANAGERS = set(ROLES) - {"EMPLOYEE"}
FIXED_LOCAL_PASSWORD = "1234"
_attempts = {}


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


def create_user(db, username, password, role, display_name):
    if role not in ROLES:
        raise ValueError("Unknown role")
    salt = secrets.token_hex(16)
    user = PortalUser(username=username.strip().lower(), display_name=display_name, role=role,
                      password_salt=salt, password_hash=password_digest(FIXED_LOCAL_PASSWORD, salt))
    db.add(user)
    db.flush()
    return user


def ensure_admin_credentials():
    with SessionLocal() as db:
        credentials_changed = False
        for username, role in (("calisan", "EMPLOYEE"), ("ihtiyac_admin", "NEEDS_ANALYST"),
                               ("teknik_admin", "TECHNICAL_DESIGN"), ("muhendislik_admin", "ENGINEERING_DESIGN")):
            if db.scalar(select(PortalUser.id).where(PortalUser.username == username)) is None:
                create_user(db, username, FIXED_LOCAL_PASSWORD, role, ROLES[role])
                credentials_changed = True

        for user in db.scalars(select(PortalUser)):
            expected = password_digest(FIXED_LOCAL_PASSWORD, user.password_salt)
            if not hmac.compare_digest(expected, user.password_hash):
                salt = secrets.token_hex(16)
                user.password_salt = salt
                user.password_hash = password_digest(FIXED_LOCAL_PASSWORD, salt)
                credentials_changed = True

        if credentials_changed:
            db.execute(delete(AccountSession))

        entries = [f"{ROLES[role]}\nKullanıcı adı: {username}\nParola: {FIXED_LOCAL_PASSWORD}\n"
                   for username, role in (("calisan", "EMPLOYEE"), ("ihtiyac_admin", "NEEDS_ANALYST"),
                                          ("teknik_admin", "TECHNICAL_DESIGN"),
                                          ("muhendislik_admin", "ENGINEERING_DESIGN"))]
        ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNTS_PATH.write_text(
            "YEREL TEST HESAPLARI\nAdres: http://127.0.0.1:8000/\n\n" + "\n".join(entries) +
            "\nTüm mevcut ve yeni yerel hesapların parolası 1234'tür.\n",
            encoding="utf-8",
        )
        ACCESS_PATH.write_text(
            "İHTİYAÇ ANALİZİ YÖNETİCİSİ\nKullanıcı adı: ihtiyac_admin\nParola: 1234\n",
            encoding="utf-8",
        )
        db.commit()


def same_origin(request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Bu kaynaktan işlem yapılamaz.")


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    display_name: str
    role: str
    delegation: dict | None = None

    @property
    def token_hash(self):
        # Account ownership does not depend on browser/session token rotation.
        return f"user:{self.delegation['delegator_id'] if self.delegation else self.user_id}"


def current_account(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    if not token:
        return None
    session = db.get(AccountSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at <= utc_now():
        return None
    user = db.get(PortalUser, session.user_id)
    if not user or not user.active or user.role not in ROLES:
        return None
    return Principal(user.id, user.username, user.display_name, user.role)


def owner_session(request: Request, account=Depends(current_account), db: Session = Depends(get_db)):
    if account is None:
        raise HTTPException(401, "Devam etmek için giriş yapın.")
    header = request.headers.get('X-Delegation-ID')
    if header:
        import re
        match = re.fullmatch(r'/api/(?:admin/)?requests/(\d+)(?:/(actions|status|refer|decisions|review-and-advance|analysis))?', request.url.path)
        if not header.isdecimal() or not match or request.method not in ('GET', 'POST', 'PATCH'):
            raise HTTPException(403, 'Vekâlet yalnızca ilgili talebin işlemlerinde kullanılabilir.')
        from .operations import acting_principal
        return acting_principal(db, account, int(header), int(match[1]))
    return account


def is_admin(account):
    return bool(account and account.role in MANAGERS)


def require_admin(account=Depends(owner_session)):
    if not is_admin(account):
        raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekiyor.")
    return account


def require_analyst(account=Depends(owner_session)):
    if account.role != "NEEDS_ANALYST":
        raise HTTPException(403, "Bu işlem ihtiyaç analizi yöneticisine aittir.")
    return account


def require_employee(account=Depends(owner_session)):
    if account.role != "EMPLOYEE":
        raise HTTPException(403, "Talep oluşturma ve kişisel takip çalışan hesabına aittir.")
    return account


def account_payload(account):
    return {"authenticated": account is not None, "is_admin": is_admin(account), "identity_mode": "named_account",
            "user": {"id": account.user_id, "username": account.username, "display_name": account.display_name,
                     "role": account.role, "role_label": ROLES[account.role]} if account else None}


def logout(request, response, db):
    token = request.cookies.get(COOKIE, "")
    if token:
        db.execute(delete(AccountSession).where(AccountSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    response.delete_cookie(COOKIE, httponly=True, samesite="strict")
    return account_payload(None)


def login(request, response, username, password, db):
    same_origin(request)
    name = username.strip().lower()
    peer = request.client.host if request.client else "local"
    keys = ("user:" + name, "peer:" + peer)
    now = time.monotonic()
    for key, limit in zip(keys, (5, 30)):
        _attempts[key] = [stamp for stamp in _attempts.get(key, []) if now - stamp < 300]
        if len(_attempts[key]) >= limit:
            raise HTTPException(429, "Çok fazla giriş denemesi. Beş dakika sonra tekrar deneyin.")
    user = db.scalar(select(PortalUser).where(PortalUser.username == name))
    salt = user.password_salt if user else "0" * 32
    digest = password_digest(password, salt)
    if not user or not user.active or user.role not in ROLES or not hmac.compare_digest(digest, user.password_hash):
        for key in keys:
            _attempts[key].append(now)
        raise HTTPException(401, "Kullanıcı adı veya parola hatalı.")
    _attempts.pop(keys[0], None)
    logout(request, response, db)
    token = secrets.token_urlsafe(32)
    db.add(AccountSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                          expires_at=utc_now() + timedelta(hours=8)))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=8 * 3600)
    return account_payload(Principal(user.id, user.username, user.display_name, user.role))
