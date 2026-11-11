from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator

Username = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")]


class Login(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=256)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=14, max_length=256)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: Literal["ADMIN", "MANAGER", "AUDITOR"]


class SessionView(BaseModel):
    user: UserView
    csrf_token: str


class SiteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    active: bool


class Outcome(StrEnum):
    TESTED = "TESTED"
    NO_SIGNAL = "NO_SIGNAL"
    NO_INTERNET = "NO_INTERNET"
    SPEEDTEST_FAILED = "SPEEDTEST_FAILED"
    SKIPPED = "SKIPPED"


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    download_mbps: FiniteFloat = Field(ge=0)
    upload_mbps: FiniteFloat = Field(ge=0)
    ping_ms: FiniteFloat = Field(ge=0)
    jitter_ms: FiniteFloat | None = Field(default=None, ge=0)
    duration_ms: int = Field(gt=0, le=300_000)
    engine: Literal["cloudflare"]
    engine_version: str = Field(min_length=1, max_length=40)
    profile_version: str = Field(min_length=1, max_length=40)
    raw_summary: dict = Field(default_factory=dict)


class InspectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: UUID
    target_id: int = Field(gt=0)
    outcome: Outcome
    network_type: Literal["4G", "4G+", "5G", "UNKNOWN"]
    mobile_data_confirmed: bool
    device_label: str = Field(default="", max_length=200)
    remarks: str = Field(default="", max_length=4000)
    observed_at: datetime
    measurement: Measurement | None = None

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if (self.outcome == Outcome.TESTED) != (self.measurement is not None):
            raise ValueError("Only TESTED requires and permits a measurement")
        if (
            self.outcome in {Outcome.TESTED, Outcome.NO_SIGNAL, Outcome.NO_INTERNET}
            and not self.mobile_data_confirmed
        ):
            raise ValueError("Confirm Wi-Fi off and the correct mobile-data SIM")
        return self
