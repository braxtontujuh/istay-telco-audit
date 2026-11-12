# Employee HTTPS access through Cloudflare Tunnel

**Public HTTPS access is working; final employee acceptance is incomplete.** The operator-owned GoDaddy domain uses Cloudflare Free and the approved hostname **`https://network.mrbraxton.net`**. The zone is Active, `IStay-HP-ProDesk` is Healthy, and the approved published application routes to `http://web:8080`. Public HTTPS authentication, Secure/HttpOnly cookies, CSRF/logout, and database/session persistence after restart and recreation passed. The operator confirmed Android mobile-data login and cached page opening in airplane mode. Android offline record capture/server acknowledgment, PWA installation and a real SIM speed test remain unverified; the operator declined creation of a synthetic phone acceptance audit. Off-host storage is still unavailable.

## Domain handover record

- Registrar and renewal remain at GoDaddy. DNS management moves to Cloudflare after delegation becomes active.
- Previous nameservers: `ns59.domaincontrol.com`, `ns60.domaincontrol.com`.
- Assigned Cloudflare nameservers: `vera.ns.cloudflare.com`, `west.ns.cloudflare.com`.
- GoDaddy records were reviewed: parked apex A, `www` CNAME, `_domainconnect` CNAME and `_dmarc` TXT, plus provider-managed NS/SOA. No MX or domain/subdomain forwarding was configured. Cloudflare imported the two parking IPs (`3.33.130.190`, `15.197.148.33`), both CNAMEs and the existing DMARC TXT; those existing records remain DNS-only. The parking IPs are not this HP's address.
- Before submission, public DNS confirmed the old GoDaddy delegation, no existing `network.mrbraxton.net` A record, and no parent DS record. No DNSSEC protection was disabled.
- Public DNS and Google DoH return the Cloudflare delegation and application address; the dashboard lists the domain as Active. A transient resolver inconsistency was observed during propagation; the operator subsequently confirmed mobile-data login.
- `.env.prod` now uses `APP_ORIGIN=https://network.mrbraxton.net` and `TRUSTED_HOSTS=network.mrbraxton.net,localhost,127.0.0.1,api`. `.deployment.json` mode is `Cloudflare`. The project remains `istay-prod` and retains `istay-prod_pgdata`, existing administrator and private database credentials.
- Current-user startup is `IStay-Production-AtLogon` -> `Start-Production.cmd --tunnel`, Limited/Interactive; its actual manual run at 22:00:43 MYT returned 0. Windows sign-in is still required. No final-mode host reboot was initiated or claimed.
- Only loopback `127.0.0.1:8080` is published for operator diagnostics. Use the formal HTTPS URL for sign-in. The earlier localhost:8444 TLS overlay and `.env.local-staging` are retained for controlled rollback, not used by the active deployment.
- Always Use HTTPS is enabled; HTTP returns 301 preserving path/query. The Active rule `IStay network - bypass edge cache` matches only `network.mrbraxton.net` and bypasses Cloudflare edge caching without a browser-TTL override. API responses retain `no-store`; service-worker files retain `no-cache`.
- The approved config-only web hotfix serves the PWA manifest as `application/manifest+json`. All 12 served frontend files, including the service worker, are byte-identical to the previous image. See `releases/phase5-pwa-mime-20261112a.json`; API/database/backup images were not replaced with GHCR artifacts.
- Token entry succeeded privately using `save-tunnel-token.py --gui`; the nonempty token file inherits access limited to the operator, SYSTEM and Administrators. The connector joins only `istay-prod_edge`, publishes no ports, and registered four QUIC connections.

## Verification and rollback

Run the installed Python executable with `scripts/verify-dev.py --production-root C:\Users\braxt\IStayTelcoAudit --smoke-only` for external certificate/authentication/manifest checks using a temporary account that is cleaned up. Omitting `--smoke-only` also restarts/recreates DB/API; schedule that disruptive persistence test deliberately. It guards the exact approved hostname and deployment metadata. Both full external persistence checks and the later hotfix smoke check passed.

The final same-host backup `istay-20261112T142046Z.dump` passed checksum/scratch restore: migration 0001, one user, four sites, six telcos, zero inspections. Evidence is in `docs/evidence/cloudflare-public-acceptance.json`.

