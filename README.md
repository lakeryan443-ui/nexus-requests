# Nexus Requests

**Self-hosted media request approvals, download scheduling, and priority management.**

Nexus Requests connects Seerr, Discord, Radarr, Sonarr, and qBittorrent through a centralized administration interface.

It gives administrators control over which requests are approved, when downloads are allowed to run, and which approved requests should download immediately.

## Features

### Discord Request Approvals

Manage incoming Seerr requests directly from Discord.

- Receive administrator-only approval cards for pending requests.
- Approve or decline movie and TV requests.
- Use **Approve & Download Now** to prioritize an approved request when scheduling is enabled.
- Restrict approval actions to configured Discord administrators.
- Keep request approvals separate from ordinary Discord conversations.

### Download Scheduler

Control when qBittorrent is permitted to download.

- Configure scheduled download windows.
- Automatically start and stop downloads according to the schedule.
- Manage scheduled downloading independently of Seerr approvals.
- Allow priority downloads to override normal scheduling restrictions.
- Preserve ordinary approval behavior without automatically forcing an immediate download.

**Approval behavior**

| Scheduler | Available actions |
|---|---|
| Disabled | Approve, Decline |
| Enabled | Approve, Approve & Download Now, Decline |

The scheduler controls download timing, while Radarr and Sonarr remain responsible for selecting releases.

### Priority Downloads

When an administrator chooses **Approve & Download Now**, Nexus Requests coordinates with the relevant media manager and qBittorrent to prioritize the approved request.

The priority workflow is designed to work with the releases selected by Radarr and Sonarr rather than replacing their release-selection logic.

### Web Administration

Configure Nexus Requests through its browser-based WebGUI.

- Create the initial administrator account.
- Configure supported service integrations.
- Store integration credentials securely.
- Test connections to configured services.
- Manage application settings through an authenticated interface.

### Supported Integrations

| Service | Purpose |
|---|---|
| Seerr | Receives and manages media requests |
| Discord | Administrator approval interface |
| Radarr | Movie download management |
| Sonarr | TV series download management |
| qBittorrent | Download scheduling and priority control |
| Jellyfin | Media-library destination; availability notifications are planned |

Nexus Requests does not replace Seerr, Radarr, Sonarr, or qBittorrent. It coordinates their existing functionality.

## How It Works

1. A user submits a movie or TV request through Seerr.
2. Nexus Requests presents the pending request to authorized Discord administrators.
3. An administrator approves, declines, or prioritizes the request.
4. Radarr or Sonarr handles the approved media request.
5. qBittorrent downloads according to the configured schedule or priority override.
6. The existing media-management workflow imports the completed download.

## Requirements

- Linux system with systemd for native installation.
- Internet access during installation.
- Access to the services being integrated.
- A Discord application and bot token for Discord approval functionality.

The native installer provisions the application's Python environment and systemd services.

## Installation

### Automated Installation

Run the installation commands as root.

**If curl is already installed:**

```bash
curl -fsSL https://raw.githubusercontent.com/lakeryan443-ui/nexus-requests/main/install.sh | bash
```

**If curl is not installed (Debian/Ubuntu):**

```bash
apt update
apt install -y curl ca-certificates
curl -fsSL https://raw.githubusercontent.com/lakeryan443-ui/nexus-requests/main/install.sh | bash
```

The default installation command requires a published stable GitHub Release.

### Release Candidate Installation

For the current release candidate, use the matching version tag:

```bash
curl -fsSL https://raw.githubusercontent.com/lakeryan443-ui/nexus-requests/v0.1.0-rc.4/install.sh | NEXUS_VERSION=v0.1.0-rc.4 bash
```

Release candidates are intended for testing and may change before the stable release.

## First-Time Administrator Setup

After installation, the installer displays a one-time administrator setup token.

1. Open `http://SERVER-IP:8081` in a browser.
2. Navigate to the initial administrator setup page.
3. Enter the setup token.
4. Create the administrator account.
5. Sign in to the WebGUI.

The setup token is also stored locally at:

```text
/opt/nexus-requests/webgui/data/setup.token
```

If you need to retrieve it, run the following command on the server:

```bash
cat /opt/nexus-requests/webgui/data/setup.token
```

The token is sensitive and should not be shared. It is intended only for initial administrator creation and is invalidated after successful setup.

## Configure Integrations

Use the WebGUI to configure your service connections.

For each applicable integration, provide the service URL and the required credentials, then use **Test Connection** to verify communication.

Ensure that Nexus Requests can reach the configured service addresses over the network.

## Managing Services

The native installation uses separate systemd services for the WebGUI, Discord bot, and scheduler.

**Check service status:**

```bash
systemctl status nexus-requests-webgui --no-pager
systemctl status nexus-requests-bot --no-pager
systemctl status nexus-requests-scheduler --no-pager
```

**View recent logs:**

```bash
journalctl -u nexus-requests-webgui -n 50 --no-pager
journalctl -u nexus-requests-bot -n 50 --no-pager
journalctl -u nexus-requests-scheduler -n 50 --no-pager
```

The Discord bot remains inactive until its required configuration is available.

## Security

Nexus Requests is intended to be administered by trusted users.

- The WebGUI requires administrator authentication after initial setup.
- Initial remote administrator creation requires a one-time setup token.
- Integration secrets are stored using encrypted local storage.
- Sensitive configuration files are protected by filesystem permissions.
- Discord approval actions are restricted to authorized administrators.
- Setup and authentication endpoints include security protections.

For remote access, use an appropriately secured reverse proxy with HTTPS. Do not expose sensitive application data or credentials publicly.

## Troubleshooting

**WebGUI is inaccessible:** Check the WebGUI service status, application logs, network connectivity, and firewall settings.

**Discord bot is inactive:** Confirm that Discord configuration has been completed and inspect the bot service logs.

**Integration connection test fails:** Verify the service URL, credentials, network accessibility, and the target service's availability.

**Scheduler is not operating as expected:** Check the configured download windows, scheduler service status, and qBittorrent connection.

## Project Status

**Current testing release:** `v0.1.0-rc.4`

The native installer has completed a successful fresh Debian 13 installation. Full end-to-end validation of the administrator setup, integrations, Discord approval workflow, and scheduler remains part of release testing.

Docker deployment is being considered for a future release.
