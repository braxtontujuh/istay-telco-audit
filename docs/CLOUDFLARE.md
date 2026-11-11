# Employee HTTPS access through Cloudflare Tunnel

**Not configured.** The operator does not yet have a Cloudflare account/domain or an off-host backup destination. No tunnel token, DNS record or public hostname was created.

## Manual prerequisites

1. Create a Cloudflare account, secure it with MFA, and add a domain you control (register one if needed). Complete its DNS/nameserver activation. Choose a stable subdomain, such as `audit.<your-domain>`.
2. In Cloudflare One/Zero Trust, create a **remotely/dashboard-managed Cloudflare Tunnel** for this HP. Select the Docker connector instructions.
3. Save only its tunnel token locally into `secrets/production/tunnel_token.txt` as UTF-8 text with no BOM. Do not paste it into chat, a terminal command, Git or a frontend environment variable. Protect the file with Windows ACLs and keep it out of OneDrive's synced production location. Rotate any token exposed accidentally.
4. Add a published application route/public hostname for the chosen subdomain. Its origin service is **HTTP `web:8080`**. `localhost` inside the tunnel container would refer to the tunnel itself, so it is incorrect here. No separate `/api` hostname is needed.
5. Set `APP_ORIGIN=https://<exact-hostname>` (no trailing slash) and `TRUSTED_HOSTS=<exact-hostname>,localhost,127.0.0.1,api` in `.env.prod`. Use the pinned `CLOUDFLARED_IMAGE` produced by Build-Production.ps1.
6. Add a Cloudflare cache rule bypassing cache for `/api/*`. Keep service-worker files uncached/revalidated. Do not apply Cache Everything to this app or cache authenticated API responses. Enable HTTPS redirection at the edge, and test the certificate and final URL.
7. Once the full app passes local/security/offline gates, enable the optional connector:

```powershell
./scripts/Start-Production.ps1 -Tunnel
docker compose --env-file .env.prod -f compose.prod.yml --profile tunnel logs --tail 50 tunnel
```

Only the tunnel connector needs outbound Cloudflare connectivity; no router port forwarding or inbound database/web firewall rule is needed. The tunnel joins the edge network, not PostgreSQL's private network. The local web port is loopback-only. The origin hop is inside this PC's Docker network; employees receive HTTPS at Cloudflare's edge through an encrypted tunnel.

Cloudflare Access can be an additional identity gate if desired. If configured, test redirect/session expiry and ensure API requests and service-worker shell downloads still work; the FastAPI session remains mandatory. Configure an edge login rate limit as defense against password spraying. Neither Access nor DNS configuration was performed.

A temporary Quick Tunnel is useful only for a controlled test and changes hostname/session/PWA origin. It is not the stable production employee URL described here. Complete the external/device/security acceptance gates before employee use.

## External acceptance

Use an Android phone on mobile data, disconnected from the HP's LAN. Verify HTTPS certificate, login, unauthorized endpoint rejection, sign-out, PWA install, app launch in airplane mode, local NO_SIGNAL capture, reconnect and one server ACK per UUID. Capture evidence in VERIFICATION.md. DNS resolution and a green tunnel status alone are insufficient.

Sources: [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/), [token-file run parameter](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/).
