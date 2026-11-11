# Application workflow and acceptance limits

The app now implements dynamic layouts, scoped audits, offline capture/sync, the pinned Cloudflare SDK, management coverage and six-sheet Excel exports. External employee deployment is still pending. See VERIFICATION.md for actual checks.

## Staff and offline work

1. Sign in with an individual account. On a personal, protected phone, opt in to reopening your downloaded workspace. Use shared devices online only.
2. Open an assigned active audit and choose **Download / refresh my assignments**. Wait for **Offline Ready**. This requires both user-scoped assignments in IndexedDB and an active worker with the current static shell cached. Vite development mode does not install the production worker.
3. Select the correct telco SIM, disable Wi-Fi, enable mobile data and confirm those steps. The browser cannot verify SIM, carrier or actual radio generation. Network type is staff reported.
4. Save No Signal / No Internet even without connectivity. No numeric speed is attached. Skipped and failed attempts remain history but do not complete a target.
5. A speed test contacts `https://speed.cloudflare.com` directly, never through FastAPI. SDK 1.17.0 uses an explicit mobile-v1 profile, 10–120 second audit timeout, cancellation and disabled result-logging endpoints. Configured test requests total about 34.2 MB before overhead/retries; this is not a guaranteed data cap. Only complete validated SDK results create TESTED in the ordinary UI. The API cannot cryptographically attest mobile-data use or carrier identity.
6. All outcomes are saved transactionally on the device first. PENDING/RETRY/SYNCING do not mean server saved. Only a valid per-record ACK becomes SYNCED. The original JSON and UUID remain immutable across retries.
7. Open/resume/focus/online/manual sync verifies API reachability and the session; online events alone are insufficient. Batches contain at most 20 records. There is no dependency on Android background sync.
8. Canceled/timeout tests save SPEEDTEST_FAILED with no numeric measurement. A running marker is persisted before testing. After abrupt page/process termination, an expired marker is recovered as failed on the next open/resume (timeout + 30 seconds); it cannot become a fabricated successful result.
9. New captures stop when the client learns an audit is closed or its assignment is revoked. Stale offline assignments allow device drafts only; the server makes the final permission/state decision. Late closed/revoked submissions remain CONFLICT. Ask a manager to review, reopen/reassign if appropriate, then retry the retained original record. No silent override exists.
10. Sign out/clear/update is blocked while local records or running tests remain. Lock hides the workspace without deleting drafts; it is a local lock, not an offline claim of server-session revocation. Reconnect and sign in as the original owner to resume. Clearing site storage, browser profiles or uninstalling can destroy unsynced records. IndexedDB is not automatically encrypted.

## Manager reporting

Audits freeze room labels, telcos, thresholds and profile on activation. Latest accepted conclusive outcome is ordered by server received_at then record ID; later failed/skipped attempts do not erase it. Client observation times are retained and skew over 15 minutes is flagged. History is immutable.

Dashboard totals count audit targets across accessible non-draft audits, not unique rooms across time. Reports can filter by site, telco and floor; each manager must have permission for every site in that audit before any filter is applied. Auditors cannot access management reports/exports. Revocation is checked again on every request.

Speed averages include only latest TESTED targets. No Signal/No Internet remain null metrics. Tables show sample counts, server sample dates, issue rates (No Signal + No Internet divided by inspected targets), pending counts and the warning about survivorship bias. Weak locations use that audit's frozen thresholds, not global mutable settings. The server cannot know how many unsynced records exist on other phones; the visible device queue is local to the current employee.

Excel sheets are Summary, Telco Comparison, Latest Results, No Signal-No Internet, Pending Targets and All Attempts. They use the same filtered data as the JSON reports. Times include UTC offsets; free text is written as string cells to prevent spreadsheet formulas. At most 50,000 accepted attempts are loaded per report/export; narrow filters if the server returns REPORT_TOO_LARGE_NARROW_FILTERS. The UI displays the first 500 rows of each result table and identifies the full count.

## Prepared CI and manual rollout

`.github/workflows/verify-and-build.yml` runs disposable PostgreSQL migrations/tests, frontend tests, PWA build and API/backup image builds. It pins the official checkout action by commit. An explicitly requested workflow_dispatch on main can publish commit-tagged images to GHCR using GITHUB_TOKEN/packages:write after verification. Base image selectors are resolved to digests before publishing; copy the digest references from the workflow summary to the production configuration.

PR #1 was merged into main at 9b37796bc4a7be66ee5521edb28ca6a3f2345bb9 after successful remote verification. The main publication workflow repeated all 44 backend tests, 20 frontend tests and production image builds, then published API/web/backup images to GHCR. All three were inspected and pulled by digest on the HP; isolated read-only checks passed without database/network/host-port access. Immutable references are in releases/ghcr-9b37796bc4a7.json. The running HP stack was not updated; it retains the previously verified local images and data. The workflow does not give a GitHub runner access to this HP or deploy automatically. For a private GHCR package on a different/fresh host, the operator may need a read:packages credential; never put it in source or frontend variables. Use the backup, migration, healthcheck and rollback procedure in OPERATIONS.md for a later controlled rollout.

References: [GitHub package publishing and permissions](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions), [official checkout action](https://github.com/actions/checkout).
