"""Exercise the real scheduler with controlled clock/backup processes, never live DB/storage."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Backup scheduler runs in the Linux container")
SCRIPT = Path(__file__).resolve().parents[2] / "ops/backup/schedule.sh"


def schedule(tmp_path, times, last=None, fail_first=False):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {"times": times, "index": 0, "now": 0, "last": last, "calls": [], "fail_first": fail_first}
        )
    )
    helper = """import json,os,sys
from pathlib import Path
p=Path(os.environ['BACKUP_TEST_STATE']);s=json.loads(p.read_text())
name=Path(sys.argv[0]).name
if name=='date':
 if s['index']>=len(s['times']):sys.exit(75)
 s['now']=s['times'][s['index']];s['index']+=1;p.write_text(json.dumps(s));print(s['now'])
elif name=='cat':
 if s['last'] is None:sys.exit(1)
 print(s['last'])
elif name=='sh':
 s['calls'].append(s['now'])
 failed=s['fail_first'] and len(s['calls'])==1
 if not failed:s['last']=s['now']
 p.write_text(json.dumps(s));sys.exit(1 if failed else 0)
elif name=='sleep':pass
else:sys.exit(2)
"""
    for name in ("date", "cat", "sh", "sleep"):
        file = tmp_path / name
        file.write_text(f"#!{sys.executable}\n" + helper)
        file.chmod(0o700)
    result = subprocess.run(
        ["/bin/sh", str(SCRIPT)],
        env=os.environ | {"PATH": str(tmp_path), "BACKUP_TEST_STATE": str(state)},
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 75, result.stderr.decode()
    return json.loads(state.read_text())


def test_initial_backup_runs_once_before_scheduled_hour(tmp_path):
    assert schedule(tmp_path, [36000, 36060, 36120])["calls"] == [36000]


def test_daily_boundary_runs_once_at_1900_utc(tmp_path):
    assert schedule(tmp_path, [68340, 68400, 68460], last=68300)["calls"] == [68400]


def test_missed_job_catches_up_after_docker_returns(tmp_path):
    assert schedule(tmp_path, [122400, 122460], last=43200)["calls"] == [122400]


def test_midnight_does_not_repeat_already_completed_daily_slot(tmp_path):
    assert schedule(tmp_path, [86400, 90000], last=72000)["calls"] == []


def test_failure_retries_next_poll_and_success_prevents_duplicate(tmp_path):
    result = schedule(tmp_path, [68400, 68460, 68520], last=43200, fail_first=True)
    assert result["calls"] == [68400, 68460] and result["last"] == 68460
