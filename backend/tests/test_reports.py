from io import BytesIO

from app.main import app
from app.models import UserSiteAccess
from conftest import login
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sync import payload, setup, sync


def measured_payload(target_id):
    return payload(target_id, "TESTED") | {
        "measurement": {
            "download_mbps": 8,
            "upload_mbps": 4,
            "ping_ms": 150,
            "duration_ms": 1000,
            "engine": "cloudflare",
            "engine_version": "mock",
            "profile_version": "mobile-v1",
        }
    }


def test_report_latest_counts_thresholds_and_excel_match_database(client):
    audit, targets = setup(client)
    with TestClient(app) as employee:
        login(employee, "auditor")
        records = [
            measured_payload(targets[0]["id"]),
            payload(targets[1]["id"], "NO_SIGNAL") | {"remarks": '=HYPERLINK("https://example.invalid")'},
            payload(targets[2]["id"], "NO_INTERNET"),
            payload(targets[0]["id"], "SPEEDTEST_FAILED"),
            payload(targets[3]["id"], "SKIPPED"),
        ]
        assert all(row["status"] == "SYNCED" for row in sync(employee, records).json()["results"])
    url = f"/api/v1/audits/{audit['id']}"
    report = client.get(url + "/results").json()
    assert report["summary"] == {
        "total": 7,
        "inspected": 3,
        "pending": 4,
        "tested": 1,
        "no_signal": 1,
        "no_internet": 1,
        "completion_percent": 42.86,
        "speedtest_success_percent": 33.33,
        "issue_percent_of_inspected": 66.67,
        "skipped_attempts": 1,
        "failed_attempts": 1,
        "attempt_count": 5,
    }
    comparison = report["telco_comparison"][0]
    assert comparison["avg_download_mbps"] == 8 and comparison["sample_count"] == 1
    assert comparison["first_received_at"] and comparison["last_received_at"]
    assert len(report["weak_locations"]) == 3
    assert report["weak_locations"][0]["weak_reasons"] == ["LOW_DOWNLOAD", "HIGH_PING"]
    assert report["latest_results"][0]["outcome"] == "TESTED"
    assert client.get(url + "/coverage").json()["summary"] == report["summary"]
    assert len(client.get(url + "/weak-locations").json()["weak_locations"]) == 3
    response = client.get(url + "/export.xlsx")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == [
        "Summary",
        "Telco Comparison",
        "Latest Results",
        "No Signal-No Internet",
        "Pending Targets",
        "All Attempts",
    ]
    assert book["Latest Results"].max_row == 8 and book["All Attempts"].max_row == 6
    assert book["Pending Targets"].max_row == 5 and book["No Signal-No Internet"].max_row == 3
    summary = dict(book["Summary"].values)
    assert summary["inspected"] == 3 and summary["failed_attempts"] == 1
    text_cells = [
        cell
        for row in book["All Attempts"]
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("=HYPERLINK")
    ]
    assert len(text_cells) == 1 and text_cells[0].data_type == "s"
    assert client.get("/api/v1/dashboard/summary").json()["summary"]["inspected"] == 3


def test_reports_export_dashboard_enforce_role_and_full_site_scope(client, database):
    audit, targets = setup(client)
    url = f"/api/v1/audits/{audit['id']}"
    with TestClient(app) as outsider:
        assert outsider.get(url + "/export.xlsx").status_code == 401
        login(outsider, "auditor")
        for suffix in ("/results", "/coverage", "/weak-locations", "/export.xlsx"):
            assert outsider.get(url + suffix).status_code == 403
        assert outsider.get("/api/v1/dashboard/summary").status_code == 403
        login(outsider, "manager")
        assert outsider.get(url + "/results?site_id=2").status_code == 403
        assert outsider.get(url + "/export.xlsx?site_id=2").status_code == 403
        assert outsider.get("/api/v1/dashboard/summary").json()["summary"]["total"] == 0
        with Session(database) as db:
            db.add(UserSiteAccess(user_id=3, site_id=1))
            db.commit()
        assert outsider.get(url + "/results").json()["summary"]["total"] == 7
        assert outsider.get(url + "/results?site_id=2").json()["latest_results"] == []
        assert outsider.get(url + "/results?telco_id=99999").json()["summary"]["total"] == 0
        floor_id = targets[0]["snapshot"]["floor_id"]
        assert outsider.get(url + f"/results?floor_id={floor_id}").json()["summary"]["total"] == 7
        with Session(database) as db:
            db.delete(
                db.scalar(
                    select(UserSiteAccess).where(UserSiteAccess.user_id == 3, UserSiteAccess.site_id == 1)
                )
            )
            db.commit()
        assert outsider.get(url + "/export.xlsx").status_code == 403
