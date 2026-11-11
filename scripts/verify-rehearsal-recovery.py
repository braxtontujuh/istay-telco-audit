"""Crash only the isolated rehearsal API and verify Docker's restart policy recovers it."""

import os
import shutil
import ssl
import subprocess
import time
from pathlib import Path

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
container = subprocess.check_output(compose + ["ps", "-q", "api"], cwd=root, text=True).strip()
if not container:
    raise SystemExit("Rehearsal API is not running")


def restarts():
    return int(
        subprocess.check_output(
            [docker, "inspect", "--format", "{{.RestartCount}}", container], text=True
        ).strip()
    )


context = ssl.create_default_context(cafile=str(root / "secrets/rehearsal-tls/ca.crt"))
with httpx.Client(base_url="https://localhost:8443", verify=context, trust_env=False, timeout=5) as client:
    for path, cache in [("/", "no-cache"), ("/api/v1/health/live", "no-store")]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == cache
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    print("PASS: HTTPS response security/cache headers on shell and API", flush=True)
    before = restarts()
    crash = """
import os, signal
from pathlib import Path
from app.config import settings
assert settings().environment == 'production' and settings().postgres_db == 'istay_rehearsal'
children = Path('/proc/1/task/1/children').read_text().split()
targets = [int(p) for p in children if int(p) != os.getpid() and b'app.main:app' in Path('/proc/'+p+'/cmdline').read_bytes()]
assert len(targets) == 1, 'Expected exactly one rehearsal uvicorn process'
os.kill(targets[0], signal.SIGKILL)
"""
    subprocess.run(compose + ["exec", "-T", "api", "python", "-c", crash], cwd=root, capture_output=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health/live")
            if restarts() > before and response.status_code == 200:
                print("PASS: API automatically restarted after process crash and HTTPS recovered", flush=True)
                break
        except (httpx.HTTPError, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    else:
        raise SystemExit("API did not automatically recover within 60 seconds")
