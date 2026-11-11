# Production preparation, backup and recovery

**Not an employee deployment.** Production configuration was exercised in an isolated `istay-rehearsal` project with separate data, localhost-only HTTPS and no Cloudflare connector. Authentication/persistence, backup restore and process-crash recovery passed there; see VERIFICATION.md. Complete the app phases and remaining acceptance gates before employees use it. Work from an approved nonsynced production directory on this HP. Commands below are operator procedures unless the verification record explicitly says otherwise.

The operator has now approved and created a separate nonsynced `istay-prod` local staging instance while deferring Cloudflare. See [LOCAL-STAGING.md](LOCAL-STAGING.md) for its loopback-only TLS, separate credentials, permanent-admin setup and logon task. This is still not an external employee deployment.

## Required configuration and credentials

| Item | Source / storage |
| --- | --- |
| Windows administrator approval | WSL/Windows features, software installation and any power/startup changes |
| Ubuntu username/password | Chosen privately on first distro launch |
| Docker license eligibility | Operator reviews Docker terms before use |
| `.env.dev` | Generated random development DB password; ignored by Git |
| `.env.prod` | Final HTTPS origin, allowed hostnames, exact image refs, DB names and backup path; ignored |
| `secrets/production/db_admin_password.txt` | Random bootstrap administrator password; not used by the API |
| `secrets/production/db_password.txt` | Different random non-superuser application/backup password |
| Administrator app account | Created interactively using CLI; no default account/password |
| Cloudflare account/domain and tunnel token file | Operator creates/configures; see CLOUDFLARE.md |
| Off-host backup destination and access | Separate device, protected share or approved backup provider; not configured yet |

Generate files with `./scripts/New-LocalConfig.ps1 -Environment Production`. The script never prints passwords or overwrites existing secrets. Protect `.env`/secret/backup files with Windows ACLs, store credentials in a password manager, and keep recovery copies securely off this PC. File-based Compose secrets are mounts, not encrypted secret storage. Do not change an initialized DB password by editing a file alone: rotate its SQL role password and the file together during a planned maintenance window.

The database init script creates a distinct non-superuser application role only for an **empty volume**. Do not delete a volume to apply a configuration change. Resolve initialization failures deliberately and preserve existing data. The API/migration role owns the application's schema; it has no cluster superuser, role creation or database creation permission. Backup uses this role; isolated restore tests use the separate administrator secret.

## Build and stage

```powershell
./scripts/Build-Production.ps1 -Release your-unique-release-name
```

The script pins PostgreSQL 17, Python, Node, nginx and cloudflared base references by digest. API/web/backup images have a unique local release tag. Copy its five image references from `releases/<release>.json` into `.env.prod`; retain previous manifests/images for rollback. Check image security updates before promoting releases; never switch PostgreSQL major versions by changing a tag.

Set `APP_ORIGIN=https://<real-domain>` with no trailing slash; set explicit `TRUSTED_HOSTS` and a real backup staging directory that already exists. Ensure app/admin database usernames differ. Do not commit credentials or fill placeholders into a client build. The production frontend always calls same-origin `/api/v1`.

A verified GHCR release is now recorded in `releases/ghcr-9b37796bc4a7.json`, built from main commit 9b37796bc4a7be66ee5521edb28ca6a3f2345bb9. Remote tests/publication and digest-based pull/artifact checks passed. Do not substitute these references into the running environment merely because publication succeeded: the current HP still uses its tested local release. Apply a candidate only through backup/migration/healthcheck/rollback procedures when the final origin is configured. A fresh host may require private-package read credentials; no registry credential belongs in frontend configuration or Git.

```powershell
docker compose --env-file .env.prod -f compose.prod.yml config --quiet
docker compose --env-file .env.prod -f compose.prod.yml up -d db
docker compose --env-file .env.prod -f compose.prod.yml run --rm migrate
docker compose --env-file .env.prod -f compose.prod.yml run --rm --no-deps api python -m app.cli seed
docker compose --env-file .env.prod -f compose.prod.yml run --rm --no-deps api python -m app.cli create-admin
./scripts/Start-Production.ps1
docker compose --env-file .env.prod -f compose.prod.yml ps -a
```

Never run `docker compose down -v`, `docker volume prune`, Docker Desktop factory reset or unregister the Docker WSL distro on a host containing needed data. `down` without `-v` preserves the named volume. Development and production use different Compose project names and volumes, `istay-dev_pgdata` and `istay-prod_pgdata`; keep these names stable.

Use http://localhost:8080 for the local production shell and public liveness endpoint. **Production login requires the final HTTPS origin** because its cookie is Secure and origin is strict; do not disable that to make HTTP login appear to work. Test local development authentication at localhost:8081, then production authentication at the external HTTPS origin.

The backup service starts with the stack. Start the tunnel only after credentials, full app behavior and external-access approval are ready; see CLOUDFLARE.md. This foundation is not employee-ready even if the containers are healthy.

## Isolated local rehearsal

