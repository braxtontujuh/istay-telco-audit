# I-Stay Telco Audit — Product & Engineering Specification (v2.1)

## Purpose and firm decisions
Build a production-oriented, mobile-first **Progressive Web App (PWA)** for staff to audit **mobile SIM-based 4G/5G Internet performance** inside corporate dormitory units, with an admin dashboard and exportable reports. The project is not a Wi-Fi signal strength monitor or fixed broadband speedtest.

- Sites: IP1, IP2, SAC, SILC (configurable).
- Audit scheduling: ad hoc, manager-initiated, with independent audit history.
- Users: individual employee accounts; roles ADMIN, MANAGER, AUDITOR.
- Audit requirement: one **completed inspection outcome per audit target**. Retests and failed attempts remain in immutable history.
- A target is uniquely identified by **audit + location + telco**. The same bedroom tested with two telcos creates two targets.
- Room layouts vary: units may have 2, 3, or other numbers of bedrooms plus a living room and optional custom spaces; support per-unit customization, configurable templates and bulk apply.
- Staff must be able to record NO_SIGNAL / NO_INTERNET **completely offline**, with eventual server synchronization.
- Actual Internet speed test uses `@cloudflare/speedtest` browser SDK while the phone is connected to the desired mobile-data SIM. Save Download Mbps, Upload Mbps, Ping ms, optional jitter, engine/version/profile and time.
- Browser cannot reliably verify active SIM, mobile network operator, true 4G/5G radio type, or enforce mobile data over Wi-Fi. Require staff confirmation (Wi-Fi off, right SIM selected, mobile data enabled); manually record telco and network generation (4G/4G+/5G/unknown). Label these values as staff-reported, not verified.
- Backend must not proxy speedtest traffic. Client measures directly against Cloudflare; FastAPI receives summary records.

## User roles and access
- ADMIN: manage sites, blocks, units, room templates, users, telcos, settings, all audits and reports.
- MANAGER: manage audits and assignments, view/export results for authorized sites; close/reopen audits.
- AUDITOR: view/download their assigned targets, run tests and submit inspection results and local offline queue; view own records.
- Backend must enforce role, site, assignment and audit status on every relevant API. Frontend hiding UI is not authorization.

## Inspection outcomes and counting
Use distinct inspection outcomes and synchronization states:
- TESTED: valid speedtest with complete download/upload/ping, counted as inspected and as successful speedtest.
- NO_SIGNAL: staff reports no mobile service, counted as inspected, no speed metrics (NULL).
- NO_INTERNET: staff reports mobile service but unusable internet, counted as inspected, no speed metrics (NULL).
- SPEEDTEST_FAILED: test could not complete, not counted as inspected until a conclusive follow-up (retain attempt).
- SKIPPED: inaccessible room or other reason, not counted as inspected.
Sync states (client-only): PENDING, SYNCING, SYNCED, RETRY, CONFLICT.
- Never convert NO_SIGNAL to 0 Mbps. Keep network issue outcomes separately in charts and coverage metrics.
- Use latest accepted conclusive inspection (TESTED / NO_SIGNAL / NO_INTERNET) per target to calculate current outcome, with entire attempt history retained. If a later retry is inconclusive, do not erase last conclusive observation. Document this policy in UI/reports.
- Inspection completion = number of targets with conclusive outcome / total targets. Speedtest success = targets whose latest conclusive outcome is TESTED / inspected targets. Show sample count and dates for telco comparisons. Ratings thresholds configurable per audit snapshot, not hard-coded global rules.

## Core hierarchy and admin configuration
sites -> blocks -> floors -> units -> test_locations (bedrooms, living room, custom). Keep site/block/unit identifiers as data, not hard-coded UI logic. Unit number is a display ID, location uses immutable primary key. An active audit snapshots selected targets; room layout changes do not silently mutate past audit target lists.

## Audit workflow
1. ADMIN/MANAGER creates DRAFT ad hoc audit, chooses authorized sites, blocks/floors/units, target telcos, assigns testers, and config snapshot (speedtest profile, thresholds).
2. Activate audit -> ACTIVE. Staff download assigned targets and app shell while online, obtain clear **Offline Ready** indication.
3. Staff navigate Site -> Block -> Floor -> Unit -> room -> telco; confirm correct SIM/mobile data/Wi-Fi off and (optional, manually reported) 4G/5G.
4. If connectivity works, run Cloudflare speedtest. Check complete numeric results; save inspection to IndexedDB first; sync to backend. Never mark green/server-saved until acknowledged.
5. If no service or no usable internet, choose NO_SIGNAL / NO_INTERNET and optional remarks; save to IndexedDB even with no network.
6. Move to next uncompleted room, including variable room counts.
7. Sync pending inspections when app opens/resumes, when online event occurs, on manual Sync Now, and optionally via Background Sync if supported. `navigator.onLine` is only a hint; verify actual API reachability.
8. Manager reviews progress/coverage and closes audit. CLOSED audit is read-only; late offline results become CONFLICT and require manager resolution with audit event, not silent acceptance.

