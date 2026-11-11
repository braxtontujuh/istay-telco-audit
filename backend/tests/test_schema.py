import math
from uuid import uuid4

import pytest
from app.cli import seed
from app.contracts import InspectionPayload
from app.models import (
    AssignmentTarget,
    Audit,
    AuditAssignment,
    AuditTarget,
    Block,
    Floor,
    Location,
    Site,
    Telco,
    Unit,
)
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_migration_contains_required_tables(database):
    assert {
        "sites",
        "test_locations",
        "audit_targets",
        "assignment_targets",
        "inspection_records",
        "speed_measurements",
        "audit_events",
        "sessions",
        "app_settings",
    } <= set(inspect(database).get_table_names())


def test_seed_is_idempotent(database):
    with Session(database) as db:
        seed(db)
        seed(db)
        assert db.query(Telco).count() == 6
        assert db.query(Site).count() == 6  # two test sites + four configured initial sites


def test_variable_layout_target_identity_and_scoped_foreign_keys(database):
    with Session(database) as db:
        db.add(Block(id=1, site_id=1, code="A"))
        db.flush()
        db.add(Floor(id=1, block_id=1, floor_no=1))
        db.flush()
        db.add_all([Unit(id=1, floor_id=1, unit_no="101"), Unit(id=2, floor_id=1, unit_no="102")])
        db.add_all([Telco(id=1, name="One"), Telco(id=2, name="Two")])
        db.add_all([Audit(id=1, title="First", created_by=1), Audit(id=2, title="Second", created_by=1)])
        db.flush()
        for uid, rooms in ((1, 3), (2, 4)):
            for n in range(rooms):
                location = Location(unit_id=uid, code=str(n), name=f"Space {n}")
                db.add(location)
                db.flush()
                db.add(AuditTarget(audit_id=1, location_id=location.id, telco_id=1))
        db.flush()
        assert db.query(AuditTarget).count() == 7
        db.add(AuditTarget(audit_id=1, location_id=1, telco_id=2))
        db.add(AuditAssignment(id=1, audit_id=2, user_id=2, assigned_by=1))
        db.commit()
        assert db.query(AuditTarget).filter_by(location_id=1).count() == 2
        db.add(AssignmentTarget(assignment_id=1, audit_id=1, target_id=1))
        with pytest.raises(IntegrityError):
            db.commit()


def sample_payload():
    return dict(
        client_id=uuid4(),
        target_id=1,
        outcome="NO_SIGNAL",
        network_type="UNKNOWN",
        mobile_data_confirmed=True,
        observed_at="2026-11-11T03:28:00Z",
    )


def test_no_signal_has_null_metrics_and_timezone_required():
    assert InspectionPayload(**sample_payload()).measurement is None
    with pytest.raises(ValidationError):
        InspectionPayload(**(sample_payload() | {"observed_at": "2026-11-11T03:28:00"}))


@pytest.mark.parametrize("value", [-1, math.nan, math.inf])
def test_speed_values_are_finite_nonnegative(value):
    measurement = dict(
        download_mbps=value,
        upload_mbps=2,
        ping_ms=20,
        duration_ms=1000,
        engine="cloudflare",
        engine_version="1",
        profile_version="mobile-v1",
    )
    with pytest.raises(ValidationError):
        InspectionPayload(**(sample_payload() | {"outcome": "TESTED", "measurement": measurement}))


def test_outcome_measurement_pair_and_confirmation():
    with pytest.raises(ValidationError):
        InspectionPayload(**(sample_payload() | {"outcome": "TESTED"}))
    with pytest.raises(ValidationError):
        InspectionPayload(**(sample_payload() | {"mobile_data_confirmed": False}))
