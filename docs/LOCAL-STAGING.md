# Nonsynced local production staging

Cloudflare setup is deliberately deferred by the operator. This phase prepares the production data/services without claiming external deployment or browser-trusted HTTPS.

On 2026-11-11 the operator approved creating `C:\Users\braxt\IStayTelcoAudit` and registering a current-user logon task after tests passed. Source was copied there without `.git`, workspace runtime configurations, test passwords, database files or backups. New independent app/admin database passwords were generated in that folder. Its DACL permits the owning Windows user, SYSTEM and Administrators; inherited broad read access was removed. Source/development remains in the original workspace.

The independent `istay-prod` project uses `istay-prod_pgdata`. PostgreSQL publishes no host port. `.env.prod` retains a placeholder external origin until Cloudflare is configured. `.env.local-staging` and `compose.local-staging.yml` temporarily use `https://localhost:8444`, bound to loopback only, with Secure session cookies and the same production images. Its seven-day test certificate is trusted explicitly by the verification client only. No Windows/browser trust store was changed; do not bypass a browser certificate warning. This URL is not an employee remote URL.

Scripts:

```powershell
# Initial staging only; refuses to overwrite an existing deployment.
./scripts/Stage-Production.ps1 -Destination "$env:USERPROFILE\IStayTelcoAudit" -Release phase5-local-20261111 -CertificatePython python

# From the staged directory:
./scripts/Start-Production.ps1 -LocalOnly
./scripts/Create-Admin.cmd
./scripts/Install-RecoveryTask.ps1 -LocalOnly
```

Certificate generation requires Python with cryptography. On this HP the existing bundled runtime was used; no additional system Python was installed. `Stage-Production.ps1 -WhatIf` prints the plan without changing files. `-ResumeEmpty` is restricted to an empty folder left by an interrupted first attempt; it never overwrites populated production files or credentials. OneDrive cloud placeholders are read as files, while symbolic links/junctions are rejected.

The permanent username is `admin`; the operator chooses its password privately in the interactive terminal. No default password is seeded. Employee accounts are created later through the admin UI. Never send passwords/tunnel tokens in chat or commit them.

`IStay-Production-AtLogon` runs under the current user with Limited privileges and Interactive logon, launching `Start-Local-Staging.cmd`. Windows PowerShell's default Restricted policy blocked .ps1 task execution, so the local task uses native CMD/Docker commands; no policy was changed. The launcher starts Docker Desktop only if the engine is unavailable, waits up to ten minutes and starts the local-only stack. Its last startup output is in restricted `logs/local-startup-last.log`. A manual task run passed with LastTaskResult=0 and healthy services.

The task requires Windows sign-in after boot. It does not enable automatic Windows login or availability before sign-in. Real reboot/logon remains a separate acceptance check. AC sleep was already disabled (`STANDBYIDLE=0`); no power setting was changed. Full reboot remains operator-controlled; this work does not reboot automatically. Local staging certificates expire after seven days; configure Cloudflare before relying on this environment long term or renew deliberately. Task/container health alone does not verify certificate validity.

The same-host backup job runs at/after 03:00 MYT while Docker is running and catches up after startup. The operator currently has no separate-device backup destination, so off-host copying/retrieval and independent alert delivery remain pending. There is no claim of disk-loss protection or a fully observed daily schedule yet.

Before enabling external production: preserve `istay-prod_pgdata`, take/verify a backup, set the real origin/hosts and tunnel token in the nonsynced directory, switch to `.env.prod` without the local TLS overlay, update the approved recovery task to final production mode, then perform Android external HTTPS/auth/PWA/SIM acceptance. Do not create a new project/volume and accidentally abandon the staged admin/data. Rehearsal certificates are never promoted to the public domain.