Audit states: DRAFT -> ACTIVE -> COMPLETED (all targets inspected) -> CLOSED. Managers may reopen completed audits; closure with unresolved targets must require a reason. Keep audit event history.

## PWA and offline acceptance requirements
- React + TypeScript + Vite with PWA manifest, icons, and robust Workbox or Vite PWA Plugin service worker. Cache App Shell and essential static assets. Do NOT cache authenticated API responses as broadly public assets.
- IndexedDB through `idb` library; stores `audit_cache`, `target_cache`, `outbox`, `sync_metadata`, each scoped to logged-in user and version. Store no plaintext passwords, authentication secrets or sensitive cookies in IndexedDB.
- Before leaving connectivity, download all assigned audit targets and ensure assets are cached. Show Offline Ready, cached audit timestamp, pending count, and explicit local-vs-server-save indicators.
- Offline outbox items use a UUID `client_id` generated on creation, `target_id`, outcome, manually reported telco network type, remarks, device label, observed_at ISO timestamp, optional speed metrics, `retryCount`, and `syncStatus`. Keep immutable payload under the same UUID across retries.
- Use IndexedDB transaction to persist before displaying 'Saved on device'. Do not rely on service worker being able to start for an uncached first launch. Warn users that clearing browser/site storage or uninstalling app may destroy unsynced data.
- Each outbox record belongs to one user; switching user must not expose or sync previous user's records. Provide sync-before-logout warning. Protect offline audit detail appropriately on shared devices.
- Outbox sync: batch small groups (e.g. <=20), per-record ACK. Do not delete on HTTP timeout; retries use same UUID. Only clear after server ACK or retain a synced tombstone to assist UI. Use exponential backoff and manual retry. Do not treat `online` as guaranteed server access. App must still function offline after first successful setup.
- If an audit closes or access is revoked while offline, mark CONFLICT and show resolution instructions; never silently bypass permissions.
- Server must verify client IDs, target assignment, audit state and payload, and enforce idempotency even under concurrent retries. Same UUID + same payload -> same saved record; same UUID + different payload -> 409 conflict. If batch includes invalid records, return independent status for each item.
- Timestamps: save observed_at on client and received_at on server; do not assume device clock is precise; use server timestamp for auditing and flag skew.
- For TESTED outcome, prevent user from manually fabricating success through ordinary UI. API cannot cryptographically attest mobile network; document this limitation.

## Technical stack
Frontend React + TS + Vite + Tailwind + TanStack Query + React Router + Zod + idb + @cloudflare/speedtest + PWA plugin. Backend Python FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2. DB PostgreSQL. Reporting openpyxl. Docker Compose; cloudflared Tunnel. GitHub Actions builds images to GitHub Container Registry (GHCR), optionally deploys to Windows 11 Docker host (HP ProDesk) using a controlled pull/restart with rollback.

Recommended dev: frontend, backend, postgres, plus reverse proxy (Caddy/Nginx) to host PWA and `/api` under one HTTPS origin. Production: pin image versions/digests, no exposed DB port, use HTTPS, `.env` never committed, backups to a separate device/location, healthchecks, migration before rollout, logging without credentials, recovery test.

## Data model
Use SQLAlchemy models + Alembic migrations, not ad hoc production CREATE TABLE scripts. Minimum entities:
- sites(id, code UNIQUE, name, active)
- blocks(id, site_id FK, code, UNIQUE(site_id,code))
- floors(id, block_id FK, floor_no, UNIQUE(block_id,floor_no))
- units(id, floor_id FK, unit_no, active, UNIQUE(floor_id,unit_no))
- test_locations(id, unit_id FK, code, name, sort_order, active, UNIQUE(unit_id,code))
- room_templates, room_template_items (for default layouts and bulk apply)
- telcos(id, name UNIQUE, active); seed CelcomDigi, Maxis, U Mobile, Yes 5G, Unifi Mobile, Other (editable)
- users(id, username UNIQUE, full_name, password_hash, role, active, created_at)
- user_site_access(user_id, site_id, PK pair)
- audits(id, title, status, created_by, created_at, activated_at, closed_at, config_snapshot JSONB, closure_note)
- audit_targets(id, audit_id, location_id, telco_id, UNIQUE(audit_id,location_id,telco_id), additional composite uniques for scoped FKs)
- audit_assignments(id, audit_id, user_id, assigned_by)
- assignment_targets(assignment_id, audit_id, target_id) with constraints ensuring assignment and target refer to same audit
- inspection_records(id, client_id UUID UNIQUE, target_id FK, user_id FK, outcome, network_type, mobile_data_confirmed, device_label, remarks, observed_at, received_at, source, payload_hash)
- speed_measurements(inspection_id PK/FK, download_mbps>=0, upload_mbps>=0, ping_ms>=0, jitter_ms nullable, duration_ms, engine, engine_version, profile_version, raw_summary JSONB)
- audit_events(id, audit_id, actor_id, action, details JSONB, created_at)
- app_settings(key, value JSONB)

