"""Shared Discord configuration adapter for Nexus Requests."""

import os
import sys
from pathlib import Path


class DiscordConfigurationError(RuntimeError):
    """Discord configuration cannot be loaded safely."""


def load_discord_config(webgui_dir=None):
    """Load activated WebGUI settings or legacy environment fallback."""

    directory = Path(
        webgui_dir
        or os.environ.get("NEXUS_WEBGUI_DIR", "/opt/nexus-requests-webgui")
    )

    if directory.is_dir():
        sys.path.insert(0, str(directory))

        try:
            from config_store import ConfigStore
            saved = ConfigStore().load_internal("discord")
        except Exception as exc:
            raise DiscordConfigurationError(
                "Unable to read WebGUI Discord configuration"
            ) from exc
        finally:
            sys.path.remove(str(directory))

        if saved:
            if not isinstance(saved, dict):
                raise DiscordConfigurationError(
                    "Invalid WebGUI Discord configuration"
                )

            required = ("bot_token", "guild_id", "channel_id")

            if not all(
                isinstance(saved.get(key), str)
                and saved[key].strip()
                for key in required
            ):
                raise DiscordConfigurationError(
                    "WebGUI Discord activation is incomplete"
                )

            try:
                guild_id = int(saved["guild_id"])
                channel_id = int(saved["channel_id"])
            except ValueError as exc:
                raise DiscordConfigurationError(
                    "Invalid Discord server or channel ID"
                ) from exc

            if guild_id <= 0 or channel_id <= 0:
                raise DiscordConfigurationError(
                    "Invalid Discord server or channel ID"
                )

            return {
                "token": saved["bot_token"],
                "guild_id": guild_id,
                "channel_id": channel_id,
                "source": "webgui",
            }

    try:
        return {
            "token": os.environ["DISCORD_TOKEN"],
            "guild_id": None,
            "channel_id": int(os.environ["APPROVALS_CHANNEL_ID"]),
            "source": "environment",
        }
    except (KeyError, ValueError) as exc:
        raise DiscordConfigurationError(
            "Discord has not been configured"
        ) from exc
