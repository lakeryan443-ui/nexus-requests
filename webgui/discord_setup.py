"""Discord setup verification for Nexus Requests WebGUI."""

import asyncio
import aiohttp

DISCORD_API = "https://discord.com/api/v10"

REQUIRED_PERMISSIONS = {
    "View Channels": 1 << 10,
    "Send Messages": 1 << 11,
    "Manage Channels": 1 << 4,
    "Embed Links": 1 << 14,
    "Read Message History": 1 << 16,
}


async def _verify(token, guild_id):
    headers = {"Authorization": f"Bot {token}"}
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(
        headers=headers, timeout=timeout
    ) as session:

        async def get(path):
            async with session.get(DISCORD_API + path) as response:
                if response.status != 200:
                    raise ValueError(
                        f"Discord API returned HTTP {response.status}"
                    )
                return await response.json()

        bot = await get("/users/@me")
        guild = await get(f"/guilds/{guild_id}")
        member = await get(
            f"/guilds/{guild_id}/members/{bot['id']}"
        )
        roles = await get(f"/guilds/{guild_id}/roles")

        role_ids = set(member["roles"])
        permissions = 0

        for role in roles:
            if role["id"] == str(guild_id) or role["id"] in role_ids:
                permissions |= int(role["permissions"])

        administrator = bool(permissions & (1 << 3))

        checks = {
            name: administrator or bool(permissions & bit)
            for name, bit in REQUIRED_PERMISSIONS.items()
        }

        return {
            "connected": True,
            "bot": bot["username"],
            "server": guild["name"],
            "owner_id": str(guild["owner_id"]),
            "permissions": checks,
            "ready": all(checks.values()),
        }


def test_discord_connection(token, guild_id):
    if not token or not guild_id or not str(guild_id).isdigit():
        raise ValueError("Valid bot token and server ID required")

    return asyncio.run(_verify(token, str(guild_id)))


async def _ensure_notification_channel(token, guild_id):
    headers = {"Authorization": f"Bot {token}"}
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        headers=headers, timeout=timeout
    ) as session:
        async with session.get(
            f"{DISCORD_API}/guilds/{guild_id}/channels"
        ) as response:
            if response.status != 200:
                raise ValueError(
                    f"Unable to retrieve Discord channels: HTTP {response.status}"
                )
            channels = await response.json()

        for channel in channels:
            if channel.get("name") == "nexus-requests" and channel.get("type") == 0:
                return {
                    "created": False,
                    "channel_id": channel["id"],
                    "channel_name": "nexus-requests",
                }

        async with session.post(
            f"{DISCORD_API}/guilds/{guild_id}/channels",
            json={
                "name": "nexus-requests",
                "type": 0,
                "topic": "Nexus Requests notifications and approvals",
            },
        ) as response:
            if response.status != 201:
                raise ValueError(
                    f"Unable to create Discord channel: HTTP {response.status}"
                )
            channel = await response.json()

        return {
            "created": True,
            "channel_id": channel["id"],
            "channel_name": channel["name"],
        }


def ensure_notification_channel(token, guild_id):
    verification = test_discord_connection(token, guild_id)

    if not verification["ready"]:
        raise ValueError("Discord permissions verification failed")

    result = asyncio.run(_ensure_notification_channel(token, str(guild_id)))
    result["owner_id"] = verification["owner_id"]
    return result


async def _send_test_notification(token, channel_id):
    headers = {"Authorization": f"Bot {token}"}
    timeout = aiohttp.ClientTimeout(total=15)

    payload = {
        "embeds": [{
            "title": "Nexus Requests — Connection Test",
            "description": (
                "Your Discord notification channel is working!\n\n"
                "Return to Nexus Requests and select "
                "**I Received It — Activate Discord**."
            ),
            "color": 3447003,
            "footer": {
                "text": "Nexus Requests • Setup Verification"
            },
        }]
    }

    async with aiohttp.ClientSession(
        headers=headers, timeout=timeout
    ) as session:
        async with session.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            json=payload,
        ) as response:
            if response.status != 200:
                raise ValueError(
                    f"Discord test notification failed: HTTP {response.status}"
                )

            message = await response.json()

    return {
        "sent": True,
        "message_id": message["id"],
        "channel_id": str(channel_id),
    }


def send_test_notification(token, channel_id):
    if not token or not str(channel_id).isdigit():
        raise ValueError("Valid Discord credentials required")

    return asyncio.run(
        _send_test_notification(token, str(channel_id))
    )


def connect_discord_and_send_test(token, guild_id):
    """Verify bot, prepare channel, and send a test notification."""
    verification = test_discord_connection(token, guild_id)

    if not verification["ready"]:
        missing = [
            name for name, allowed
            in verification["permissions"].items()
            if not allowed
        ]
        raise ValueError(
            "Missing Discord permissions: " + ", ".join(missing)
        )

    channel = ensure_notification_channel(token, guild_id)

    notification = send_test_notification(
        token, channel["channel_id"]
    )

    return {
        "success": True,
        "bot": verification["bot"],
        "server": verification["server"],
        "channel_name": channel["channel_name"],
        "channel_id": channel["channel_id"],
        "channel_created": channel["created"],
        "notification_sent": notification["sent"],
        "message_id": notification["message_id"],
    }