Require transaction-level invariant: TESTED has valid one-to-one measurement; non-TESTED does not. No cascading deletion of historical audit records. Index targets by audit and inspections by target/time. Use database uniqueness/authorization and atomic transaction for batch sync. Avoid making identity of a target depend on mutable room label.

## REST API under /api/v1
Auth: POST /auth/login, POST /auth/logout, GET /auth/me, POST /auth/change-password.
Buildings: GET /sites, GET /sites/{site_id}/blocks, GET /blocks/{block_id}/floors, GET /floors/{floor_id}/units, POST/PATCH /units, GET/POST /units/{unit_id}/locations, PATCH /locations/{id}, POST /units/import, GET /telcos; admin templates CRUD and apply endpoint.
Audits: POST /audits, GET /audits, GET/PATCH /audits/{id}, POST /audits/{id}/targets, POST /audits/{id}/assignments, POST /audits/{id}/activate, POST /audits/{id}/reopen, POST /audits/{id}/close, GET /audits/{id}/targets, GET /audits/{id}/progress.
Inspections: POST /inspections, POST /inspections/batch-sync, GET /audit-targets/{id}/history, GET /audits/{id}/results.
Reports: GET /dashboard/summary, GET /audits/{id}/coverage, GET /audits/{id}/weak-locations, GET /audits/{id}/export.xlsx.
Operations: GET /health/live (public minimal), GET /health/ready (controlled), GET /openapi.json.

Example offline inspection payload:
```json
{
  "client_id":"847eb2d4-68b2-497e-8bcc-a6ae236600d8",
  "target_id":1359,
  "outcome":"NO_SIGNAL",
  "network_type":"UNKNOWN",
  "mobile_data_confirmed":true,
  "device_label":"Samsung Galaxy A54",
  "observed_at":"2026-11-11T03:28:00Z",
  "remarks":"Phone shows No Service in Bedroom 3",
  "measurement":null
}
```

Example completed test payload:
```json
{
  "client_id":"26fe54b0-9322-43a7-ac49-eb65e8e379cd",
  "target_id":1358,
  "outcome":"TESTED",
  "network_type":"5G",
  "mobile_data_confirmed":true,
  "observed_at":"2026-11-11T03:25:00Z",
  "measurement":{
    "download_mbps":35.8,
    "upload_mbps":12.5,
    "ping_ms":28.4,
    "jitter_ms":6.2,
    "duration_ms":19500,
    "engine":"cloudflare",
    "profile_version":"mobile-v1"
  }
}
```
Server gets user identity from HttpOnly server session; do not accept arbitrary user IDs for authorization. `source` should be determined/validated server-side and is not a security assertion.

Batch sync request: `{ "records": [ ... ] }` with individually reported results: `client_id`, `status` (SYNCED/RETRY/CONFLICT), `server_id` or `error` (machine code + message). Document maximum batch size and partial success semantics. Endpoint should return proper 400/401/403/409/422/429 codes as appropriate, and a stable JSON error schema.

## UI routes
User: `/login`, `/app`, `/app/audits/:id`, `/app/audits/:id/units`, `/app/targets/:id`, `/app/history`, `/app/sync`.
Admin/manager: `/admin`, `/admin/sites`, `/admin/units`, `/admin/room-templates`, `/admin/telcos`, `/admin/users`, `/admin/audits`, `/admin/audits/:id`, `/admin/coverage`, `/admin/reports`, `/admin/settings`.
- Mobile inspection screen: clearly show site/block/floor/unit/room/telco; confirm Wi-Fi OFF and mobile data correct; Start Speed Test and distinct manual No Signal/No Internet flow; manual remarks; Next Room; local save/sync indicators.
- Do not offer a manual 'TESTED' button. Only valid SDK results create TESTED in normal UI.
- Dashboard: target totals, inspected, pending, tested, no signal, no internet, skipped, failures and offline pending (device-local), floor heatmap, telco comparisons, latest results, full history.
- Excel sheets: Summary, Telco Comparison, Latest Results, No Signal-No Internet, Pending Targets, All Attempts. Make it evident that averaging only successful tests produces survivorship bias; always display tested counts and issue rates.

