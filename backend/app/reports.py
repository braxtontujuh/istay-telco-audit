"""Scoped reports use frozen labels and latest accepted conclusive outcomes."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audits import CONCLUSIVE, POLICY, audit_access, list_audits, progress_for, visible_targets
from app.buildings import manager
from app.db import get_db
from app.models import AuditTarget, Inspection, SpeedMeasurement, User, utcnow
from app.security import current_user

router = APIRouter(prefix="/api/v1", tags=["Reports"])
BIAS = "Speed averages include successful tests only; review sample counts, pending targets and issue rates. No signal/internet is never 0 Mbps."


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def count_rows(rows):
    counts = Counter(row["outcome"] for row in rows)
    inspected = sum(counts[key] for key in CONCLUSIVE)
    total = len(rows)
    return {
        "total": total,
        "inspected": inspected,
        "pending": total - inspected,
        "tested": counts["TESTED"],
        "no_signal": counts["NO_SIGNAL"],
        "no_internet": counts["NO_INTERNET"],
        "completion_percent": round(100 * inspected / total, 2) if total else 0,
        "speedtest_success_percent": round(100 * counts["TESTED"] / inspected, 2) if inspected else None,
        "issue_percent_of_inspected": round(
            100 * (counts["NO_SIGNAL"] + counts["NO_INTERNET"]) / inspected, 2
        )
        if inspected
        else None,
    }


def report(db, user, audit_id, site_id=None, telco_id=None, floor_id=None):
    manager(user)
    audit = audit_access(db, user, audit_id)
    targets = list(db.scalars(visible_targets(db, user, audit_id)))
    filters = {"site_id": site_id, "telco_id": telco_id, "floor_id": floor_id}
    targets = [
        target
        for target in targets
        if all(value is None or target.location_snapshot.get(key) == value for key, value in filters.items())
    ]
    ids = [target.id for target in targets]
    records = list(
        db.scalars(
            select(Inspection)
            .where(Inspection.target_id.in_(ids))
            .order_by(Inspection.received_at, Inspection.id)
            .limit(50001)
        )
    )
    if len(records) > 50000:
        raise HTTPException(413, "REPORT_TOO_LARGE_NARROW_FILTERS")
    measurements = {
        value.inspection_id: value
        for value in db.scalars(
            select(SpeedMeasurement).where(
                SpeedMeasurement.inspection_id.in_([record.id for record in records])
            )
        )
    }
    latest = {}
    attempts = []
    by_target = {target.id: target for target in targets}
    for record in records:
        measurement = measurements.get(record.id)
        row = {
            "inspection_id": record.id,
            "client_id": str(record.client_id),
            "target_id": record.target_id,
            **by_target[record.target_id].location_snapshot,
            "outcome": record.outcome,
            "user_id": record.user_id,
            "network_type": record.network_type,
            "mobile_data_confirmed": record.mobile_data_confirmed,
            "device_label": record.device_label,
            "remarks": record.remarks,
            "observed_at": utc(record.observed_at),
            "received_at": utc(record.received_at),
            "clock_skew_flag": abs((utc(record.received_at) - utc(record.observed_at)).total_seconds()) > 900,
            **{
                key: getattr(measurement, key) if measurement else None
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
            },
        }
        attempts.append(row)
        if record.outcome in CONCLUSIVE:
            latest[record.target_id] = row
    rows = [
        latest.get(target.id, {"target_id": target.id, **target.location_snapshot, "outcome": "PENDING"})
        for target in targets
    ]
    summary = count_rows(rows) | {
        "skipped_attempts": sum(row["outcome"] == "SKIPPED" for row in attempts),
        "failed_attempts": sum(row["outcome"] == "SPEEDTEST_FAILED" for row in attempts),
        "attempt_count": len(attempts),
    }
    telcos, floors = defaultdict(list), defaultdict(list)
    weak = []
    config = audit.config_snapshot
    for row in rows:
        telcos[(row.get("telco_id"), row.get("telco"))].append(row)
        floors[(row.get("site"), row.get("block"), row.get("floor"), row.get("floor_id"))].append(row)
        reasons = []
        if row["outcome"] in ("NO_SIGNAL", "NO_INTERNET"):
            reasons.append(row["outcome"])
        if row["outcome"] == "TESTED":
            if row["download_mbps"] < config.get("weak_download_mbps", 10):
                reasons.append("LOW_DOWNLOAD")
            if row["upload_mbps"] < config.get("weak_upload_mbps", 2):
                reasons.append("LOW_UPLOAD")
            if row["ping_ms"] > config.get("high_ping_ms", 100):
                reasons.append("HIGH_PING")
        if reasons:
            weak.append(row | {"weak_reasons": reasons})
    comparison = []
    for (id, name), values in telcos.items():
        tested = [row for row in values if row["outcome"] == "TESTED"]
        dates = [row["received_at"] for row in values if row.get("received_at")]
        comparison.append(
            {
                "telco_id": id,
                "telco": name,
                **count_rows(values),
                "sample_count": len(tested),
                "first_received_at": min(dates) if dates else None,
                "last_received_at": max(dates) if dates else None,
                **{
                    f"avg_{key}": round(sum(row[key] for row in tested) / len(tested), 3) if tested else None
                    for key in ("download_mbps", "upload_mbps", "ping_ms")
                },
            }
        )
    weak_ids = {value["target_id"] for value in weak}
    coverage = [
        {
            "site": site,
            "block": block,
            "floor": floor,
            "floor_id": id,
            **count_rows(values),
            "weak_targets": sum(row["target_id"] in weak_ids for row in values),
        }
        for (site, block, floor, id), values in floors.items()
    ]
    return {
        "audit_id": audit.id,
        "title": audit.title,
        "status": audit.status,
        "generated_at": utcnow(),
        "policy": POLICY,
        "averages_warning": BIAS,
        "config_snapshot": config,
        "filters": filters,
        "summary": summary,
        "telco_comparison": comparison,
        "coverage": coverage,
        "latest_results": rows,
        "weak_locations": weak,
        "all_attempts": list(reversed(attempts)),
    }


def filters(
    site_id: int | None = Query(None, gt=0),
    telco_id: int | None = Query(None, gt=0),
    floor_id: int | None = Query(None, gt=0),
):
    return {"site_id": site_id, "telco_id": telco_id, "floor_id": floor_id}


@router.get("/audits/{audit_id}/results")
def results(
    audit_id: int,
    scope: dict = Depends(filters),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return report(db, user, audit_id, **scope)


@router.get("/audits/{audit_id}/coverage")
def coverage(
    audit_id: int,
    scope: dict = Depends(filters),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = report(db, user, audit_id, **scope)
    return {key: data[key] for key in ("audit_id", "policy", "summary", "coverage", "filters")}


@router.get("/audits/{audit_id}/weak-locations")
def weak_locations(
    audit_id: int,
    scope: dict = Depends(filters),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = report(db, user, audit_id, **scope)
    return {key: data[key] for key in ("audit_id", "config_snapshot", "weak_locations", "filters")}


@router.get("/dashboard/summary")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    manager(user)
    audits = [audit for audit in list_audits(user, db) if audit.status != "DRAFT"]
    ids = [audit.id for audit in audits]
    target_ids = list(
        db.scalars(
            visible_targets(db, user).where(AuditTarget.audit_id.in_(ids)).with_only_columns(AuditTarget.id)
        )
    )
    return {
        "audit_count": len(audits),
        "summary": progress_for(db, target_ids),
        "generated_at": utcnow(),
        "policy": POLICY,
        "scope_note": "Totals count audit targets across all accessible non-draft audits; repeated audits count separately. Device-only drafts are not known to the server.",
    }


def workbook(data):
    book = Workbook(write_only=True)

    def sheet(name, rows, columns):
        ws = book.create_sheet(name)
        ws.freeze_panes = "A2"
        ws.append(columns)
        for row in rows:
            cells = []
            for key in columns:
                value = row.get(key)
                if isinstance(value, datetime):
                    value = value.isoformat()
                if isinstance(value, str):
                    # Explicit strings prevent formula injection, including =/+/−/@ prefixes.
                    cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", value))
                    cell.data_type = "s"
                    cells.append(cell)
                else:
                    cells.append(value)
            ws.append(cells)

    summary = {
        key: data[key]
        for key in ("audit_id", "title", "status", "generated_at", "policy", "averages_warning")
    }
    summary.update(data["summary"])
    summary.update({f"config_{key}": value for key, value in data["config_snapshot"].items()})
    summary.update({f"filter_{key}": value for key, value in data["filters"].items()})
    sheet(
        "Summary",
        [
            {"field": key, "value": str(value) if isinstance(value, (list, dict)) else value}
            for key, value in summary.items()
        ],
        ["field", "value"],
    )
    sheet(
        "Telco Comparison",
        data["telco_comparison"],
        [
            "telco",
            "total",
            "inspected",
            "pending",
            "tested",
            "no_signal",
            "no_internet",
            "sample_count",
            "issue_percent_of_inspected",
            "avg_download_mbps",
            "avg_upload_mbps",
            "avg_ping_ms",
            "first_received_at",
            "last_received_at",
        ],
    )
    columns = [
        "target_id",
        "site",
        "block",
        "floor",
        "unit",
        "room",
        "telco",
        "outcome",
        "inspection_id",
        "user_id",
        "network_type",
        "mobile_data_confirmed",
        "device_label",
        "download_mbps",
        "upload_mbps",
        "ping_ms",
        "jitter_ms",
        "duration_ms",
        "observed_at",
        "received_at",
        "clock_skew_flag",
        "engine",
        "engine_version",
        "profile_version",
        "remarks",
        "client_id",
    ]
    sheet("Latest Results", data["latest_results"], columns)
    sheet(
        "No Signal-No Internet",
        [row for row in data["latest_results"] if row["outcome"] in ("NO_SIGNAL", "NO_INTERNET")],
        columns,
    )
    sheet("Pending Targets", [row for row in data["latest_results"] if row["outcome"] == "PENDING"], columns)
    sheet("All Attempts", data["all_attempts"], columns)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


@router.get("/audits/{audit_id}/export.xlsx")
def export(
    audit_id: int,
    scope: dict = Depends(filters),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = report(db, user, audit_id, **scope)
    return Response(
        workbook(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="istay-audit-{audit_id}.xlsx"'},
    )
