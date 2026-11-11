# Verification record

Date: 2026-11-11, Asia/Kuala_Lumpur. **Not a completed deployment.**

| Gate | Status / evidence |
| --- | --- |
| Repository inspection | Passed: upstream contains SPEC.md only |
| Hardware/OS inspection | Passed: HP ProDesk 400 G7, i5-10500, Windows 11 Pro 25H2, 8 GB RAM, ~398 GiB free |
| WSL installation | Passed: WSL 3.0.5 installed after approval; no automatic reboot |
| WSL2 + Ubuntu execution | Passed: docker-desktop and Ubuntu-24.04 listed as VERSION 2; Ubuntu uname confirms WSL2 kernel. Normal Linux user setup remains manual |
| Docker Desktop / Compose | Passed: approved supported per-user installation, Desktop 4.99.0, Engine 29.9.3, Compose v5.7.0; Linux engine and hello-world passed |
| Backend unit/integration tests | 39 passed against disposable PostgreSQL, no skips, 28.25 seconds. Includes dynamic layouts, snapshots, independent ACKs, concurrent UUIDs, closure/revocation, report/export scope and counts. One upstream Starlette/httpx deprecation warning |
| PostgreSQL-specific migrations/triggers | Passed: actual migrations, deferred TESTED/measurement pairing, non-TESTED measurement rejection, immutable history and cross-audit foreign keys |
| Frontend type-check/build/PWA shell | Passed: TypeScript/Vite production build, 12 static precache entries (~506 KiB); 20 tests for owner isolation, atomic claims/ACKs/retries, known closure/revocation, interrupted tests, SDK unit conversion/cancellation/timeout/partial results |
| Python lint / PowerShell syntax | Passed: ruff checks and parsing all prepared .ps1 scripts |
| Compose CLI configuration validation | Passed with installed Compose plugin, all dev/test/prod/tunnel/operations profiles. Earlier portable validator was blocked by Windows Application Control; no policy bypass performed |
| Local development access | Passed via HTTP client: localhost:8081 shell/API, login, authorized sites, readiness, CSRF rejection, logout. Temporary test account removed; permanent admin creation is manual |
| Production local access | Passed in isolated istay-rehearsal project, localhost:8443 only, separate volume; all long-running rehearsal services healthy |
| Final local release rehearsal | Built pinned phase5-local-20261111 images and updated isolated rehearsal after a verified backup. Repeated CA-verified HTTPS authentication, restart/recreation record/session persistence, CSRF/logout, backup/scratch restore and process-crash recovery passed. This is not the external production deployment |
| Production HTTPS authentication | Passed locally using client-specific trusted test CA (certificate verification enabled), Secure/HttpOnly cookie, CSRF and logout. Not external Cloudflare/browser HTTPS verification |
| Database restart/recreation persistence | Passed in dev AND rehearsal: known DB probe/user/session survived restart and force-recreate of DB/API. No volume deletion used; probes/users cleaned up |
| Database role/network isolation | Passed: app role istay has rolsuper=False, rolcreatedb=False, rolcreaterole=False. No host DB port mapping; dev/rehearsal named volumes differ |
| Daily backup execution and real restore | Manual pg_dump/checksum/pg_restore passed again on phase5 release: istay-20261111T132726Z.dump restored to isolated scratch DB, revision 0001, 4 sites, 6 telcos, 0 users/inspections. Scratch DB removed. Daily 03:00 MYT schedule configured; a full daily cycle has not elapsed. Backup startup waits for migration. A restore containing actual business inspections still needs final employee acceptance data |
| Container process recovery | Passed: killed only rehearsal uvicorn process; Docker restart count increased and verified HTTPS liveness recovered automatically |
| Windows startup task | Approved current-user IStay-Production-AtLogon registered in the nonsynced directory with Limited/Interactive logon, no tunnel. Native CMD launcher used because Windows PowerShell .ps1 execution is Restricted; no execution policy was changed. Manual task run passed (LastTaskResult=0), all local production services healthy. Real reboot/logon remains untested; no automatic reboot |
| Nonsynced production staging | Approved and created C:\Users\braxt\IStayTelcoAudit with restricted ACL, new independent DB credentials and istay-prod_pgdata. Local-only TLS 8444, production Secure cookies; CA-verified login/readiness, restart/recreation persistence, CSRF/logout passed with a disposable account. Final Cloudflare origin remains deferred; no browser trust installed |
| Browser visual verification | Passed in attached in-app desktop browser after native Brave access had timed out. Login/audit/target/queue screens exercised; 375px mobile viewport had no horizontal overflow. Screenshot docs/evidence/phase3-sync-mobile.png. This is not Android device verification |
| External HTTPS/Android access | Blocked: no Cloudflare account/domain/tunnel configured |
| Desktop cached PWA outage/reconnect | Passed: stopped only isolated istay-browser-test web/API; captured synthetic NO_SIGNAL, refreshed cached shell, locked/switch accounts, closed audit before sync -> retained CONFLICT; manager reopened -> ACK record 1; retries did not duplicate. Updated PWA safely, closed old tab, launched fresh cached tab while services stopped, saved NO_INTERNET, restarted services -> ACK record 2. DB has two unique UUIDs, no speed measurements. Evidence docs/evidence/phase4-browser-database.json |
| Android install/airplane-mode/reconnect | Not tested; requires phone and stable external HTTPS origin. Desktop server-outage simulation does not pass this gate |
| Cloudflare SDK integration | Implemented pinned 1.17.0 after inspecting installed API. Browser confirms mobile-data/data-use consent required before starting; mocks validate metrics/partial failure/cancellation/timeout. Running markers preserve failed interrupted attempts. No desktop test is claimed as a SIM speed test |
| Real mobile SIM speed test | Not tested; requires Android mobile data, correct SIM selection, staff confirmation and HTTPS |
| Management reports and Excel | Passed against PostgreSQL: latest-conclusive policy/counts, thresholds, issue rates, null no-service metrics, sample counts/dates, six sheets, formula-safe strings, auditor denial and manager site revocation. Browser report/telco filter/download passed; downloaded C:\Users\braxt\Downloads\istay-audit-1.xlsx reopened with six sheets and two accepted attempts. Synthetic fixture totals matched UI/JSON/Excel: 3 targets, 2 inspected, 1 pending. Screenshot docs/evidence/phase5-report-browser.png |
| Prepared GitHub CI/GHCR | Workflow YAML parsed; official checkout action pinned by verified commit. PostgreSQL/frontend/container-build jobs and manual main-only GHCR publication prepared. No push, remote workflow run, GHCR publish or automatic HP deployment performed |
| Off-host backup/retrieval | Blocked: no destination chosen |
| Backup with business history | Passed: same-host dump istay-20261111T134751Z.dump restored into scratch DB with synthetic completed audit, frozen unit/room labels, accepted TESTED and NO_SIGNAL records. Exact TESTED UUID/hash/download/upload/ping/profile values verified. Synthetic bootstrap admin disabled. Evidence docs/evidence/business-backup-restore.json |

## Next acceptance work (do not mark passed without evidence)

- Create permanent administrator interactively; complete normal Ubuntu user setup and review Docker licensing.
- Complete real Android/SIM acceptance; final local browser report/filter/download checks have passed.
- Run the prepared CI in GitHub after source review/publication; local test/build passes do not prove remote workflow execution.
- Move actual production source/secrets to an approved nonsynced location before employee use; pinned rehearsal release manifests are under releases/.
- Choose an off-host destination, configure protected replication/alerts and retrieve/restore a copy from it. Observe the daily job after the next scheduled run.
- Configure stable Cloudflare HTTPS hostname, authenticate from an Android phone on another network and test real cookie/CSRF behavior.
- On Android, cache assigned targets online; airplane-mode relaunch/capture; reconnect/retry same UUID; verify exactly one server record. Repeat closed/revoked conflicts, account switching and unsynced-logout checks already covered on desktop/automated tests.
- Test approved logon/reboot recovery and service crash behavior. Record limitations and alerting.

No production employee data or external account credentials were imported. Generated rehearsal database passwords, local certificates and backups are ignored by Git and are test artifacts; they are not a production credential/recovery plan.
