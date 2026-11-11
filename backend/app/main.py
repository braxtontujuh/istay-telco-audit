import secrets
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DbSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.audits import router as audits_router
from app.buildings import router as buildings_router
from app.config import settings
from app.contracts import ChangePassword, Login, SessionView, SiteView, UserView
from app.db import get_db
from app.inspections import router as inspections_router
from app.models import Session, Site, User, utcnow
from app.reports import router as reports_router
from app.security import (
    allowed_sites,
    consume_login_attempt,
    current_session,
    current_user,
    digest,
    dummy_hash,
    hasher,
    mutation,
    origin_check,
    revoke_sessions,
    verify_password,
)

app = FastAPI(title="I-Stay Telco Audit", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings().trusted_hosts.split(","))
app.include_router(buildings_router)
app.include_router(audits_router)
app.include_router(inspections_router)
app.include_router(reports_router)


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def error_response(request, exc):
    return JSONResponse(
        {"error": {"code": str(exc.detail), "message": str(exc.detail)}},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def invalid_response(request, exc):
    # Do not echo password or arbitrary inspection input into diagnostics.
    return JSONResponse(
        {"error": {"code": "VALIDATION_ERROR", "message": "Invalid request fields"}}, status_code=422
    )


@app.exception_handler(SQLAlchemyError)
async def database_response(request, exc):
    return JSONResponse(
        {"error": {"code": "DATABASE_UNAVAILABLE", "message": "Please retry later"}}, status_code=503
    )


@app.exception_handler(IntegrityError)
async def constraint_response(request, exc):
    return JSONResponse(
        {"error": {"code": "CONSTRAINT_CONFLICT", "message": "Duplicate or inconsistent data"}},
        status_code=409,
    )


@app.get("/api/v1/health/live")
def live():
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def ready(user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    db.execute(text("SELECT 1"))
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != "0001":
        raise HTTPException(503, "MIGRATION_REQUIRED")
    return {"status": "ready"}


@app.get("/api/v1/openapi.json")
def openapi(user: User = Depends(current_user)):
    return app.openapi()


@app.post("/api/v1/auth/login", response_model=SessionView)
def login(payload: Login, request: Request, response: Response, db: DbSession = Depends(get_db)):
    origin_check(request)
    consume_login_attempt(db, payload.username)
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = verify_password(user.password_hash if user else dummy_hash, payload.password)
    if not user or not valid or not user.active:
        raise HTTPException(401, "INVALID_CREDENTIALS")
    # Rotate an existing session to prevent session fixation.
    previous = request.cookies.get("istay_session")
    if previous:
        old_session = db.get(Session, digest(previous))
        if old_session:
            db.delete(old_session)
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.add(
        Session(
            token_hash=digest(token),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=utcnow() + timedelta(hours=settings().session_hours),
        )
    )
    db.commit()
    response.set_cookie(
        "istay_session",
        token,
        secure=settings().secure_cookies,
        httponly=True,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"user": UserView.model_validate(user), "csrf_token": csrf}


@app.get("/api/v1/auth/me", response_model=SessionView)
def me(request: Request, session: Session = Depends(current_session)):
    return {"user": UserView.model_validate(request.state.user), "csrf_token": session.csrf_token}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(
    response: Response,
    user: User = Depends(mutation),
    session: Session = Depends(current_session),
    db: DbSession = Depends(get_db),
):
    db.delete(session)
    db.commit()
    response.delete_cookie(
        "istay_session", path="/", secure=settings().secure_cookies, httponly=True, samesite="strict"
    )


@app.post("/api/v1/auth/change-password", status_code=204)
def change_password(
    payload: ChangePassword,
    response: Response,
    user: User = Depends(mutation),
    db: DbSession = Depends(get_db),
):
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(403, "INVALID_CREDENTIALS")
    user.password_hash = hasher.hash(payload.new_password)
    revoke_sessions(db, user.id)
    db.commit()
    response.delete_cookie(
        "istay_session", path="/", secure=settings().secure_cookies, httponly=True, samesite="strict"
    )


@app.get("/api/v1/sites", response_model=list[SiteView])
def sites(user: User = Depends(current_user), db: DbSession = Depends(get_db)):
    return list(db.scalars(select(Site).where(Site.id.in_(allowed_sites(db, user))).order_by(Site.code)))
