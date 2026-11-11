from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("site_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    code: Mapped[str] = mapped_column(String(40))


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("block_id", "floor_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id"))
    floor_no: Mapped[int] = mapped_column(Integer)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("floor_id", "unit_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"))
    unit_no: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(default=True)


class Location(Base):
    __tablename__ = "test_locations"
    __table_args__ = (UniqueConstraint("unit_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)


class RoomTemplate(Base):
    __tablename__ = "room_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class RoomTemplateItem(Base):
    __tablename__ = "room_template_items"
    __table_args__ = (UniqueConstraint("template_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("room_templates.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(default=0)


class Telco(Base):
    __tablename__ = "telcos"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(default=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('ADMIN','MANAGER','AUDITOR')", name="user_role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSiteAccess(Base):
    __tablename__ = "user_site_access"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), primary_key=True)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginLimit(Base):
    __tablename__ = "login_limits"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Audit(Base):
    __tablename__ = "audits"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ACTIVE','COMPLETED','CLOSED')", name="audit_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_snapshot: Mapped[dict] = mapped_column(Json, default=dict)
    closure_note: Mapped[str | None] = mapped_column(Text)


class AuditTarget(Base):
    __tablename__ = "audit_targets"
    __table_args__ = (
        UniqueConstraint("audit_id", "location_id", "telco_id"),
        UniqueConstraint("audit_id", "id"),
        Index("ix_targets_audit", "audit_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("test_locations.id"))
    telco_id: Mapped[int] = mapped_column(ForeignKey("telcos.id"))
    # Immutable location labels at activation. Live room edits must not rewrite audit history.
    location_snapshot: Mapped[dict] = mapped_column(Json, default=dict)


class AuditAssignment(Base):
    __tablename__ = "audit_assignments"
    __table_args__ = (UniqueConstraint("audit_id", "id"), UniqueConstraint("audit_id", "user_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class AssignmentTarget(Base):
    __tablename__ = "assignment_targets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["audit_id", "assignment_id"], ["audit_assignments.audit_id", "audit_assignments.id"]
        ),
        ForeignKeyConstraint(["audit_id", "target_id"], ["audit_targets.audit_id", "audit_targets.id"]),
    )
    assignment_id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[int] = mapped_column(primary_key=True)


class Inspection(Base):
    __tablename__ = "inspection_records"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('TESTED','NO_SIGNAL','NO_INTERNET','SPEEDTEST_FAILED','SKIPPED')",
            name="inspection_outcome",
        ),
        CheckConstraint("network_type IN ('4G','4G+','5G','UNKNOWN')", name="inspection_network"),
        Index("ix_inspection_target_time", "target_id", "received_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("audit_targets.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(30))
    network_type: Mapped[str] = mapped_column(String(10))
    mobile_data_confirmed: Mapped[bool] = mapped_column(Boolean)
    device_label: Mapped[str] = mapped_column(String(200), default="")
    remarks: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(30), default="browser")
    payload_hash: Mapped[str] = mapped_column(String(64))


class SpeedMeasurement(Base):
    __tablename__ = "speed_measurements"
    __table_args__ = (
        CheckConstraint("download_mbps >= 0 AND upload_mbps >= 0 AND ping_ms >= 0", name="speed_nonnegative"),
        CheckConstraint("jitter_ms IS NULL OR jitter_ms >= 0", name="jitter_nonnegative"),
        CheckConstraint("duration_ms > 0", name="duration_positive"),
    )
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspection_records.id"), primary_key=True)
    download_mbps: Mapped[float] = mapped_column(Float)
    upload_mbps: Mapped[float] = mapped_column(Float)
    ping_ms: Mapped[float] = mapped_column(Float)
    jitter_ms: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(40))
    engine_version: Mapped[str] = mapped_column(String(40))
    profile_version: Mapped[str] = mapped_column(String(40))
    raw_summary: Mapped[dict] = mapped_column(Json, default=dict)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(Json)
