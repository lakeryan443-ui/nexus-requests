# Nexus Requests

A lightweight Discord bot for managing Seerr media requests
from anywhere, directly through interactive Discord cards.

## Overview

Nexus Requests posts pending Seerr requests to a Discord
approvals channel. Administrators can approve or decline
requests from Discord. For movie requests, they can also
approve and start the exact matching Radarr torrent.

People submitting requests through Seerr or a connected
Jellyfin interface do not need Discord accounts.

## Current features

- Post pending Seerr requests with the title, poster, requester,
  and request details
- Approve or decline requests in Seerr from Discord
- Restrict request actions to configured Discord administrators
- Approve a movie request and start its verified Radarr torrent
- Add the `nexus-priority` tag to the exact verified torrent
- Record movie download progress and completion in the local
  priority job store
- Keep job history when a torrent is missing or needs review

The priority button is available for movie requests. TV requests
can be approved or declined, but TV priority matching is not
implemented. Recovery controls are disabled.

Download progress is recorded in the local job store and service
logs; the Discord card does not show live progress updates. A
completed job means qBittorrent reports that the download
finished. It does not confirm that Radarr imported the media or
that Jellyfin can play it.

## Discord request card

Each pending request has these buttons:

- **Approve** — approve the request in Seerr.
- **Approve & Download Now** — for movie requests, approve in
  Seerr, verify the exact Radarr-linked torrent in qBittorrent,
  tag it, and start it.
- **Decline** — decline the request in Seerr.

The priority workflow requires confirmed Seerr approval and a
unique movie-to-torrent match. Ambiguous matches are not started.
If a started torrent later disappears from qBittorrent, the job
is marked failed for manual review and retained in local history.

## Requirements

- Linux host with systemd
- Python 3.13 or newer
- Discord bot application and token
- Seerr API access
- Radarr API access
- qBittorrent Web UI access

The current application reads its environment file and stores
runtime state under `/opt/nexus-requests`. Install at that path
unless the source paths are updated consistently.

## Configuration

Create `/opt/nexus-requests/.env` with these values:

```dotenv
DISCORD_TOKEN=
ADMIN_DISCORD_IDS=
APPROVALS_CHANNEL_ID=

SEERR_URL=
SEERR_API_KEY=

RADARR_URL=
RADARR_API_KEY=

QBT_URL=
QBT_USERNAME=
QBT_PASSWORD=
```

Use base service URLs, such as `http://host:port`; do not append
`/api/v1`. `ADMIN_DISCORD_IDS` accepts numeric Discord user IDs
separated by commas. The bot uses the approvals channel ID and
does not currently require a Discord server ID.

Movie priority uses Radarr and qBittorrent credentials. Sonarr
configuration is not required for the current movie-only
priority workflow.

Protect the environment file:

```bash
chmod 600 /opt/nexus-requests/.env
```

Never commit `.env`, API keys, bot tokens, passwords, or runtime
state to Git.

## Installation

Clone or copy the repository into `/opt/nexus-requests`, then
install the Python dependencies and create the runtime directory:

```bash
cd /opt/nexus-requests
python3 -m venv venv
venv/bin/pip install -r requirements.txt
install -d -m 700 istate
```

Create and fill in `/opt/nexus-requests/.env` before starting
the bot. The application loads this fixed path.

## Run as a systemd service

Create `/etc/systemd/system/nexus-requests.service`:

```ini
[Unit]
Description=Nexus Requests Discord Bot
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/opt/nexus-requests
ExecStart=/opt/nexus-requests/venv/bin/python /opt/nexus-requests/bot.py
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30
UMask=0077

[Install]
WantedBy=multi-user.target
```

Set the timezone through the host or add an appropriate systemd
`Environment=TZ=Area/Location` value. The unit above has no
`User=` setting and therefore runs as root, matching the current
owner installation. For another host, configure a dedicated
service account and grant it access to the application,
environment file, and `istate` directory before enabling the
service.

Verify and start the service:

```bash
systemd-analyze verify /etc/systemd/system/nexus-requests.service
systemctl daemon-reload
systemctl enable --now nexus-requests.service
systemctl status nexus-requests.service --no-pager --full
journalctl -u nexus-requests.service -n 50 --no-pager
```

After changing application code, run syntax checks and relevant
tests before restarting:

```bash
cd /opt/nexus-requests
python -m py_compile bot.py movie_priority.py priority.py priority_worker.py qbt_verify.py
systemctl restart nexus-requests.service
```

Follow service logs with:

```bash
journalctl -u nexus-requests.service -f
```

## State and backups

Runtime state is stored in `/opt/nexus-requests/istate/`.
It includes posted request IDs and priority job history. Git
ignores this directory.

Back up the environment file, runtime state, and installed
systemd unit together. Stop the service while creating the
archive so the JSON state is not being updated:

```bash
install -d -m 700 /root/nexus-backups
backup_file="/root/nexus-backups/nexus-requests-$(date +%F-%H%M%S).tar.gz"
systemctl stop nexus-requests.service
tar -czf "$backup_file" \
  /opt/nexus-requests/.env \
  /opt/nexus-requests/istate \
  /etc/systemd/system/nexus-requests.service
backup_status=$?
systemctl start nexus-requests.service
if [ "$backup_status" -ne 0 ]; then
  exit "$backup_status"
fi
chmod 600 "$backup_file"
```

Keep backups outside the Git repository and protect them as
carefully as the `.env` file. Keep an encrypted copy off the host
to protect against host or disk failure.

To restore, stop the service, extract the selected archive as
root from `/`, restore `.env` permissions, reload systemd, and
start the service:

```bash
systemctl stop nexus-requests.service
tar -xzf /root/nexus-backups/SELECTED-BACKUP.tar.gz -C /
chmod 600 /opt/nexus-requests/.env
systemctl daemon-reload
systemctl start nexus-requests.service
systemctl status nexus-requests.service --no-pager --full
```

Replace `SELECTED-BACKUP.tar.gz` with the actual backup filename.
Application source code is managed in Git; runtime state and
credentials are not.

## Security

- Keep `.env` readable only by the service account.
- Do not paste credentials into Discord, GitHub issues, logs,
  or the repository.
- Keep `istate/` and backup archives out of Git.
- Only configured Discord administrators can manage requests.
- Review repository changes and tests before restarting the
  production service.

## Project status

Movie request approval and priority downloading are implemented
and running as a systemd service in the owner installation.
TV priority matching, recovery actions, an optional distributed
qBittorrent scheduler, and a self-hosted setup wizard are planned
as later work orders.
