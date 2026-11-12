# Employee HTTPS access through Cloudflare Tunnel

**Account created; external deployment not configured.** On 2026-11-12 the operator reported creating a Cloudflare account, confirmed no domain is owned yet, and chose the formal-domain route rather than a temporary Quick Tunnel. Domain name/budget selection and registration are pending. No tunnel token, DNS record or public hostname has been configured; local-only staging remains in use. Off-host backup storage is also still unavailable.

## Manual prerequisites

1. Sign in to the newly created Cloudflare account, secure it with MFA, and add a domain you control (register one if needed). The operator chooses the domain and privately completes registrant/payment details and agreement acceptance. Confirm domain activation before choosing the final application hostname, such as `audit.<your-domain>`. Registration availability and final price must be confirmed in the registrar checkout; no purchase has been made by the agent.
2. In Cloudflare One/Zero Trust, create a **remotely/dashboard-managed Cloudflare Tunnel** for this HP. Select the Docker connector instructions.
3. Save only its tunnel token locally into `secrets/production/tunnel_token.txt` as UTF-8 text with no BOM. Do not paste it into chat, a terminal command, Git or a frontend environment variable. Protect the file with Windows ACLs and keep it out of OneDrive's synced production location. Rotate any token exposed accidentally.
4. Add a published application route/public hostname for the chosen subdomain. Its origin service is **HTTP `web:8080`**. `localhost` inside the tunnel container would refer to the tunnel itself, so it is incorrect here. No separate `/api` hostname is needed.
5. Set `APP_ORIGIN=https://<exact-hostname>` (no trailing slash) and `TRUSTED_HOSTS=<exact-hostname>,localhost,127.0.0.1,api` in `.env.prod`. Use the pinned `CLOUDFLARED_IMAGE` produced by Build-Production.ps1.
6. Add a Cloudflare cache rule bypassing cache for `/api/*`. Keep service-worker files uncached/revalidated. Do not apply Cache Everything to this app or cache authenticated API responses. Enable HTTPS redirection at the edge, and test the certificate and final URL.
7. Once the full app passes local/security/offline gates, enable the optional connector:

```powershell
./scripts/Start-Production.cmd --tunnel
docker compose --env-file .env.prod -f compose.prod.yml --profile tunnel logs --tail 50 tunnel
```

Only the tunnel connector needs outbound Cloudflare connectivity; no router port forwarding or inbound database/web firewall rule is needed. The tunnel joins the edge network, not PostgreSQL's private network. The local web port is loopback-only. The origin hop is inside this PC's Docker network; employees receive HTTPS at Cloudflare's edge through an encrypted tunnel.

Cloudflare Access can be an additional identity gate if desired. If configured, test redirect/session expiry and ensure API requests and service-worker shell downloads still work; the FastAPI session remains mandatory. Configure an edge login rate limit as defense against password spraying. Neither Access nor DNS configuration was performed.

A temporary Quick Tunnel is useful only for a controlled test and changes hostname/session/PWA origin. It is not the stable production employee URL described here. Complete the external/device/security acceptance gates before employee use.

## External acceptance

Use an Android phone on mobile data, disconnected from the HP's LAN. Verify HTTPS certificate, login, unauthorized endpoint rejection, sign-out, PWA install, app launch in airplane mode, local NO_SIGNAL capture, reconnect and one server ACK per UUID. Capture evidence in VERIFICATION.md. DNS resolution and a green tunnel status alone are insufficient.

Sources: [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/), [token-file run parameter](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/).

Domain guidance: [Cloudflare registration procedure](https://developers.cloudflare.com/registrar/get-started/register-domain/), [current extension prices](https://pricing.registrar.cloudflare.com/). The native CMD launcher above matches this HP's unchanged Restricted PowerShell execution policy. Do not enable the tunnel before the exact hostname/token/private configuration and external-access approval are ready.