## Cloudflare speed test implementation
- Install/pin `@cloudflare/speedtest` and verify its actual TypeScript API for installed version; use `autoStart:false`, `play()`, `onFinish`, `onResultsChange`, `onError`, `pause()` if available. Do not assume every error is fatal; validate final measures.
- `getDownloadBandwidth()` and `getUploadBandwidth()` are in bits per second; convert to Mbps dividing by 1e6. Use unloaded latency (ping) in ms. Capture speedtest profile/version and duration if available.
- An Internet test cannot run while offline. NO_SIGNAL/NO_INTERNET records can be manually entered offline. Do not assume app detects radio status itself.
- Browser SDK cannot authenticate actual carrier/SIM/wireless generation; in UI mark these 'staff selected/confirmed'.
- Implement cancellation, duplicate-click suppression, interrupted page handling, bounded tests/configurable timeout, and save-then-sync (locally) with meaningful error messages.
- Distinguish Internet speed from raw RF signal strength; no RSSI/dBm promised in v1.

## Security
- Server-side session via Secure HttpOnly SameSite cookies, CSRF protection on mutations, password hashing Argon2id, proper logout/revocation, session expiry, per-site RBAC, rate-limiting, input validation and audit logging.
- Do not embed Cloudflare Tunnel secret, DB passwords or other tokens in client bundle or git.
- IndexedDB outbox not automatically encrypted; protect shared devices, avoid storing private credentials, require sync before logout, provide secure cleanup controls after sync.
- For devices with no network and stale login session, support local draft capture only for pre-cached authorized assignments; server makes final decision at sync. Never tell staff that a local draft is server-verified.

## Acceptance tests (must be automated where possible)
1. Create unit with 2 bedrooms + living room, and another with 3 bedrooms + living room; target counts are 3 and 4 respectively per telco.
2. Same bedroom with two telcos creates two distinct targets.
3. Load PWA online + cache an assigned audit; go airplane mode; app launches and records NO_SIGNAL locally with clear 'Saved on device / Pending sync'.
4. Restore connectivity; batch sync creates one server record; retry same UUID doesn't duplicate it.
5. Same UUID and modified payload returns conflict; per-record errors do not abort whole batch.
6. No Signal / No Internet count as inspected; failed attempts and skipped don't; no signal never enters numeric avg as zero.
7. Submit valid speed test metrics; validate Mbps unit conversion, optional jitter, and no manual success UI.
8. Revoke site permission while employee offline; sync yields CONFLICT rather than silently saving.
9. Close audit before offline sync; sync yields CONFLICT and manager workflow.
10. Logout/switch user on shared device; cached records of prior user aren't exposed/synced under next account.
11. Multiple employees sync concurrently; no duplicated records or incorrect counts.
12. Excel exports match DB totals and filter by site permissions.
13. Docker Compose development stack starts, migrations run, PWA works under HTTPS in deployed environment, backups restore successfully.

## Phased Codex implementation plan
Phase 1: scaffold monorepo, Docker dev stack, backend models + migrations + seed sites/telcos, auth/RBAC, typed API contracts, tests.
Phase 2: unit dynamic room layouts, ad hoc audit creation/target snapshots/assignments, mobile UI navigation.
Phase 3 (highest priority): PWA install, service worker, offline-ready, IndexedDB outbox, manual NO_SIGNAL/NO_INTERNET, sync API idempotency and conflict tests; fully test offline.
Phase 4: Cloudflare SDK integration with mocks and real-device validation; result UI and history.
Phase 5: management dashboard, coverage reports, Excel export, CI/CD, secure production deployment and docs.

## Instructions to coding agent
- First inspect repo, identify existing code, and write a short implementation plan / task checklist. Do not replace existing work without examining it.
- Implement one phase at a time. For each phase, write actual runnable code and tests, run test suite/build/migrations, report changed files and commands/results.
- Prefer small, reviewable commits/PRs. Keep TODOs explicit. Do not claim deployment, offline verification or live mobile speed testing without actually performing it.
- If a specification item requires a design decision, choose a secure and simple default and document it in README rather than blocking on unnecessary questions.
