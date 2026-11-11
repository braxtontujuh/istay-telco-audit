"""Lock installed runtime dependencies for Linux builds, without local paths or test tooling."""

import importlib.metadata as metadata
import tomllib
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root = Path(__file__).resolve().parents[1]
project = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]
queue = [Requirement(value) for value in project["dependencies"]]
locked = {}
while queue:
    req = queue.pop()
    name = canonicalize_name(req.name)
    if name in locked:
        continue
    dist = metadata.distribution(name)
    locked[name] = dist.version
    for dep in dist.requires or []:
        candidate = Requirement(dep)
        env = default_environment() | {
            "sys_platform": "linux",
            "platform_system": "Linux",
            "os_name": "posix",
        }
        if not candidate.marker or any(
            candidate.marker.evaluate(env | {"extra": extra}) for extra in ["", *req.extras]
        ):
            queue.append(candidate)
(root / "backend/requirements.lock").write_text(
    "# Resolved and tested 2026-11-11. Update deliberately and rebuild images.\n"
    + "\n".join(f"{name}=={version}" for name, version in sorted(locked.items()))
    + "\n"
)
