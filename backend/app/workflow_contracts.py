from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.contracts import Username

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Ids = Annotated[list[int], Field(min_length=1, max_length=5000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Named(Strict):
    name: Label
    active: bool = True


class SiteInput(Named):
    code: Code


class BlockInput(Strict):
    site_id: int = Field(gt=0)
    code: Code


class FloorInput(Strict):
    block_id: int = Field(gt=0)
    floor_no: int = Field(ge=-20, le=200)


class LocationInput(Strict):
    code: Code
    name: Label
    sort_order: int = Field(default=0, ge=0, le=10000)
    active: bool = True


class UnitInput(Strict):
    floor_id: int = Field(gt=0)
    unit_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    locations: list[LocationInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_codes(self):
        if len({item.code for item in self.locations}) != len(self.locations):
            raise ValueError("Room codes must be unique within a unit")
        return self


class UnitPatch(Strict):
    unit_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = (
        None
    )
    active: bool | None = None


class UnitImport(Strict):
    units: list[UnitInput] = Field(min_length=1, max_length=500)


class TemplateInput(Strict):
    name: Label
    items: list[LocationInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_codes(self):
        if len({item.code for item in self.items}) != len(self.items):
            raise ValueError("Template room codes must be unique")
        if not all(item.active for item in self.items):
            raise ValueError("Template items must be active")
        return self


class ApplyTemplate(Strict):
    unit_ids: Ids


class UserCreate(Strict):
    username: Username
    full_name: Label
    password: str = Field(min_length=14, max_length=256)
    role: Literal["ADMIN", "MANAGER", "AUDITOR"]
    site_ids: list[int] = Field(default_factory=list, max_length=100)


class UserPatch(Strict):
    full_name: Label | None = None
    role: Literal["ADMIN", "MANAGER", "AUDITOR"] | None = None
    active: bool | None = None
    site_ids: list[int] | None = Field(default=None, max_length=100)


class AuditConfig(Strict):
    profile_version: Code = "mobile-v1"
    timeout_seconds: int = Field(default=60, ge=10, le=120)
    weak_download_mbps: float = Field(default=10, ge=0, le=10000, allow_inf_nan=False)
    weak_upload_mbps: float = Field(default=2, ge=0, le=10000, allow_inf_nan=False)
    high_ping_ms: float = Field(default=100, ge=0, le=100000, allow_inf_nan=False)


class AuditCreate(Strict):
    title: Label
    site_ids: Annotated[list[int], Field(min_length=1, max_length=100)]
    config: AuditConfig = Field(default_factory=AuditConfig)


class AuditPatch(Strict):
    title: Label | None = None
    config: AuditConfig | None = None


class TargetSelection(Strict):
    unit_ids: list[int] = Field(default_factory=list, max_length=1000)
    location_ids: list[int] = Field(default_factory=list, max_length=5000)
    telco_ids: Annotated[list[int], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def has_locations(self):
        if not self.unit_ids and not self.location_ids:
            raise ValueError("Select at least one unit or room")
        return self


class AssignTargets(Strict):
    user_id: int = Field(gt=0)
    target_ids: list[int] = Field(max_length=5000)


class AuditReason(Strict):
    reason: str = Field(default="", max_length=4000)


class AuditView(Strict):
    id: int
    title: str
    status: Literal["DRAFT", "ACTIVE", "COMPLETED", "CLOSED"]
    created_at: datetime
    activated_at: datetime | None
    closed_at: datetime | None
    config_snapshot: dict
    closure_note: str | None


class TargetView(Strict):
    id: int
    audit_id: int
    location_id: int
    telco_id: int
    snapshot: dict
    assigned_to_me: bool
    assigned_user_ids: list[int]


class ProgressView(Strict):
    total: int
    inspected: int
    pending: int
    tested: int
    no_signal: int
    no_internet: int
    skipped_attempts: int
    failed_attempts: int
    completion_percent: float
    speedtest_success_percent: float | None
    policy: str
