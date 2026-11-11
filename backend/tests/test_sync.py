from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.main import app
from app.models import Audit, Inspection, SpeedMeasurement, UserSiteAccess
from conftest import login
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_workflow import activate_assigned, draft_with_targets, send


def payload(target_id, outcome="NO_SIGNAL"):
    return {
        "client_id": str(uuid4()),
        "target_id": target_id,
        "outcome": outcome,
        "network_type": "UNKNOWN",
        "mobile_data_confirmed": True,
        "observed_at": "2026-11-11T03:28:00Z",
        "remarks": "Offline test",
    }


def setup(client):
    login(client)
    audit, targets, _, _ = draft_with_targets(client)
    activate_assigned(client, audit, targets)
    return audit, targets


def sync(client, records, owner=2):
    token = client.get("/api/v1/auth/me").json()["csrf_token"]
    return client.post(
        "/api/v1/inspections/batch-sync",
        json={"records": records},
        headers={"Origin": "http://testserver", "X-CSRF-Token": token, "X-Workspace-User": str(owner)},
    )


def test_independent_acks_and_immutable_uuid(client, database):
    audit, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        item = payload(targets[0]["id"])
        invalid = payload(targets[1]["id"]) | {"outcome": "TESTED"}
        response = sync(employee, [item, invalid, payload(targets[2]["id"])])
        assert response.status_code == 200
        results = response.json()["results"]
        assert [value["status"] for value in results] == ["SYNCED", "CONFLICT", "SYNCED"]
        repeated = sync(employee, [item]).json()["results"][0]
        assert repeated["server_id"] == results[0]["server_id"]
        changed = sync(employee, [item | {"remarks": "Changed immutable payload"}]).json()["results"][0]
        assert changed["status"] == "CONFLICT" and changed["error"]["code"] == "UUID_PAYLOAD_CONFLICT"
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Inspection)) == 2
        assert db.scalar(select(SpeedMeasurement)) is None


def test_outcomes_completion_and_later_failure_policy(client, database):
    audit, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        records = [
            payload(value["id"], "NO_INTERNET" if i % 2 else "NO_SIGNAL") for i, value in enumerate(targets)
        ]
        records[0] = payload(targets[0]["id"], "TESTED") | {
            "measurement": {
                "download_mbps": 35.8,
                "upload_mbps": 12.5,
                "ping_ms": 28.4,
                "duration_ms": 19000,
                "engine": "cloudflare",
                "engine_version": "test",
                "profile_version": "mobile-v1",
            }
        }
        assert all(value["status"] == "SYNCED" for value in sync(employee, records).json()["results"])
        assert (
            sync(employee, [payload(targets[0]["id"], "SPEEDTEST_FAILED")]).json()["results"][0]["status"]
            == "SYNCED"
        )
    counts = client.get(f"/api/v1/audits/{audit['id']}/progress").json()
    assert (
        counts["inspected"] == 7
        and counts["tested"] == 1
        and counts["pending"] == 0
        and counts["failed_attempts"] == 1
    )
    assert counts["no_signal"] == 3 and counts["no_internet"] == 3
    with Session(database) as db:
        assert db.get(Audit, audit["id"]).status == "COMPLETED"
        assert db.scalar(select(func.avg(SpeedMeasurement.download_mbps))) == 35.8


def test_late_closed_record_conflicts_and_manager_reopen(client, database):
    audit, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        accepted = payload(targets[0]["id"])
        assert sync(employee, [accepted]).json()["results"][0]["status"] == "SYNCED"
        late = payload(targets[1]["id"])
        send(client, f"/audits/{audit['id']}/close", {"reason": "Manager closed before reconnect"})
        result = sync(employee, [late, accepted]).json()["results"]
        assert result[0]["status"] == "CONFLICT" and result[1]["status"] == "SYNCED"
        send(client, f"/audits/{audit['id']}/reopen", {"reason": "Resolve late offline draft"})
        assert sync(employee, [late]).json()["results"][0]["status"] == "SYNCED"
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Inspection)) == 2


def test_revoked_site_and_account_switch_are_not_silently_accepted(client, database):
    _, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        wrong = sync(employee, [payload(targets[0]["id"])], owner=1)
        assert wrong.status_code == 409
        with Session(database) as db:
            db.execute(delete(UserSiteAccess).where(UserSiteAccess.user_id == 2))
            db.commit()
        result = sync(employee, [payload(targets[0]["id"])]).json()["results"][0]
        assert result["status"] == "CONFLICT" and result["error"]["code"] == "SITE_ACCESS_REVOKED"
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Inspection)) == 0


def test_batch_size_auth_and_profile_validation(client):
    _, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        assert sync(employee, [payload(targets[0]["id"])] * 21).status_code == 422
        bad = payload(targets[0]["id"], "TESTED") | {
            "measurement": {
                "download_mbps": 1,
                "upload_mbps": 1,
                "ping_ms": 1,
                "duration_ms": 1000,
                "engine": "cloudflare",
                "engine_version": "test",
                "profile_version": "wrong",
            }
        }
        result = sync(employee, [bad]).json()["results"][0]
        assert result["status"] == "CONFLICT" and result["error"]["code"] == "MEASUREMENT_PROFILE_MISMATCH"


def test_concurrent_duplicate_sync_has_one_record(client, database):
    if database.dialect.name != "postgresql":
        pytest.skip("Concurrent transactions require PostgreSQL")
    _, targets = setup(client)
    with TestClient(app) as employee:
        token = login(employee, "auditor")
        cookie = employee.cookies.get("istay_session")
    item = payload(targets[0]["id"])

    def submit(_):
        with TestClient(app) as worker:
            worker.cookies.set("istay_session", cookie)
            return worker.post(
                "/api/v1/inspections/batch-sync",
                json={"records": [item]},
                headers={"Origin": "http://testserver", "X-CSRF-Token": token, "X-Workspace-User": "2"},
            ).json()["results"][0]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    assert all(value["status"] == "SYNCED" for value in results)
    assert len({value["server_id"] for value in results}) == 1
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Inspection)) == 1
