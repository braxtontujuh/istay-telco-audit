"""Real PostgreSQL transaction tests; never treat SQLite skips as passes."""

from uuid import uuid4

import pytest
from app.models import (
    Audit,
    AuditEvent,
    AuditTarget,
    Block,
    Floor,
    Inspection,
    Location,
    SpeedMeasurement,
    Telco,
    Unit,
    utcnow,
)
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def postgres_target(database):
    if database.dialect.name != "postgresql":
        pytest.skip("Run the Compose test profile against PostgreSQL")
    with Session(database) as db:
        db.add(Block(id=1, site_id=1, code="A"))
        db.flush()
        db.add(Floor(id=1, block_id=1, floor_no=1))
        db.flush()
        db.add(Unit(id=1, floor_id=1, unit_no="101"))
        db.flush()
        db.add_all([Location(id=1, unit_id=1, code="B1", name="Bedroom 1"), Telco(id=1, name="Test")])
        db.add(Audit(id=1, title="Test audit", created_by=1))
        db.flush()
        db.add(AuditTarget(id=1, audit_id=1, location_id=1, telco_id=1))
        db.commit()
    return database


def record(outcome):
    return Inspection(
        client_id=uuid4(),
        target_id=1,
        user_id=2,
        outcome=outcome,
        network_type="UNKNOWN",
        mobile_data_confirmed=True,
        observed_at=utcnow(),
        payload_hash="a" * 64,
    )


def measurement(inspection_id):
    return SpeedMeasurement(
        inspection_id=inspection_id,
        download_mbps=35.8,
        upload_mbps=12.5,
        ping_ms=28.4,
        jitter_ms=None,
        duration_ms=1000,
        engine="cloudflare",
        engine_version="test",
        profile_version="mobile-v1",
    )


def test_tested_requires_measurement_at_commit(postgres_target):
    with Session(postgres_target) as db:
        db.add(record("TESTED"))
        db.flush()  # Deferred invariant permits the transaction to construct both records.
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        attempt = record("TESTED")
        db.add(attempt)
        db.flush()
        db.add(measurement(attempt.id))
        db.commit()
        assert db.scalar(select(SpeedMeasurement.download_mbps)) == 35.8


def test_no_signal_forbids_measurements(postgres_target):
    with Session(postgres_target) as db:
        attempt = record("NO_SIGNAL")
        db.add(attempt)
        db.flush()
        db.add(measurement(attempt.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(record("NO_SIGNAL"))
        db.commit()
        assert db.scalar(select(SpeedMeasurement)) is None


def test_history_is_immutable(postgres_target):
    with Session(postgres_target) as db:
        db.add(record("NO_SIGNAL"))
        db.add(AuditEvent(audit_id=1, actor_id=1, action="test"))
        db.commit()
        for statement in (
            update(Inspection).values(remarks="rewritten"),
            delete(Inspection),
            update(AuditEvent).values(action="rewritten"),
            delete(AuditEvent),
        ):
            with pytest.raises(IntegrityError):
                db.execute(statement)
                db.commit()
            db.rollback()
