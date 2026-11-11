"""Create labelled synthetic business data only in rehearsal; verify real dump/restore contents."""

import json
import os
import secrets
import shutil
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

root = Path(__file__).resolve().parents[1]
docker = shutil.which("docker") or str(
    Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe"
)
compose = [
    docker,
    "compose",
    "-p",
    "istay-rehearsal",
    "--env-file",
    ".env.rehearsal",
    "-f",
    "compose.prod.yml",
    "-f",
    "compose.rehearsal.yml",
]
fixture_path = root / ".tools/rehearsal-business-fixture.json"
origin = "https://localhost:8443"
verify = ssl.create_default_context(cafile=str(root / "secrets/rehearsal-tls/ca.crt"))


def execute(arguments, data=None):
    result = subprocess.run(
        compose + arguments, cwd=root, text=True, input=data, capture_output=True, check=True
    )
    return result.stdout


if not fixture_path.exists():
    suffix = uuid4().hex[:8]
    credentials = {"username": "restore_" + suffix, "password": secrets.token_urlsafe(32)}
    bootstrap = """
import json,sys
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User
from app.security import hasher
assert settings().environment=='production' and settings().postgres_db=='istay_rehearsal'
data=json.load(sys.stdin)
with Session(engine()) as db:
 db.add(User(username=data['username'],full_name='SYNTHETIC backup acceptance admin',role='ADMIN',password_hash=hasher.hash(data['password'])))
 db.commit()
"""
    execute(["exec", "-T", "api", "python", "-c", bootstrap], json.dumps(credentials))
    with httpx.Client(base_url=origin, verify=verify, trust_env=False, timeout=25) as client:
        response = client.post("/api/v1/auth/login", json=credentials, headers={"Origin": origin})
        response.raise_for_status()
        admin_session = response.json()
        headers = {
            "Origin": origin,
            "X-CSRF-Token": admin_session["csrf_token"],
            "X-Workspace-User": str(admin_session["user"]["id"]),
        }

        def post(path, payload):
            result = client.post("/api/v1" + path, json=payload, headers=headers)
            result.raise_for_status()
            return result.json()

        site = client.get("/api/v1/sites").json()[0]
        block = post("/blocks", {"site_id": site["id"], "code": "RESTORE-" + suffix})
        floor = post("/floors", {"block_id": block["id"], "floor_no": 1})
        unit = post(
            "/units",
            {
                "floor_id": floor["id"],
                "unit_no": "SYNTHETIC-RESTORE",
                "locations": [
                    {"code": "L", "name": "Synthetic living room", "sort_order": 0},
                    {"code": "B1", "name": "Synthetic bedroom", "sort_order": 1},
                ],
            },
        )
        audit = post(
            "/audits", {"title": "SYNTHETIC database restore acceptance " + suffix, "site_ids": [site["id"]]}
        )
        telco = client.get("/api/v1/telcos").json()[0]
        targets = post(
            f"/audits/{audit['id']}/targets", {"unit_ids": [unit["id"]], "telco_ids": [telco["id"]]}
        )
        post(
            f"/audits/{audit['id']}/assignments",
            {"user_id": admin_session["user"]["id"], "target_ids": [t["id"] for t in targets]},
        )
        post(f"/audits/{audit['id']}/activate", None)
        client_id = str(uuid4())
        base = {
            "network_type": "UNKNOWN",
            "mobile_data_confirmed": True,
            "device_label": "SYNTHETIC restore fixture, not a SIM measurement",
            "remarks": "Synthetic backup acceptance data only",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        measured = base | {
            "client_id": client_id,
            "target_id": targets[0]["id"],
            "outcome": "TESTED",
            "measurement": {
                "download_mbps": 35.8,
                "upload_mbps": 12.5,
                "ping_ms": 28.4,
                "duration_ms": 19000,
                "engine": "cloudflare",
                "engine_version": "synthetic-restore",
                "profile_version": "mobile-v1",
            },
        }
        no_signal = base | {
            "client_id": str(uuid4()),
            "target_id": targets[1]["id"],
            "outcome": "NO_SIGNAL",
            "measurement": None,
        }
        response = post("/inspections/batch-sync", {"records": [measured, no_signal]})
        assert all(item["status"] == "SYNCED" for item in response["results"]), response
        client.post("/api/v1/auth/logout", headers=headers).raise_for_status()
    fixture_path.write_text(
        json.dumps(
            {"client_id": client_id, "audit_id": audit["id"], "owner_id": admin_session["user"]["id"]}
        ),
        encoding="utf-8",
    )
    # Disable the synthetic bootstrap account after creating its immutable historical data.
    disable = """
import json,sys
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User
from app.security import revoke_sessions
assert settings().postgres_db=='istay_rehearsal'
with Session(engine()) as db:
 user=db.scalar(select(User).where(User.username==json.load(sys.stdin)['username']))
 user.active=False
 revoke_sessions(db,user.id)
 db.commit()
"""
    execute(["exec", "-T", "api", "python", "-c", disable], json.dumps({"username": credentials["username"]}))

fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
read_hash = """
import json,sys
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import Inspection
assert settings().postgres_db=='istay_rehearsal'
with Session(engine()) as db: print(db.scalar(select(Inspection.payload_hash).where(Inspection.client_id==UUID(json.load(sys.stdin)['client_id']))))
"""
payload_hash = execute(["exec", "-T", "api", "python", "-c", read_hash], json.dumps(fixture)).strip()
assert len(payload_hash) == 64
backup_log = execute(["exec", "-T", "backup", "sh", "/opt/backup/backup.sh"])
filename = backup_log.strip().split(": ")[-1]
assert filename.startswith("istay-") and filename.endswith(".dump")
restored = execute(
    ["--profile", "operations", "run", "--rm", "restorecheck", filename, fixture["client_id"], payload_hash]
)
record = json.loads(
    next(
        line.removeprefix("BUSINESS_RECORD_JSON ")
        for line in restored.splitlines()
        if line.startswith("BUSINESS_RECORD_JSON ")
    )
)
assert record["outcome"] == "TESTED" and record["audit_status"] == "COMPLETED"
assert record["measurement"] == {
    "download_mbps": 35.8,
    "upload_mbps": 12.5,
    "ping_ms": 28.4,
    "engine_version": "synthetic-restore",
    "profile_version": "mobile-v1",
}
assert record["snapshot"]["unit"] == "SYNTHETIC-RESTORE" and record["user_id"] == fixture["owner_id"]
evidence = {
    "backup": filename,
    "scratch_restore_verified": True,
    "record": record,
    "notes": "Synthetic data only; disabled fixture account; live DB not overwritten. This is a same-host restore, not off-host recovery.",
}
(root / "docs/evidence/business-backup-restore.json").write_text(
    json.dumps(evidence, indent=2), encoding="utf-8"
)
print(
    "PASS: restored a real dump containing synthetic audit history, frozen target labels and exact speed metrics; fixture account disabled; scratch database removed."
)
