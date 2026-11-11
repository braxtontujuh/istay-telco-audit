from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.buildings import get_or_404, location_context, manager, validate_site_ids
from app.db import get_db
from app.models import (
    AssignmentTarget,
    Audit,
    AuditAssignment,
    AuditEvent,
    AuditTarget,
    Block,
    Floor,
    Inspection,
    Location,
    Telco,
    Unit,
    User,
    utcnow,
)
from app.security import allowed_sites, current_user, mutation, require_site
from app.workflow_contracts import (
    AssignTargets,
    AuditCreate,
    AuditPatch,
    AuditReason,
    AuditView,
    ProgressView,
    TargetSelection,
    TargetView,
)

router = APIRouter(prefix="/api/v1", tags=["Audits"])
CONCLUSIVE = ("TESTED", "NO_SIGNAL", "NO_INTERNET")
POLICY = "Latest accepted conclusive inspection per target; failed/skipped retries do not erase it."


def assignment_target_ids(db, user_id, audit_id=None):
    query = (
        select(AssignmentTarget.target_id)
        .join(AuditAssignment, AuditAssignment.id == AssignmentTarget.assignment_id)
        .where(AuditAssignment.user_id == user_id)
    )
    if audit_id is not None:
        query = query.where(AssignmentTarget.audit_id == audit_id)
    return query


def visible_targets(db, user, audit_id=None):
    query = (
        select(AuditTarget)
        .join(Location, Location.id == AuditTarget.location_id)
        .join(Unit, Unit.id == Location.unit_id)
        .join(Floor, Floor.id == Unit.floor_id)
        .join(Block, Block.id == Floor.block_id)
        .where(Block.site_id.in_(allowed_sites(db, user)))
    )
    if audit_id is not None:
        query = query.where(AuditTarget.audit_id == audit_id)
    if user.role == "AUDITOR":
        query = query.where(AuditTarget.id.in_(assignment_target_ids(db, user.id, audit_id)))
    return query.order_by(AuditTarget.id)


