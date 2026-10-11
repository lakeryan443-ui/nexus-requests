# Nexus Requests

A lightweight Discord bot for managing Seerr media requests
from anywhere, directly through interactive Discord cards.

## Overview

Nexus Requests makes it easy to approve, decline, and monitor
movie and TV show requests submitted through Seerr without
needing to open the Seerr web interface.

Designed for convenient request management on desktop and
mobile Discord.

## Features

- Automatically display pending Seerr requests in Discord
- Show media titles, posters, and requesting users
- Approve requests with one click
- Approve and monitor download progress
- Decline requests with one click
- Restrict approval actions to authorized administrators
- Update Discord cards as request statuses change

## Discord Request Card

Each request displays three buttons in a single row:

[Approve] [Approve & Monitor] [Decline]

### Button Actions

**Approve**
Approves the request in Seerr, allowing the configured media
management application to begin its normal download workflow.

**Approve & Monitor**
Approves the request and enables Discord progress updates
until the requested media becomes available.

**Decline**
Declines the request in Seerr.

## Requirements

- Python 3.13+
- Discord bot application and token
- Seerr instance with API access
- discord.py
- aiohttp
- python-dotenv

## Security

- Only configured Discord administrators can approve or
  decline requests.
- Credentials are stored in environment variables.
- Secrets and runtime data are excluded from Git.

## Development Status

Early development. Features described above are planned
and are not yet implemented.
