# I-Stay Telco Audit

**Current state: application runs locally; employee deployment is not complete.** Upstream contained only [SPEC.md](SPEC.md). This checkout adds React/TypeScript/Vite PWA, FastAPI server sessions and scoped authorization, dynamic room layouts, audit snapshots/assignments, user-scoped IndexedDB outbox, idempotent sync, Cloudflare SDK integration, coverage reports and Excel exports, plus Alembic migrations and deployment tooling. Android/SIM and external HTTPS acceptance remain pending.

WSL2, Ubuntu 24.04 and Docker Desktop are installed. The development stack is at http://localhost:8081. All 44 PostgreSQL/Linux tests and 20 frontend tests passed. Desktop browser tests verified cached relaunch, local No Signal/No Internet capture, account isolation, closure conflicts, manager resolution and server acknowledgment without duplicates. Authentication, restart/recreation persistence, production HTTPS rehearsal, backup restore and API crash recovery were verified using disposable data. The permanent production-staging administrator admin has now been created privately and its account/backup verified; development and rehearsal accounts remain separate. Local HTTPS rehearsal uses a test CA trusted only by the test client; it is not the external employee URL.

See [PLAN.md](PLAN.md), [application workflow](docs/APPLICATION.md), [host inspection](docs/HOST-INSPECTION.md), [Windows setup](docs/WINDOWS-SETUP.md), [operations](docs/OPERATIONS.md), [Cloudflare setup](docs/CLOUDFLARE.md), and [verification record](docs/VERIFICATION.md).

Cloudflare is currently deferred by the operator. Approved nonsynced local production staging and its tested logon task are described in [LOCAL-STAGING.md](docs/LOCAL-STAGING.md). Off-host storage is not yet available, so disk-loss recovery and off-host alerting are not claimed.

The implementation is merged into main and the [GHCR publication run](https://github.com/braxtontujuh/istay-telco-audit/actions/runs/43122556416) passed. Published API/web/backup images were pulled and checked by digest; references are recorded in [the release manifest](releases/ghcr-9b37796bc4a7.json). This did not replace the running HP release or enable external access.

## Development (after WSL2 and Docker Desktop work)

Run from this repository in PowerShell:

```powershell
./scripts/New-LocalConfig.ps1 -Environment Development
docker compose --env-file .env.dev -f compose.dev.yml config --quiet
docker compose --env-file .env.dev -f compose.dev.yml up -d --build
docker compose --env-file .env.dev -f compose.dev.yml exec api python -m app.cli seed
docker compose --env-file .env.dev -f compose.dev.yml exec api python -m app.cli create-admin
```

Visit http://localhost:8081. Login credentials are created interactively; none are seeded or committed. `create-admin` hides password input. Migrations run before the API starts. The development database uses the `istay-dev_pgdata` Docker volume. No PostgreSQL port is published; use `docker compose ... exec db psql` for local maintenance.

Development HTTP allows non-Secure session cookies **only on localhost**. Android remote use must use the production HTTPS origin. Vite's development server does not provide the production service worker; use the production image/preview for later PWA tests. Do not expose the development server via a tunnel.

## Checks without Docker

With Python 3.12+, Node 24+ and pnpm 11.25.0 available:

```powershell
python -m venv .venv
./.venv/Scripts/python -m pip install -r backend/requirements.lock
./.venv/Scripts/python -m pip install -e './backend[test]'
./.venv/Scripts/python -m pytest backend/tests -q
./.venv/Scripts/python -m ruff check --config backend/pyproject.toml backend
pnpm --dir frontend install --frozen-lockfile
python scripts/export-openapi.py
pnpm --dir frontend contracts
pnpm --dir frontend test
pnpm --dir frontend build
```

The backend tests use temporary SQLite databases by default. PostgreSQL-only deferred triggers and concurrent transactions are explicitly skipped there. The Docker test profile exercises the complete suite against PostgreSQL; neither suite substitutes for real container persistence, browser or device acceptance.

After Docker works, run the same suite plus PostgreSQL-only transaction tests in an isolated disposable database:

```powershell
docker compose --env-file .env.dev -f compose.dev.yml --profile test run --build --rm tests
docker compose --env-file .env.dev -f compose.dev.yml --profile test stop test-db
```

This test profile uses an ephemeral `istay_test` database, no published port, and a fresh schema for each test. It does not use development or production data volumes. Skips in the SQLite run are not evidence PostgreSQL invariants passed.

## Architecture and defaults

- API and UI share one origin through nginx, under `/api/v1`. PostgreSQL receives no public port mapping.
- Authentication uses random server sessions; only token hashes are stored. Cookies are HttpOnly/SameSite=Strict and Secure in production. CSRF requires the exact configured Origin and an in-memory token on mutations. Login requires Origin too. Unknown usernames get the same password-verification work. A database-backed account limiter allows ten login attempts per fifteen minutes.
- Role and site checks use live database state, not frontend claims. Audit/target/sync/report endpoints enforce site, assignment, role and state as appropriate. Reports require complete audit site access before filtering.
- Seed is idempotent and creates only initial sites/telcos. Admin creation is a local operator CLI. There is no public registration.
- Models include all minimum SPEC entities. Historical inspections/measurements/events are immutable in PostgreSQL, and deferred triggers enforce TESTED/measurement consistency. The initial schema is a frozen Alembic revision, not runtime `create_all`.
- API responses use `Cache-Control: no-store`; the PWA precaches static shell files only. Passwords, session and CSRF secrets are not stored in IndexedDB/localStorage. Downloaded assignments, limited account identity and immutable drafts are user-scoped. Offline Ready requires downloaded assignments and a cached production shell; drafts remain distinct from server ACKs.
- Exact resolved Python runtime versions and a pnpm lockfile are committed. Production build tooling resolves base images to digests and uses unique release tags. Do not overwrite a release tag.
- The current account limiter is per username rather than trusting forwarded IP headers. Before public use, configure an edge login rate limit and complete security review alongside later phases.

## Production preparation

Follow [OPERATIONS.md](docs/OPERATIONS.md). Production requires separate database administrator/app passwords in ignored secret files, final HTTPS hostname, pinned images, a working backup destination and an operator-created admin account. Cloudflare credentials never belong in `.env` values sent to frontend builds or in Git.

Production deployment is incomplete until local UI/API access, HTTPS authentication, persistence across restart/recreation, actual backup restoration, external Android access and offline save/reconnect/idempotent sync have passed. Desktop simulated-outage tests, an observed host reboot/logon and the real nightly backup/restore have passed. Android airplane-mode, real mobile-data SDK tests, external HTTPS and off-host backup retrieval remain pending.
