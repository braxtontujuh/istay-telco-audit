import hashlib
import json
from datetime import timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.audits import assignment_target_ids, audit_access, event, progress_for, visible_targets
from app.buildings import get_or_404, location_context
from app.contracts import InspectionPayload
from app.db import get_db
from app.models import AssignmentTarget, Audit, AuditTarget, Inspection, SpeedMeasurement, User, utcnow
from app.security import allowed_sites, consume_budget, current_user, mutation

router = APIRouter(prefix="/api/v1", tags=["Inspections"])


class BatchRequest(BaseModel):
    records: list[Any] = Field(min_length=1, max_length=20)


class SyncError(BaseModel):
    code: str
    message: str


class Ack(BaseModel):
    client_id: str | None
    status: Literal["SYNCED", "RETRY", "CONFLICT"]
    server_id: int | None = None
    error: SyncError | None = None


class BatchResponse(BaseModel):
    results: list[Ack]


def payload_hash(payload):
    normalized = payload.model_copy(update={"observed_at": payload.observed_at.astimezone(timezone.utc)})
    serialized = json.dumps(
        normalized.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def expected_workspace(expected, user_id):
    # This assertion prevents a stale tab sending an old user's outbox with a new user's cookie.
    # Identity/authorization ALWAYS come from the HttpOnly server session, never this header.
    if expected != str(user_id):
        raise HTTPException(409, "WORKSPACE_ACCOUNT_CHANGED")


def accept_record(db, payload, user_id):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.active:
        raise HTTPException(403, "ACCOUNT_ACCESS_REVOKED")
    target = get_or_404(db, AuditTarget, payload.target_id)
    audit = db.scalar(select(Audit).where(Audit.id == target.audit_id).with_for_update())
    site = location_context(db, target.location_id)[4]
    if not site.active or site.id not in allowed_sites(db, user):
        raise HTTPException(403, "SITE_ACCESS_REVOKED")
    assigned = db.scalar(
        assignment_target_ids(db, user_id, audit.id).where(AssignmentTarget.target_id == target.id)
    )
    if assigned is None:
        raise HTTPException(403, "ASSIGNMENT_REVOKED")
    hashed = payload_hash(payload)
    previous = db.scalar(select(Inspection).where(Inspection.client_id == payload.client_id))
    if previous is not None:
        if previous.user_id != user_id or previous.payload_hash != hashed:
            raise HTTPException(409, "UUID_PAYLOAD_CONFLICT")
        # A duplicate acknowledgment does not alter a closed audit.
        return previous.id
    if audit.status not in ("ACTIVE", "COMPLETED"):
        raise HTTPException(409, "AUDIT_CLOSED_OR_NOT_ACTIVE")
    if payload.measurement and payload.measurement.profile_version != audit.config_snapshot.get(
        "profile_version"
    ):
        raise HTTPException(422, "MEASUREMENT_PROFILE_MISMATCH")
    record = Inspection(
        **payload.model_dump(exclude={"measurement"}),
        user_id=user_id,
        payload_hash=hashed,
        source="browser",
        received_at=utcnow(),
    )
    db.add(record)
    db.flush()
    if payload.measurement is not None:
        db.add(SpeedMeasurement(inspection_id=record.id, **payload.measurement.model_dump()))
    skew = abs((record.received_at - payload.observed_at.astimezone(timezone.utc)).total_seconds())
    event(
        db,
        audit,
        user,
        "INSPECTION_ACCEPTED",
        {
            "client_id": str(payload.client_id),
            "target_id": target.id,
            "outcome": payload.outcome.value,
            "clock_skew_flag": skew > 900,
        },
    )
    db.flush()
    ids = list(db.scalars(select(AuditTarget.id).where(AuditTarget.audit_id == audit.id)))
    if audit.status == "ACTIVE" and progress_for(db, ids)["pending"] == 0:
        audit.status = "COMPLETED"
        event(db, audit, user, "COMPLETED")
    db.commit()  # PostgreSQL deferred measurement invariant is enforced here.
    return record.id


def save_with_retry(db_bind, payload, user_id):
    with Session(db_bind, expire_on_commit=False) as transaction:
        try:
            return accept_record(transaction, payload, user_id)
        except IntegrityError:
            transaction.rollback()
            # Different accounts/audits can race on the globally unique UUID.
            existing = transaction.scalar(select(Inspection).where(Inspection.client_id == payload.client_id))
            if existing and existing.user_id == user_id and existing.payload_hash == payload_hash(payload):
                return existing.id
            raise HTTPException(409, "UUID_OR_RECORD_CONFLICT")


@router.post("/inspections", response_model=Ack)
def inspect(
    payload: InspectionPayload,
    user: User = Depends(mutation),
    db: Session = Depends(get_db),
    x_workspace_user: str | None = Header(default=None),
):
    user_id = user.id
    expected_workspace(x_workspace_user, user_id)
    consume_budget(db, f"sync:{user_id}", 120, 60, "SYNC_RATE_LIMIT")
    bind = db.get_bind()
    db.rollback()
    server_id = save_with_retry(bind, payload, user_id)
    return Ack(client_id=str(payload.client_id), status="SYNCED", server_id=server_id)


@router.post("/inspections/batch-sync", response_model=BatchResponse)
def batch(
    payload: BatchRequest,
    user: User = Depends(mutation),
    db: Session = Depends(get_db),
    x_workspace_user: str | None = Header(default=None),
):
    user_id = user.id
    expected_workspace(x_workspace_user, user_id)
    consume_budget(db, f"sync:{user_id}", 120, 60, "SYNC_RATE_LIMIT", len(payload.records))
    bind = db.get_bind()
    db.rollback()
    results = []
    for raw in payload.records:
        client_id = (
            str(raw.get("client_id"))[:100] if isinstance(raw, dict) and raw.get("client_id") else None
        )
        try:
            item = InspectionPayload.model_validate(raw)
            server_id = save_with_retry(bind, item, user_id)
            results.append(Ack(client_id=str(item.client_id), status="SYNCED", server_id=server_id))
        except ValidationError:
            results.append(
                Ack(
                    client_id=client_id,
                    status="CONFLICT",
                    error=SyncError(code="INVALID_PAYLOAD", message="Invalid inspection fields"),
                )
            )
        except HTTPException as exc:
            results.append(
                Ack(
                    client_id=client_id,
                    status="CONFLICT",
                    error=SyncError(code=str(exc.detail), message=str(exc.detail)),
                )
            )
        except SQLAlchemyError:
            results.append(
                Ack(
                    client_id=client_id,
                    status="RETRY",
                    error=SyncError(
                        code="DATABASE_RETRY", message="Temporary database failure; retry the same UUID"
                    ),
                )
            )
    return BatchResponse(results=results)


def record_view(db, record):
    observed = (
        record.observed_at.replace(tzinfo=timezone.utc)
        if record.observed_at.tzinfo is None
        else record.observed_at
    )
    received = (
        record.received_at.replace(tzinfo=timezone.utc)
        if record.received_at.tzinfo is None
        else record.received_at
    )
    measurement = db.get(SpeedMeasurement, record.id)
    metrics = (
        {
            key: getattr(measurement, key)
            for key in (
                "download_mbps",
                "upload_mbps",
                "ping_ms",
                "jitter_ms",
                "duration_ms",
                "engine",
                "engine_version",
                "profile_version",
            )
        }
        if measurement
        else None
    )
    return {
        "id": record.id,
        "client_id": str(record.client_id),
        "target_id": record.target_id,
        "user_id": record.user_id,
        "outcome": record.outcome,
        "network_type": record.network_type,
        "mobile_data_confirmed": record.mobile_data_confirmed,
        "device_label": record.device_label,
        "remarks": record.remarks,
        "observed_at": record.observed_at,
        "received_at": record.received_at,
        "clock_skew_flag": abs((received - observed).total_seconds()) > 900,
        "measurement": metrics,
    }


@router.get("/audit-targets/{target_id}/history")
def history(target_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = db.scalar(visible_targets(db, user).where(AuditTarget.id == target_id))
    if target is None:
        raise HTTPException(403, "TARGET_ACCESS_DENIED")
    audit_access(db, user, target.audit_id)
    query = select(Inspection).where(Inspection.target_id == target_id)
    if user.role == "AUDITOR":
        query = query.where(Inspection.user_id == user.id)
    return [
        record_view(db, value)
        for value in db.scalars(query.order_by(Inspection.received_at.desc(), Inspection.id.desc()))
    ]


@router.get("/inspections/mine")
def own_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = (
        select(Inspection)
        .where(
            Inspection.user_id == user.id,
            Inspection.target_id.in_(visible_targets(db, user).with_only_columns(AuditTarget.id)),
        )
        .order_by(Inspection.received_at.desc(), Inspection.id.desc())
        .limit(500)
    )
    return [record_view(db, value) for value in db.scalars(query)]
