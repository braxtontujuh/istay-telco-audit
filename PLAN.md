# Implementation and deployment checklist

Inspected 2026-11-11: upstream `main` contains SPEC.md only. No existing PWA or IndexedDB implementation exists.

Implement sequentially, validating each phase before describing it as complete:

- [x] Phase 1: runnable monorepo, development Compose, full schema/migrations, seed, server sessions/CSRF/RBAC and typed contracts.
- [x] Phase 2: dynamic layouts, scoped audit workflow, target snapshots/assignment and mobile navigation; PostgreSQL workflow tests passed.
- [x] Phase 3 implementation and desktop browser acceptance: cached relaunch after tab closure, user-scoped IndexedDB, offline capture, immutable outbox, independent ACK/idempotency/conflicts, account isolation and manager resolution. Operator confirmed Android cached airplane-mode opening; Android installation and record capture/reconnect/ACK remain outstanding.
- [ ] Phase 4 final acceptance: pinned SDK 1.17.0, bounded/cancellable tests, metric validation, interrupted-attempt recovery and mocks implemented/tested; real Android SIM test outstanding.
- [ ] Phase 5 final acceptance: dashboard/coverage, scoped reports, six-sheet Excel, main/PR CI and GHCR publication passed. Public HTTPS/authentication/persistence and mobile-data login passed; Android record sync/PWA installation/SIM/off-host gates remain outstanding.

Operational work:
- [x] Inspect host and upstream without changing settings.
- [x] Obtain explicit approval before WSL/Docker installation, nonsynced production staging and current-user startup task. Startup task manual run passed. No power changes or automatic reboot performed.
- [x] Separate dev/prod Compose projects, volumes and credentials; production database has no published ports. Verified in local production rehearsal.
- [x] Production restart policies, real daily backup execution, scratch restore and recovery instructions; API process-crash recovery and observed host reboot/logon passed. Off-host backup remains pending because no destination is available.
- [x] Configure Cloudflare Free, approved nameservers, private token, Healthy edge-only tunnel and network.mrbraxton.net route; enable HTTPS redirect/cache bypass and final Limited/Interactive logon task. Final-task manual run returned 0. Approved PWA manifest MIME patch deployed with all static assets preserved.
- [ ] Complete final acceptance: dev/production access, external HTTPS auth, restart/recreate persistence, backup restore, Android mobile-data login and cached airplane-mode opening passed. Android record capture/reconnect/server ACK is deferred after the operator declined synthetic test history; PWA install/SIM/off-host checks remain pending.

Never equate generated configuration or passing static checks with a completed deployment.

Current verification: 44 PostgreSQL/Linux tests and 20 frontend tests passed, TypeScript/PWA builds passed. Synthetic desktop records synchronized exactly once; reports/Excel matched database counts. Approved production Cloudflare HTTPS/authentication, CSRF/logout, record/session persistence after restart/recreation, final-task execution, and same-host backup restoration passed. Operator-confirmed Android online login and cached airplane-mode opening passed. The final backup restored one user, four sites, six telcos and zero inspections. No completed employee rollout is claimed.