`compose.rehearsal.yml` overlays production with TLS on `127.0.0.1:8443`, using ignored short-lived files under `secrets/rehearsal-tls`. `.env.rehearsal` uses the `istay_rehearsal` database and a separate staging directory; `-p istay-rehearsal` creates its separate volume. Never use rehearsal credentials/certificates for employees. The test CA is trusted explicitly by the Python test client only; it was not installed in Windows/browser trust. A browser certificate warning must not be bypassed to claim successful browser HTTPS testing.

Prepared checks: `python scripts/verify-dev.py` tests the localhost development stack with disposable data. `python scripts/verify-dev.py --rehearsal` tests Secure cookies and persistence with CA-verified localhost HTTPS. `python scripts/verify-rehearsal-recovery.py` intentionally crashes only the rehearsal API and checks automatic recovery and response headers. These scripts require the workspace Python test dependencies. Certificate generation uses `cryptography` (available in Codex's bundled Python); it does not install trust or write a reusable CA signing key.

## Persistence verification (Docker required)

1. Inspect the DB mount with `docker volume inspect istay-prod_pgdata` and confirm the Compose DB service has no `ports` entry.
2. Create an authenticated admin and a harmless known record (initial sites/telcos are also suitable). Query/count them through the API and DB. Record the expected values.
3. Run `docker compose --env-file .env.prod -f compose.prod.yml restart db api`; wait for DB health and confirm the same records and login remain valid.
4. Run `docker compose --env-file .env.prod -f compose.prod.yml up -d --force-recreate db api`; confirm the same known records again. Never add `-v` or remove the named volume.
5. Reboot only after separate approval, log in to Windows, start Docker, and verify the same records and services. This is a distinct host recovery gate.

Record actual commands, timestamps and results in VERIFICATION.md. A declared volume alone does not prove persistence.

## Daily backups

The backup container uses PostgreSQL 17 `pg_dump --format=custom --no-owner --no-acl` over the private network. It runs at startup and once daily at/after **19:00 UTC / 03:00 Malaysia time**. Missed jobs catch up after Docker starts. Failures retry every minute. A dump is finalized only after both dump and archive-list checks succeed, with SHA-256 checksum and atomic last-success marker. Retention defaults to 30 days, pruning only this application's finalized files after a successful new backup.

Backups are readable database copies, not encrypted archives. Store them on protected storage. `BACKUP_DIR=./backups/production` is **same-host staging only**. It does not protect against PC/disk loss. Before production, configure a reliable second copy to a different device/location, its credentials, encryption, retention and failure alerts. Verify a restore using a file retrieved from that destination. This part remains manual until a destination is chosen. Docker volumes and cloud sync of live database files are not substitutes for database backups.

Trigger a backup and inspect health:

```powershell
docker compose --env-file .env.prod -f compose.prod.yml exec backup sh /opt/backup/backup.sh
docker compose --env-file .env.prod -f compose.prod.yml logs --tail 50 backup
docker compose --env-file .env.prod -f compose.prod.yml ps backup
```

Do not overlap manual backup runs. A stale last-success marker makes the container unhealthy after 26 hours; this is visibility only, not an external alert. Configure independent monitoring and test alert delivery before production.

## Restore test

Choose the basename of a finalized file under BACKUP_DIR:

```powershell
docker compose --env-file .env.prod -f compose.prod.yml --profile operations run --rm restorecheck istay-YYYYMMDDTHHMMSSZ.dump
```

The restore job verifies its checksum, creates a fresh `istay_restore_<time>_<pid>` database, runs `pg_restore --exit-on-error`, queries migration/user/inspection counts, and drops only that generated scratch database. It never replaces the live database. Verify representative restored business records as the application grows; successful archive listing alone is not a restore test. A killed process can leave a scratch database; inspect names and ownership before manual cleanup.

For real disaster recovery, stop application writers, preserve the damaged volume, create a **new** production volume/project, initialize roles, and restore the selected verified dump into a blank database. Match PostgreSQL major version and application migration revision. Rehearse the procedure and record the selected recovery point before replacing any live instance. Do not blindly downgrade schema or restore over live users.

## Updates and recovery

1. Run tests/builds and create a new unique release. Take and verify a backup before migrations.
2. Record current image refs/schema revision and the rollback plan. Run migrations as a one-shot job; do not roll out API if it fails.
3. Start the new API/web images and run authenticated readiness and acceptance checks. Preserve prior images and backups.
4. For a compatible code-only rollback, restore previous API/web refs in `.env.prod` and recreate those services. A destructive/incompatible migration needs a separately approved data restore plan; old code is not guaranteed to work on a new schema.

`restart: unless-stopped` handles process exits and engine restart after Docker returns. It respects manually stopped containers, does not restart unhealthy processes automatically, and cannot recover while the PC is asleep/off. The operator-approved `IStay-Production-AtLogon` task is installed for localhost-only staging; manual invocation and an observed reboot/logon passed. It runs with the current user's Limited/Interactive logon and does not provide availability before Windows sign-in. Switching it to the final origin/tunnel remains part of Cloudflare rollout. No power setting, inbound firewall rule or router port forward was changed. See LOCAL-STAGING.md for the native CMD launcher and verified task details.

Logs are rotated (three 10 MB files per service) and API access logs are disabled to avoid logging sensitive requests. Inspect restricted diagnostics for failures; do not publish logs containing tokens or personal data.