def audit_access(db, user, audit_id, lock=False):
    query = select(Audit).where(Audit.id == audit_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    audit = db.scalar(query)
    if audit is None:
        raise HTTPException(404, "AUDIT_NOT_FOUND")
    if user.role != "ADMIN":
        permitted = set(allowed_sites(db, user))
        if user.role == "MANAGER":
            sites = set(audit.config_snapshot.get("site_ids", []))
            if not sites or not sites <= permitted:
                raise HTTPException(403, "SITE_ACCESS_DENIED")
        elif audit.status == "DRAFT" or db.scalar(visible_targets(db, user, audit_id).limit(1)) is None:
            raise HTTPException(403, "ASSIGNMENT_REQUIRED")
    return audit


def event(db, audit, user, action, details=None):
    db.add(AuditEvent(audit_id=audit.id, actor_id=user.id, action=action, details=details or {}))


def snapshot(db, target):
    location, unit, floor, block, site = location_context(db, target.location_id)
    telco = get_or_404(db, Telco, target.telco_id)
    if not all((location.active, unit.active, site.active, telco.active)):
        raise HTTPException(409, "INACTIVE_TARGET_CONFIGURATION")
    return {
        "site_id": site.id,
        "site": site.code,
        "block_id": block.id,
        "block": block.code,
        "floor_id": floor.id,
        "floor": floor.floor_no,
        "unit_id": unit.id,
        "unit": unit.unit_no,
        "location_id": location.id,
        "room_code": location.code,
        "room": location.name,
        "telco_id": telco.id,
        "telco": telco.name,
    }


def latest_conclusive(db, target_ids):
    if not target_ids:
        return {}
    ranked = (
        select(
            Inspection.id,
            Inspection.target_id,
            Inspection.outcome,
            Inspection.received_at,
            func.row_number()
            .over(
                partition_by=Inspection.target_id,
                order_by=(Inspection.received_at.desc(), Inspection.id.desc()),
            )
            .label("position"),
        )
        .where(Inspection.target_id.in_(target_ids), Inspection.outcome.in_(CONCLUSIVE))
        .subquery()
    )
    return {
        value["target_id"]: dict(value)
        for value in db.execute(select(ranked).where(ranked.c.position == 1)).mappings()
    }


def progress_for(db, target_ids):
    latest = latest_conclusive(db, target_ids)
    counts = Counter(value["outcome"] for value in latest.values())
    attempts = dict(
        db.execute(
            select(Inspection.outcome, func.count())
            .where(
                Inspection.target_id.in_(target_ids), Inspection.outcome.in_(("SKIPPED", "SPEEDTEST_FAILED"))
            )
            .group_by(Inspection.outcome)
        ).all()
    )
    total, inspected = len(target_ids), len(latest)
    return {
        "total": total,
        "inspected": inspected,
        "pending": total - inspected,
        "tested": counts["TESTED"],
        "no_signal": counts["NO_SIGNAL"],
        "no_internet": counts["NO_INTERNET"],
        "skipped_attempts": attempts.get("SKIPPED", 0),
        "failed_attempts": attempts.get("SPEEDTEST_FAILED", 0),
        "completion_percent": round(100 * inspected / total, 2) if total else 0,
        "speedtest_success_percent": round(100 * counts["TESTED"] / inspected, 2) if inspected else None,
        "policy": POLICY,
    }


def target_view(db, user, target):
    assigned = list(
        db.scalars(
            select(AuditAssignment.user_id)
            .join(AssignmentTarget, AuditAssignment.id == AssignmentTarget.assignment_id)
            .where(AssignmentTarget.target_id == target.id)
        )
    )
    return {
        "id": target.id,
        "audit_id": target.audit_id,
        "location_id": target.location_id,
        "telco_id": target.telco_id,
        "snapshot": target.location_snapshot,
        "assigned_to_me": user.id in assigned,
        "assigned_user_ids": assigned if user.role != "AUDITOR" else [user.id],
    }


@router.post("/audits", response_model=AuditView, status_code=201)
def create_audit(payload: AuditCreate, user: User = Depends(mutation), db: Session = Depends(get_db)):
    manager(user)
    validate_site_ids(db, payload.site_ids)
    if not set(payload.site_ids) <= set(allowed_sites(db, user)):
        raise HTTPException(403, "SITE_ACCESS_DENIED")
    audit = Audit(
        title=payload.title,
        created_by=user.id,
        config_snapshot=payload.config.model_dump() | {"site_ids": sorted(set(payload.site_ids))},
    )
    db.add(audit)
    db.flush()
    event(db, audit, user, "CREATED")
    db.commit()
    return audit


@router.get("/audits", response_model=list[AuditView])
def list_audits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    audits = list(db.scalars(select(Audit).order_by(Audit.created_at.desc(), Audit.id.desc())))
    result = []
    for audit in audits:
        try:
            audit_access(db, user, audit.id)
            result.append(audit)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    return result


@router.get("/audits/{audit_id}", response_model=AuditView)
def get_audit(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return audit_access(db, user, audit_id)


@router.patch("/audits/{audit_id}", response_model=AuditView)
def patch_audit(
    audit_id: int, payload: AuditPatch, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status != "DRAFT":
        raise HTTPException(409, "AUDIT_CONFIG_FROZEN")
    if any(value is None for value in payload.model_dump(exclude_unset=True).values()):
        raise HTTPException(422, "NULL_NOT_ALLOWED")
    if payload.title is not None:
        audit.title = payload.title
    if payload.config is not None:
        audit.config_snapshot = payload.config.model_dump() | {"site_ids": audit.config_snapshot["site_ids"]}
    event(db, audit, user, "DRAFT_UPDATED")
    db.commit()
    return audit


@router.post("/audits/{audit_id}/targets", response_model=list[TargetView], status_code=201)
def add_targets(
    audit_id: int, payload: TargetSelection, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status != "DRAFT":
        raise HTTPException(409, "TARGET_LIST_FROZEN")
    units = set(payload.unit_ids)
    if units != set(db.scalars(select(Unit.id).where(Unit.id.in_(units), Unit.active.is_(True)))):
        raise HTTPException(422, "INVALID_UNIT_IDS")
    for unit_id in units:
        # A unit must be inside the audit's declared scope even if its room list is empty.
        unit = get_or_404(db, Unit, unit_id)
        floor = get_or_404(db, Floor, unit.floor_id)
        if get_or_404(db, Block, floor.block_id).site_id not in audit.config_snapshot["site_ids"]:
            raise HTTPException(403, "TARGET_OUTSIDE_AUDIT_SCOPE")
    locations = list(
        db.scalars(
            select(Location).where(
                or_(Location.unit_id.in_(units), Location.id.in_(payload.location_ids)),
                Location.active.is_(True),
            )
        )
    )
    if not set(payload.location_ids) <= {value.id for value in locations}:
        raise HTTPException(422, "INVALID_LOCATION_IDS")
    telcos = set(payload.telco_ids)
    if telcos != set(db.scalars(select(Telco.id).where(Telco.id.in_(telcos), Telco.active.is_(True)))):
        raise HTTPException(422, "INVALID_TELCO_IDS")
    existing = {
        (value.location_id, value.telco_id)
        for value in db.scalars(select(AuditTarget).where(AuditTarget.audit_id == audit_id))
    }
    wanted = {(value.id, telco_id) for value in locations for telco_id in telcos}
    if not wanted or len(existing | wanted) > 5000:
        raise HTTPException(422, "TARGET_LIMIT_OR_EMPTY_SELECTION")
    for location in locations:
        _, _, _, _, site = location_context(db, location.id)
        require_site(db, user, site.id)
        if site.id not in audit.config_snapshot["site_ids"]:
            raise HTTPException(403, "TARGET_OUTSIDE_AUDIT_SCOPE")
    for location_id, telco_id in sorted(wanted - existing):
        value = AuditTarget(audit_id=audit_id, location_id=location_id, telco_id=telco_id)
        value.location_snapshot = snapshot(db, value)
        db.add(value)
    event(db, audit, user, "TARGETS_ADDED", {"count": len(wanted - existing)})
    db.commit()
    return [target_view(db, user, value) for value in db.scalars(visible_targets(db, user, audit_id))]


@router.post("/audits/{audit_id}/assignments")
def assign(
    audit_id: int, payload: AssignTargets, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status not in ("DRAFT", "ACTIVE", "COMPLETED"):
        raise HTTPException(409, "AUDIT_CLOSED")
    employee = get_or_404(db, User, payload.user_id)
    if not employee.active:
        raise HTTPException(409, "USER_INACTIVE")
    targets = list(
        db.scalars(
            select(AuditTarget).where(
                AuditTarget.audit_id == audit_id, AuditTarget.id.in_(set(payload.target_ids))
            )
        )
    )
    if {value.id for value in targets} != set(payload.target_ids):
        raise HTTPException(422, "TARGET_AUDIT_MISMATCH")
    for target in targets:
        require_site(db, employee, location_context(db, target.location_id)[4].id)
    assignment = db.scalar(
        select(AuditAssignment).where(
            AuditAssignment.audit_id == audit_id, AuditAssignment.user_id == employee.id
        )
    )
    if assignment is None:
        assignment = AuditAssignment(audit_id=audit_id, user_id=employee.id, assigned_by=user.id)
        db.add(assignment)
        db.flush()
    db.execute(delete(AssignmentTarget).where(AssignmentTarget.assignment_id == assignment.id))
    for target in targets:
        db.add(AssignmentTarget(assignment_id=assignment.id, audit_id=audit_id, target_id=target.id))
    event(
        db,
        audit,
        user,
        "ASSIGNMENT_UPDATED",
        {"user_id": employee.id, "target_ids": sorted(set(payload.target_ids))},
    )
    db.commit()
    return {"assignment_id": assignment.id, "assigned_count": len(targets)}


@router.post("/audits/{audit_id}/activate", response_model=AuditView)
def activate(audit_id: int, user: User = Depends(mutation), db: Session = Depends(get_db)):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status != "DRAFT":
        raise HTTPException(409, "AUDIT_NOT_DRAFT")
    targets = list(db.scalars(select(AuditTarget).where(AuditTarget.audit_id == audit_id)))
    if not targets:
        raise HTTPException(409, "AUDIT_HAS_NO_TARGETS")
    valid_assigned = set()
    for employee, target_id in db.execute(
        select(User, AssignmentTarget.target_id)
        .join(AuditAssignment, AuditAssignment.user_id == User.id)
        .join(AssignmentTarget, AssignmentTarget.assignment_id == AuditAssignment.id)
        .where(AuditAssignment.audit_id == audit_id, User.active.is_(True))
    ):
        target = next(value for value in targets if value.id == target_id)
        if location_context(db, target.location_id)[4].id in allowed_sites(db, employee):
            valid_assigned.add(target_id)
    if valid_assigned != {value.id for value in targets}:
        raise HTTPException(409, "ALL_TARGETS_REQUIRE_AUTHORIZED_ASSIGNEE")
    for target in targets:
        target.location_snapshot = snapshot(db, target)
    audit.status, audit.activated_at = "ACTIVE", utcnow()
    event(db, audit, user, "ACTIVATED", {"targets": len(targets), "config": audit.config_snapshot})
    db.commit()
    return audit


@router.get("/audits/{audit_id}/targets", response_model=list[TargetView])
def targets(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit_access(db, user, audit_id)
    return [target_view(db, user, value) for value in db.scalars(visible_targets(db, user, audit_id))]


@router.get("/audit-targets/{target_id}", response_model=TargetView)
def get_target(target_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = db.scalar(visible_targets(db, user).where(AuditTarget.id == target_id))
    if target is None:
        raise HTTPException(403, "TARGET_ACCESS_DENIED")
    audit_access(db, user, target.audit_id)
    return target_view(db, user, target)


@router.get("/audits/{audit_id}/progress", response_model=ProgressView)
def progress(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit_access(db, user, audit_id)
    return progress_for(db, [value.id for value in db.scalars(visible_targets(db, user, audit_id))])


@router.post("/audits/{audit_id}/close", response_model=AuditView)
def close(audit_id: int, payload: AuditReason, user: User = Depends(mutation), db: Session = Depends(get_db)):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status not in ("ACTIVE", "COMPLETED"):
        raise HTTPException(409, "AUDIT_CANNOT_CLOSE")
    counts = progress_for(
        db, list(db.scalars(select(AuditTarget.id).where(AuditTarget.audit_id == audit_id)))
    )
    if counts["pending"] and len(payload.reason.strip()) < 3:
        raise HTTPException(422, "UNRESOLVED_CLOSURE_REQUIRES_REASON")
    audit.status, audit.closed_at, audit.closure_note = "CLOSED", utcnow(), payload.reason.strip()
    event(db, audit, user, "CLOSED", {"reason": payload.reason.strip(), "unresolved": counts["pending"]})
    db.commit()
    return audit


@router.post("/audits/{audit_id}/reopen", response_model=AuditView)
def reopen(
    audit_id: int, payload: AuditReason, user: User = Depends(mutation), db: Session = Depends(get_db)
):
    manager(user)
    audit = audit_access(db, user, audit_id, lock=True)
    if audit.status not in ("CLOSED", "COMPLETED") or len(payload.reason.strip()) < 3:
        raise HTTPException(409, "REOPEN_REQUIRES_CLOSED_OR_COMPLETED_AUDIT_AND_REASON")
    audit.status, audit.closed_at, audit.closure_note = "ACTIVE", None, None
    event(db, audit, user, "REOPENED", {"reason": payload.reason.strip()})
    db.commit()
    return audit


@router.get("/audits/{audit_id}/events")
def events(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    audit_access(db, user, audit_id)
    return [
        {
            "id": value.id,
            "actor_id": value.actor_id,
            "action": value.action,
            "details": value.details,
            "created_at": value.created_at,
        }
        for value in db.scalars(
            select(AuditEvent).where(AuditEvent.audit_id == audit_id).order_by(AuditEvent.id)
        )
    ]
