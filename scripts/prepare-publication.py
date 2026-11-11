"""Prepare reviewed Git source for connector upload; never include local secrets or backups."""

import argparse
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--emit-batch", type=int)
args = parser.parse_args()
directory = root / ".tools/publication"
if args.emit_batch is not None:
    print((directory / f"batch-{args.emit_batch}.json").read_text(encoding="utf-8"))
    raise SystemExit()

paths = (
    subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
    .decode()
    .split("\0")
)
paths = sorted(set(path for path in paths if path))
known_secrets = []
for file in (root / "secrets").rglob("*.txt"):
    value = file.read_text(encoding="utf-8-sig").strip()
    if len(value) >= 16:
        known_secrets.append(value)
for file in root.glob(".env*"):
    if file.name.endswith(".example"):
        continue
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        if re.match(r"^(POSTGRES_PASSWORD|.*TOKEN|.*SECRET)=", line):
            value = line.partition("=")[2].strip()
            if len(value) >= 16:
                known_secrets.append(value)
for file in (root / ".tools").glob("*fixture*.json"):

    def passwords(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "password" and isinstance(item, str):
                    known_secrets.append(item)
                else:
                    passwords(item)
        elif isinstance(value, list):
            for item in value:
                passwords(item)

    passwords(json.loads(file.read_text(encoding="utf-8-sig")))

entries, hashes = [], {}
for path in paths:
    if (
        re.match(r"^(secrets|backups|\.tools|\.venv|\.git|node_modules)/", path)
        or path == ".deployment.json"
        or (path.startswith(".env") and not path.endswith(".example"))
    ):
        raise SystemExit(f"Refusing private runtime file: {path}")
    file = root / path
    data = file.read_bytes()
    hashes[path] = hashlib.sha256(data).hexdigest()
    if file.suffix.lower() in (".png", ".ico"):
        entries.append({"path": path, "encoding": "base64", "content": base64.b64encode(data).decode()})
        continue
    content = data.decode("utf-8").replace("\r\n", "\n")
    if any(secret in content for secret in known_secrets) or re.search(
        r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
        content,
    ):
        raise SystemExit(f"Refusing possible secret in {path}; contents were not printed")
    entries.append({"path": path, "encoding": "utf-8", "content": content})

directory.mkdir(parents=True, exist_ok=True)
batches, batch, length = [], [], 0
for entry in entries:
    size = len(json.dumps(entry))
    if batch and length + size > 60000:
        batches.append(batch)
        batch, length = [], 0
    batch.append(entry)
    length += size
if batch:
    batches.append(batch)
for index, batch in enumerate(batches):
    (directory / f"batch-{index}.json").write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
metadata = {
    "file_count": len(entries),
    "batch_count": len(batches),
    "files": hashes,
    "secret_scan": "known local credentials and token/private-key patterns checked",
}
(directory / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in metadata.items() if key != "files"}))
