"""Controlled service management for Nexus Requests."""

import subprocess

BOT_SERVICE = "nexus-requests-rebuild.service"


class BotServiceError(RuntimeError):
    pass


def restart_bot():
    """Restart the configured Nexus Requests bot service."""
    try:
        result = subprocess.run(
            ["systemctl", "restart", BOT_SERVICE],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BotServiceError("Bot restart could not be completed") from exc

    if result.returncode != 0:
        raise BotServiceError("Bot restart failed")

    return True
