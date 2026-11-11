# Windows setup and approval record

## Observed status

The approved installation is now working: WSL 3.0.5, Docker Desktop 4.99.0 (245822), Docker Engine 29.9.3 and Compose v5.7.0. Docker's Linux engine uses kernel `6.18.58.1-microsoft-standard-WSL2`. Both `docker-desktop` and `Ubuntu-24.04` are listed as WSL VERSION 2; Ubuntu successfully executed `uname -r`. Docker hello-world passed. No automatic reboot was performed.

Two all-users Docker installation attempts ended during UAC relaunch (installer code 4294967291; winget -1978335226). The supported per-user installation then succeeded at 18:51 MYT, using `install --user --backend=wsl-2 --no-windows-containers`. It installs under `%LOCALAPPDATA%\Programs\DockerDesktop`, without the all-users privileged service. The prepared installer script now defaults to this mode. The first all-users winget package supplied `--accept-license`; the successful per-user override omitted that flag. Installation/engine availability are not proof of license eligibility; the operator must review Docker's commercial terms.

The remaining Ubuntu manual step is choosing a normal Linux username/password on first interactive launch. No Linux user password was chosen by the agent. Do not change Windows security settings or bypass application-control policy.

## WSL installation procedure (already completed)

Open PowerShell **as Administrator** and run:

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
```

Save work and restart only with the operator's explicit permission if Windows requests it. After restart:

```powershell
wsl --version
wsl --status
wsl --list --verbose
wsl -d Ubuntu-24.04
```

Choose your Linux username/password privately at first launch. Verify Ubuntu is listed as VERSION 2. If installation reports firmware virtualization disabled after a reboot, verify Intel virtualization in HP BIOS with operator involvement; do not change BIOS automatically. The pre-install CPU flags conflicted with an active Windows hypervisor, so they do not establish a BIOS problem.

## Docker Desktop — installed per user after approval

Prepared script:

```powershell
./scripts/Install-Prerequisites.ps1 -Component Docker -WhatIf
./scripts/Install-Prerequisites.ps1 -Component Docker
```

Review Docker's license terms yourself, including whether this organization's commercial use needs a paid subscription. Launch Docker Desktop, use **WSL2 backend / Linux containers**, and enable Ubuntu integration if developing inside WSL. Do not enable the unauthenticated TCP Docker daemon. Reopen the terminal after installation if needed.

```powershell
docker version
docker compose version
docker info
docker run --rm hello-world
```

Confirm Docker Engine is Linux and WSL starts successfully. Native Windows Node/Python/PostgreSQL/cloudflared installation is unnecessary for the Compose workflow. Codex's bundled Git, Node, Python and pnpm were used for workspace checks; they are not a guaranteed independent development installation.

## Hosting and restart decisions — separate approval required

- This PC has 8 GB RAM, Docker's current minimum. Only ~1.5 GB was free during inspection. Close unused applications before builds and test resource pressure. Upgrade RAM if sustained production use warrants it.
- Approved and created nonsynced `C:\Users\braxt\IStayTelcoAudit`, with restricted ACLs, fresh database secrets and the separate istay-prod volume. The development checkout remains in OneDrive; no workspace credentials or test database was promoted. See LOCAL-STAGING.md.
- After explicit approval, registered `IStay-Production-AtLogon`. It runs under the current user at logon, waits for Docker and starts localhost-only production staging. Manual invocation and a later observed real reboot/logon passed; see VERIFICATION.md. Native CMD launchers avoid blocked .ps1 execution without changing policy. It does not provide boot-before-login availability, automatic login, firmware power restoration or a Windows service installation.
- After approval, configure sleep/hibernate and AC power policy for hosting, and consider a UPS. No such changes were made. Screen locking is compatible with hosting; sleep stops availability and backup execution.
- Container `restart: unless-stopped` supports process/engine recovery, but a healthcheck alone does not restart a hung container. Investigate unhealthy services and restart them deliberately. Do not mount the Docker socket into an autohealer.

Sources: [Docker Windows install/requirements](https://docs.docker.com/desktop/setup/install/windows-install/), [Microsoft WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install), [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/).