Private `.env.prod.before-network-*`, `.env.prod.before-pwa-*`, deployment metadata and task XML snapshots are retained in the nonsynced directory. A web-only rollback restores the prior `WEB_IMAGE` and recreates only `web`. To withdraw public application access, remove/disable its published route or stop only the tunnel service. Returning to localhost-only mode also requires deliberately restoring the earlier logon-task action and using `.env.local-staging` with its TLS overlay; preserve the named volume throughout. Never remove volumes or restore a dump over the live database as a code rollback.

Browser storage is origin-specific. Keep the formal hostname stable; synchronize pending work before changing URLs. Employees need their own scoped accounts and a real configured audit/target before the remaining phone capture/sync acceptance can be performed. No synthetic business audit was created in production.

## Manual prerequisites

1. Confirm `mrbraxton.net` is Active in the existing Cloudflare account and that public NS delegation matches the assigned pair above. The operator privately manages account MFA, registrar/payment details and agreement acceptance. The selected application hostname is `network.mrbraxton.net`; domain purchase was completed by the operator.
2. This account uses **Cloudflare dashboard -> Networking -> Tunnels** for its remotely managed tunnel. `IStay-HP-ProDesk` already exists; select the Docker connector instructions only when provisioning/replacing a connector. Do not create duplicate tunnels or rotate a working token unintentionally.
3. Save only its tunnel token locally into `secrets/production/tunnel_token.txt` as UTF-8 text with no BOM. The prepared helper is `python scripts/save-tunnel-token.py --gui --root C:\Users\braxt\IStayTelcoAudit`, run interactively with the installed Python executable. The masked graphical input supports Ctrl+V; console entry is available without `--gui`. It accepts the token or a Cloudflare connector install command, extracts the token without executing the command, refuses an existing file, and inherits the protected production-directory ACL. Optional `--status-file` records only the generic result, never the input. Verify successful exit and a nonempty token file before starting the connector. Do not paste credentials into chat, shell arguments, Git or a frontend environment variable. Keep production secrets outside OneDrive. Rotate any token exposed accidentally.
4. Add a published application route/public hostname for the chosen subdomain. Its origin service is **HTTP `web:8080`**. `localhost` inside the tunnel container would refer to the tunnel itself, so it is incorrect here. No separate `/api` hostname is needed.
5. Set `APP_ORIGIN=https://<exact-hostname>` (no trailing slash) and `TRUSTED_HOSTS=<exact-hostname>,localhost,127.0.0.1,api` in `.env.prod`. Use the pinned `CLOUDFLARED_IMAGE` produced by Build-Production.ps1.
6. The application-hostname edge-cache bypass and HTTPS redirect are enabled. Retain that rule and origin cache headers; do not apply Cache Everything or browser-TTL overrides to authenticated APIs or service-worker files.
7. After local/security checks and operator approval of public access, enable the connector for external acceptance, then complete phone/offline/SIM gates before employee rollout:

```powershell
./scripts/Start-Production.cmd --tunnel
docker compose --env-file .env.prod -f compose.prod.yml --profile tunnel logs --tail 50 tunnel
```

Only the tunnel connector needs outbound Cloudflare connectivity; no router port forwarding or inbound database/web firewall rule is needed. The tunnel joins the edge network, not PostgreSQL's private network. The local web port is loopback-only. The origin hop is inside this PC's Docker network; employees receive HTTPS at Cloudflare's edge through an encrypted tunnel.

Cloudflare Access can be an additional identity gate if desired. If configured, test redirect/session expiry and ensure API requests and service-worker shell downloads still work; the FastAPI session remains mandatory. Review an edge login rate limit as additional protection; server-side login limiting is already implemented. Access and an extra edge login rate-limit rule are not configured. Account MFA, registrar renewal and future credential recovery remain operator responsibilities.

A temporary Quick Tunnel is useful only for a controlled test and changes hostname/session/PWA origin. It is not the stable production employee URL described here. Complete the external/device/security acceptance gates before employee use.

## External acceptance

Use an Android phone on mobile data, disconnected from the HP's LAN. Verify HTTPS certificate, login, unauthorized endpoint rejection, sign-out, PWA install, app launch in airplane mode, local NO_SIGNAL capture, reconnect and one server ACK per UUID. Capture evidence in VERIFICATION.md. DNS resolution and a green tunnel status alone are insufficient.

Sources: [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/), [token-file run parameter](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/).

Domain guidance: [Cloudflare registration procedure](https://developers.cloudflare.com/registrar/get-started/register-domain/), [current extension prices](https://pricing.registrar.cloudflare.com/). The native CMD launcher above matches this HP's unchanged Restricted PowerShell execution policy. Do not enable the tunnel before the exact hostname/token/private configuration and external-access approval are ready.
