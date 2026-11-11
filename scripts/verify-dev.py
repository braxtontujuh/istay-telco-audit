"""Verify real localhost auth and restart/recreate persistence using disposable development data."""

import argparse
import json
import os
import secrets
import shutil
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker") or str(
    Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe"
)
parser = argparse.ArgumentParser()
parser.add_argument("--rehearsal", action="store_true")
parser.add_argument("--local-staging-root", type=Path)
args = parser.parse_args()
if args.rehearsal and args.local_staging_root:
    parser.error("Choose rehearsal or local production staging, not both")
COMPOSE = (
    [
        DOCKER,
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
    if args.rehearsal
    else [DOCKER, "compose", "--env-file", ".env.dev", "-f", "compose.dev.yml"]
)
ORIGIN = "https://localhost:8443" if args.rehearsal else "http://localhost:8081"
SAFE_ENVIRONMENT = "(settings().environment, settings().postgres_db) in [('development','istay_dev'), ('production','istay_rehearsal')]"
if args.local_staging_root:
    ROOT = args.local_staging_root.resolve()
    metadata = json.loads((ROOT / ".deployment.json").read_text(encoding="utf-8-sig"))
    if metadata["mode"] != "LocalStaging" or Path(metadata["directory"]).resolve() != ROOT:
        raise RuntimeError("Only an explicitly staged local deployment may be verified")
    COMPOSE = [
        DOCKER,
        "compose",
        "-p",
        "istay-prod",
        "--env-file",
        ".env.local-staging",
        "-f",
        "compose.prod.yml",
        "-f",
        "compose.local-staging.yml",
    ]
    ORIGIN = "https://localhost:8444"
    SAFE_ENVIRONMENT = "settings().environment=='production' and settings().postgres_db=='istay' and settings().app_origin=='https://localhost:8444'"
username = "envcheck_" + uuid4().hex
password = secrets.token_urlsafe(32)
probe = uuid4().hex

BOOTSTRAP = """
import json, sys
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User, AppSetting
from app.security import hasher
assert SAFE_ENVIRONMENT, 'Disposable dev/rehearsal database only'
data = json.load(sys.stdin)
with Session(engine()) as db:
    db.add(User(username=data['username'],full_name='Temporary environment check',role='ADMIN',password_hash=hasher.hash(data['password'])))
    db.add(AppSetting(key=data['username'],value={'probe':data['probe']}))
    db.commit()
"""
CHECK = """
import json, sys
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User, AppSetting
assert SAFE_ENVIRONMENT
data=json.load(sys.stdin)
with Session(engine()) as db:
    assert db.get(AppSetting,data['username']).value == {'probe':data['probe']}
    assert db.scalar(select(User).where(User.username == data['username'])) is not None
"""
CLEANUP = """
import json,sys
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models import User, AppSetting, LoginLimit
from app.security import revoke_sessions, digest
assert SAFE_ENVIRONMENT
name=json.load(sys.stdin)['username']
assert name.startswith('envcheck_') and len(name)==41
with Session(engine()) as db:
    user=db.scalar(select(User).where(User.username==name))
    if user:
        revoke_sessions(db,user.id)
        db.delete(user)
    db.execute(delete(AppSetting).where(AppSetting.key==name))
    db.execute(delete(LoginLimit).where(LoginLimit.key_hash==digest(name)))
    db.commit()
"""


def run_python(code):
    subprocess.run(
        COMPOSE + ["exec", "-T", "api", "python", "-c", code.replace("SAFE_ENVIRONMENT", SAFE_ENVIRONMENT)],
        cwd=ROOT,
        input=json.dumps({"username": username, "password": password, "probe": probe}),
        text=True,
        check=True,
        capture_output=True,
    )


def wait_ready(client):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health/ready")
            if response.status_code == 200 and response.json() == {"status": "ready"}:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("Authenticated readiness did not recover within 90 seconds")


def main():
    verify = (
        ssl.create_default_context(
            cafile=str(
                ROOT
                / (
                    "secrets/local-staging-tls/ca.crt"
                    if args.local_staging_root
                    else "secrets/rehearsal-tls/ca.crt"
                )
            )
        )
        if args.rehearsal or args.local_staging_root
        else True
    )
    with httpx.Client(base_url=ORIGIN, timeout=10, trust_env=False, verify=verify) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/health/live").json() == {"status": "ok"}
        assert client.get("/api/v1/auth/me").status_code == 401
        run_python(BOOTSTRAP)
        try:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
                headers={"Origin": ORIGIN},
            )
            assert response.status_code == 200, f"Login failed: {response.status_code}"
            if args.rehearsal or args.local_staging_root:
                assert "Secure" in response.headers["set-cookie"]
                assert "HttpOnly" in response.headers["set-cookie"]
            csrf = response.json()["csrf_token"]
            assert len(client.get("/api/v1/sites").json()) >= 4
            wait_ready(client)
            print("PASS: localhost UI/API, session login and authenticated readiness", flush=True)
            for command, label in (
                (["restart", "db", "api"], "restart"),
                (["up", "-d", "--force-recreate", "db", "api"], "container recreation"),
            ):
                subprocess.run(COMPOSE + command, cwd=ROOT, check=True)
                wait_ready(client)
                run_python(CHECK)
                print(f"PASS: database record and session persisted after {label}", flush=True)
            denied = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
            assert denied.status_code == 403
            response = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
            assert response.status_code == 204
            assert client.get("/api/v1/auth/me").status_code == 401
            print("PASS: CSRF rejection and server-side logout/revocation", flush=True)
        finally:
            run_python(CLEANUP)
            print("Temporary development verification account/probe cleaned up", flush=True)


if __name__ == "__main__":
    main()
