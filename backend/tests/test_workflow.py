import pytest
from app.main import app
from app.models import AuditEvent, Unit
from conftest import login
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def send(client, path, payload=None, method="POST", expected=200):
    csrf = client.get("/api/v1/auth/me").json()["csrf_token"]
    response = client.request(
        method, "/api/v1" + path, json=payload, headers={"Origin": "http://testserver", "X-CSRF-Token": csrf}
    )
    assert response.status_code == expected, response.text
    return response.json() if response.content else None


def layouts(client):
    block = send(client, "/blocks", {"site_id": 1, "code": "A"}, expected=201)
    floor = send(client, "/floors", {"block_id": block["id"], "floor_no": 1}, expected=201)
    units = []
    for number, bedrooms in [("101", 2), ("102", 3)]:
        rooms = [{"code": f"B{i}", "name": f"Bedroom {i}", "sort_order": i} for i in range(1, bedrooms + 1)]
        rooms.append({"code": "L", "name": "Living room", "sort_order": 0})
        units.append(
            send(
                client,
                "/units",
                {"floor_id": floor["id"], "unit_no": number, "locations": rooms},
                expected=201,
            )
        )
    telcos = [
        send(client, "/telcos", {"name": name}, expected=201) for name in ("Carrier One", "Carrier Two")
    ]
    return floor, units, telcos


def draft_with_targets(client):
    floor, units, telcos = layouts(client)
    audit = send(client, "/audits", {"title": "Dormitory audit", "site_ids": [1]}, expected=201)
    targets = send(
        client,
        f"/audits/{audit['id']}/targets",
        {"unit_ids": [value["id"] for value in units], "telco_ids": [telcos[0]["id"]]},
        expected=201,
    )
    return audit, targets, units, telcos


def activate_assigned(client, audit, targets):
    send(
        client,
        f"/audits/{audit['id']}/assignments",
        {"user_id": 2, "target_ids": [value["id"] for value in targets]},
    )
    return send(client, f"/audits/{audit['id']}/activate")


def test_variable_room_targets_and_telco_identity(client):
    login(client)
    audit, targets, units, telcos = draft_with_targets(client)
    assert len(targets) == 7
    assert sum(value["snapshot"]["unit_id"] == units[0]["id"] for value in targets) == 3
    assert sum(value["snapshot"]["unit_id"] == units[1]["id"] for value in targets) == 4
    first = targets[0]
    targets = send(
        client,
        f"/audits/{audit['id']}/targets",
        {"location_ids": [first["location_id"]], "telco_ids": [telcos[1]["id"]]},
        expected=201,
    )
    assert len(targets) == 8
    assert len([value for value in targets if value["location_id"] == first["location_id"]]) == 2
    targets = send(
        client,
        f"/audits/{audit['id']}/targets",
        {"location_ids": [first["location_id"]], "telco_ids": [telcos[1]["id"]]},
        expected=201,
    )
    assert len(targets) == 8  # repeated selection does not duplicate a target


def test_activation_freezes_target_list_and_labels(client, database):
    login(client)
    audit, targets, units, telcos = draft_with_targets(client)
    send(client, f"/audits/{audit['id']}/activate", expected=409)
    assert activate_assigned(client, audit, targets)["status"] == "ACTIVE"
    first = targets[0]
    send(
        client,
        f"/locations/{first['location_id']}",
        {"code": first["snapshot"]["room_code"], "name": "Renamed after activation"},
        method="PATCH",
    )
    template = send(
        client,
        "/room-templates",
        {"name": "Custom layout", "items": [{"code": "OFFICE", "name": "Office"}]},
        expected=201,
    )
    send(client, f"/room-templates/{template['id']}/apply", {"unit_ids": [units[0]["id"]]})
    current = client.get(f"/api/v1/audits/{audit['id']}/targets").json()
    assert len(current) == 7
    assert current[0]["snapshot"]["room"] == first["snapshot"]["room"]
    send(
        client,
        f"/audits/{audit['id']}/targets",
        {"unit_ids": [units[0]["id"]], "telco_ids": [telcos[1]["id"]]},
        expected=409,
    )
    send(
        client, f"/audits/{audit['id']}", {"config": {"weak_download_mbps": 1}}, method="PATCH", expected=409
    )
    with Session(database) as db:
        assert list(db.scalars(select(AuditEvent.action).where(AuditEvent.audit_id == audit["id"]))) == [
            "CREATED",
            "TARGETS_ADDED",
            "ASSIGNMENT_UPDATED",
            "ACTIVATED",
        ]


