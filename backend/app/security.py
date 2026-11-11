import hashlib
import secrets
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.db import get_db
from app.models import LoginLimit, Session, Site, User, UserSiteAccess, utcnow

hasher = PasswordHasher()
# Make unknown usernames cost the same password hash verification work.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def origin_check(request: Request):
    if request.headers.get("origin") != settings().app_origin:
        raise HTTPException(403, "ORIGIN_REJECTED")


def consume_budget(db: DbSession, key_value: str, limit: int, seconds: int, code: str, weight: int = 1):
    # Persistent per-account limiter: atomic increments survive restarts and multiple workers.
    # No trust in arbitrary forwarded IP headers. Shared account limit is intentionally conservative.
    key = digest(key_value)
    now = utcnow()
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(LoginLimit).values(key_hash=key, count=0, window_start=now).on_conflict_do_nothing())
    row = db.scalar(select(LoginLimit).where(LoginLimit.key_hash == key).with_for_update())
    start = (
        row.window_start.replace(tzinfo=timezone.utc) if row.window_start.tzinfo is None else row.window_start
    )
    if now - start > timedelta(seconds=seconds):
        row.count = 0
        row.window_start = now
    row.count += weight
    limited = row.count > limit
    db.commit()
    if limited:
        raise HTTPException(429, code, headers={"Retry-After": str(seconds)})


def consume_login_attempt(db: DbSession, username: str):
    consume_budget(db, username, 10, 900, "LOGIN_RATE_LIMIT")


def current_session(request: Request, db: DbSession = Depends(get_db)):
    token = request.cookies.get("istay_session", "")
    session = db.get(Session, digest(token)) if token else None
    if not session:
        raise HTTPException(401, "LOGIN_REQUIRED")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    user = db.get(User, session.user_id)
    if expires <= utcnow() or not user or not user.active:
        raise HTTPException(401, "SESSION_EXPIRED")
    expected = request.headers.get('x-workspace-user')
    if expected is not None and expected != str(user.id):
        raise HTTPException(409, 'WORKSPACE_ACCOUNT_CHANGED')
    request.state.user = user
    return session


def current_user(request: Request, session: Session = Depends(current_session)):
    return request.state.user


def mutation(request: Request, session: Session = Depends(current_session)):
    origin_check(request)
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
        raise HTTPException(403, "CSRF_REJECTED")
    return request.state.user


def require_role(user: User, *roles: str):
    if user.role not in roles:
        raise HTTPException(403, "ROLE_DENIED")


def allowed_sites(db: DbSession, user: User):
    query = select(Site.id)
    if user.role != "ADMIN":
        query = query.join(UserSiteAccess, UserSiteAccess.site_id == Site.id).where(
            UserSiteAccess.user_id == user.id, Site.active.is_(True)
        )
    return list(db.scalars(query))


def require_site(db: DbSession, user: User, site_id: int):
    if site_id not in allowed_sites(db, user):
        raise HTTPException(403, "SITE_ACCESS_DENIED")


def revoke_sessions(db: DbSession, user_id: int):
    db.execute(delete(Session).where(Session.user_id == user_id))
