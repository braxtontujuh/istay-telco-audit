# Implementation and deployment checklist

Inspected 2026-11-11: upstream `main` contains SPEC.md only. No existing PWA or IndexedDB implementation exists.

Implement sequentially, validating each phase before describing it as complete:

- [x] Phase 1: runnable monorepo, development Compose, full schema/migrations, seed, server sessions/CSRF/RBAC and typed contracts.
- [x] Phase 2: dynamic layouts, scoped audit workflow, target snapshots/assignment and mobile navigation; PostgreSQL workflow tests passed.
- [x] Phase 3 implementation and desktop browser acceptance: cached relaunch after tab closure, user-scoped IndexedDB, offline capture, immutable outbox, independent ACK/idempotency/conflicts, account isolation and manager resolution. Android install/airplane-mode acceptance remains outstanding.
- [ ] Phase 4 final acceptance: pinned SDK 1.17.0, bounded/cancellable tests, metric validation, interrupted-attempt recovery and mocks implemented/tested; real Android SIM test outstanding.
- [ ] Phase 5 final acceptance: dashboard/coverage, scoped reports, six-sheet Excel and optional GHCR build workflow implemented; GitHub execution, external deployment and final device/operational gates outstanding.

Operational work:
- [x] Inspect host and upstream without changing settings.
- [x] Obtain explicit approval before WSL/Docker installation, nonsynced production staging and current-user startup task. Startup task manual run passed. No power changes or automatic reboot performed.
- [x] Separate dev/prod Compose projects, volumes and credentials; production database has no published ports. Verified in local production rehearsal.
- [x] Production restart policies, daily backup job, scratch restore and recovery instructions; API process-crash recovery passed. Off-host backup and Windows logon/reboot recovery remain pending.
- [x] Prepare Cloudflare Tunnel and private-network configuration. Real account/hostname/token still required from operator.
- [ ] Test development and production local access, authentication, restart/recreate persistence, backup restore, external HTTPS and Android offline sync.

Never equate generated configuration or passing static checks with a completed deployment.

Current verification: 44 PostgreSQL/Linux tests and 20 frontend tests passed, TypeScript/PWA production build passed. Synthetic desktop browser records synchronized exactly once; reports and Excel matched database counts. Local authentication, Secure-cookie HTTPS rehearsal, CSRF/logout, restart/recreation persistence, business-data backup restore and process-crash recovery passed. Nonsynced local production staging and approved logon-task manual execution passed. Rehearsal/staging use localhost-only certificates, not Cloudflare. No employee deployment is claimed.