def test_role_site_and_assignment_checks(client):
    login(client)
    audit, targets, units, telcos = draft_with_targets(client)
    send(
        client,
        f"/audits/{audit['id']}/assignments",
        {"user_id": 3, "target_ids": [targets[0]["id"]]},
        expected=403,
    )
    send(client, f"/audits/{audit['id']}/assignments", {"user_id": 2, "target_ids": [targets[0]["id"]]})
    # All rooms must have a permitted assignee before activation.
    send(client, f"/audits/{audit['id']}/activate", expected=409)
    activate_assigned(client, audit, targets)
    with TestClient(app) as employee:
        login(employee, "auditor")
        assert len(employee.get(f"/api/v1/audits/{audit['id']}/targets").json()) == 7
        send(employee, "/blocks", {"site_id": 1, "code": "B"}, expected=403)
        send(employee, f"/audits/{audit['id']}/close", {"reason": "Not allowed"}, expected=403)
        send(client, f"/audits/{audit['id']}/assignments", {"user_id": 2, "target_ids": []})
        assert employee.get(f"/api/v1/audits/{audit['id']}/targets").status_code == 403
    with TestClient(app) as manager:
        login(manager, "manager")
        assert manager.get(f"/api/v1/audits/{audit['id']}").status_code == 403
        assert manager.get("/api/v1/sites/1/blocks").status_code == 403


def test_close_requires_reason_and_reopen_is_audited(client, database):
    login(client)
    audit, targets, _, _ = draft_with_targets(client)
    activate_assigned(client, audit, targets)
    counts = client.get(f"/api/v1/audits/{audit['id']}/progress").json()
    assert counts["total"] == 7 and counts["pending"] == 7 and counts["speedtest_success_percent"] is None
    send(client, f"/audits/{audit['id']}/close", {}, expected=422)
    assert (
        send(client, f"/audits/{audit['id']}/close", {"reason": "Units inaccessible"})["status"] == "CLOSED"
    )
    send(client, f"/audits/{audit['id']}/assignments", {"user_id": 2, "target_ids": []}, expected=409)
    assert (
        send(client, f"/audits/{audit['id']}/reopen", {"reason": "Manager approved follow-up"})["status"]
        == "ACTIVE"
    )
    with Session(database) as db:
        events = list(
            db.scalars(select(AuditEvent).where(AuditEvent.audit_id == audit["id"]).order_by(AuditEvent.id))
        )
        assert events[-2].details["unresolved"] == 7
        assert events[-1].action == "REOPENED"


def test_bulk_import_rolls_back_whole_request(client, database):
    login(client)
    floor, _, _ = layouts(client)
    send(
        client,
        "/units/import",
        {"units": [{"floor_id": floor["id"], "unit_no": "new"}, {"floor_id": 99999, "unit_no": "bad"}]},
        expected=404,
    )
    with Session(database) as db:
        assert db.scalar(select(Unit).where(Unit.unit_no == "new")) is None


def test_user_creation_and_live_permission_revocation(client):
    login(client)
    new_user = send(
        client,
        "/users",
        {
            "username": "new.employee",
            "full_name": "New Employee",
            "password": "temporary-long-test-password",
            "role": "AUDITOR",
            "site_ids": [1],
        },
        expected=201,
    )
    assert "password" not in new_user and "password_hash" not in new_user
    with TestClient(app) as employee:
        response = employee.post(
            "/api/v1/auth/login",
            json={"username": "new.employee", "password": "temporary-long-test-password"},
            headers={"Origin": "http://testserver"},
        )
        assert response.status_code == 200
        send(client, f"/users/{new_user['id']}", {"site_ids": []}, method="PATCH")
        assert employee.get("/api/v1/auth/me").status_code == 401
    send(client, "/users/1", {"active": False}, method="PATCH", expected=409)


@pytest.mark.parametrize("payload", [{"site_ids": [1]}, {"site_ids": [1, 2]}])
def test_manager_cannot_expand_site_scope(client, payload):
    login(client, "manager")
    send(client, "/audits", {"title": "Forbidden", **payload}, expected=403)
