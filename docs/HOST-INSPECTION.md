# HP inspection — 2026-11-11 (Asia/Kuala_Lumpur)

Read-only checks:

| Item | Finding |
| --- | --- |
| Computer | HP ProDesk 400 G7 Small Form Factor PC |
| OS | Windows 11 Pro, 25H2, build 26200.9711, x64 |
| CPU | Intel Core i5-10500 @ 3.10 GHz |
| RAM | 8,354,234,368 bytes (~7.78 GiB); ~1.47 GiB available at inspection |
| C: free | ~398 GiB |
| Virtualization | HypervisorPresent=True. CPU firmware/SLAT flags returned False under the active hypervisor; verify via WSL start rather than assuming BIOS disabled. |
| WSL | wsl.exe exists, but `wsl --status` and `--list --verbose` say WSL is not installed |
| Docker Desktop / Compose | CLI not on PATH; standard all-users executable absent; must check per-user location before install |
| Git | 2.56.0, bundled Codex runtime |
| Node | 24.22.1, bundled Codex runtime; npm not on PATH |
| Python | WindowsApps alias on PATH; bundled Python 3.12 available to this task |
| cloudflared | Not on PATH; proposed deployment uses container, so Windows installation is unnecessary |
| Repository | Cloned into this workspace; upstream contains SPEC.md only |

Missing: WSL runtime and Linux distro; Docker Desktop with WSL2 backend/Compose; project dependencies and images; Cloudflare hostname/account/tunnel token; unique production credentials; separate-device/off-host backup destination.

Unverified: Windows optional feature state (requires administrator), LanmanServer service/start mode, Docker license eligibility, reboot/startup recovery, power management, Android device/browser.

Follow-up: LanmanServer is Running/Automatic. Standard per-user Docker locations were checked too and absent. After explicit approval, WSL 3.0.5 runtime installed. WSL still reports Virtual Machine Platform unavailable and no distro; the next UAC prompt was canceled. See WINDOWS-SETUP.md for continuation. The original observations above record the pre-install state.

Latest follow-up: Docker Desktop 4.99.0 installed successfully in supported per-user mode after approval. Docker Engine 29.9.3 and Compose v5.7.0 verified. Linux engine runs under WSL2 (kernel 6.18.58.1-microsoft-standard-WSL2), with ~3.71 GiB available to the Docker VM. Ubuntu-24.04 also installed as WSL2 and successfully ran uname. hello-world, development stack and an isolated production rehearsal ran successfully. These supersede the earlier missing-prerequisite observations; no reboot, Windows recovery task or power-policy change was performed.

8 GB is Docker Desktop's documented minimum; close memory-heavy applications before builds. Consider 16 GB or more if this PC will also be used interactively. No BIOS, Windows features, software installation, firewall, startup, power setting or reboot has been changed by inspection.
