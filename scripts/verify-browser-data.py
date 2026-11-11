"""Read-only acceptance checks for the named disposable browser fixture, never production."""

import json
import os
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import httpx
from openpyxl import load_workbook

root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / ".tools/browser-fixture.json").read_text(encoding="utf-8-sig"))
assert fixture["origin"] == "http://localhost:8082"
docker = shutil.which("docker") or str(Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe")
compose = [docker, "compose", "--env-file", ".env.browser-test", "-p", "istay-browser-test", "-f", "compose.dev.yml", "-f", "compose.browser-test.yml"]
query = """
import json
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import Inspection, SpeedMeasurement
assert settings().environment == 'development' and settings().postgres_db == 'istay_browser_test'
with Session(engine()) as db:
 records = list(db.scalars(select(Inspection).order_by(Inspection.id)))
 print(json.dumps({'inspection_count':len(records),'distinct_client_ids':len({str(r.client_id) for r in records}),
 'records':[{'server_id':r.id,'client_id':str(r.client_id),'outcome':r.outcome,'owner_id':r.user_id} for r in records],
 'measurement_count':db.scalar(select(func.count()).select_from(SpeedMeasurement))}))
"""
database = json.loads(subprocess.check_output(compose + ["exec", "-T", "api", "python", "-c", query], cwd=root, text=True))
assert database["inspection_count"] == database["distinct_client_ids"] == 2
assert database["measurement_count"] == 0
assert {r["outcome"] for r in database["records"]} == {"NO_SIGNAL", "NO_INTERNET"}
assert all(r["owner_id"] == fixture["owner_id"] for r in database["records"])
with httpx.Client(base_url=fixture["origin"], trust_env=False, timeout=20) as client:
    login = client.post("/api/v1/auth/login", json=fixture["admin"], headers={"Origin": fixture["origin"]})
    login.raise_for_status()
    try:
        path = f"/api/v1/audits/{fixture['audit_id']}"
        response = client.get(path + "/results")
        response.raise_for_status()
        report = response.json()
        assert report["summary"]["total"] == 3 and report["summary"]["inspected"] == 2 and report["summary"]["pending"] == 1
        assert report["telco_comparison"][0]["avg_download_mbps"] is None
        response = client.get(path + "/export.xlsx")
        response.raise_for_status()
        book = load_workbook(BytesIO(response.content))
        assert book["All Attempts"].max_row == 3 and book["Pending Targets"].max_row == 2
        evidence = database | {"report_summary": report["summary"], "xlsx_sheets": book.sheetnames,
                               "notes": "Synthetic desktop browser records; server-outage simulation, not Android airplane-mode or real SIM validation."}
        (root / "docs/evidence/phase4-browser-database.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    finally:
        client.post("/api/v1/auth/logout", headers={"Origin": fixture["origin"], "X-CSRF-Token": login.json()["csrf_token"]}).raise_for_status()
print("PASS: two unique accepted synthetic records, no speed measurements, report/Excel totals match; evidence saved.")
