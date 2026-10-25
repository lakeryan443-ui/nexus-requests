import asyncio
import os
import logging
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

from discord_config_adapter import load_discord_config

discord_config = load_discord_config()

TOKEN = discord_config["token"]
from seerr_config_adapter import load_seerr_config

seerr_config = load_seerr_config()
SEERR_URL = seerr_config["url"]
SEERR_KEY = seerr_config["api_key"]
CHANNEL_ID = discord_config["channel_id"]
ADMIN_IDS = {
    int(value.strip())
    for value in os.environ["ADMIN_DISCORD_IDS"].split(",")
    if value.strip()
}


class RequestView(discord.ui.View):
    priority_enabled = True

    def __init__(self, request_id, media_type=None):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.processing = False
        from webgui.config_store import ConfigStore

        scheduler = ConfigStore().load_internal("scheduler")
        scheduler_enabled = (
            str(scheduler.get("enabled", "true")).lower() == "true"
        )

        service = {
            "movie": "radarr",
            "tv": "sonarr",
        }.get(media_type)

        eligible = False
        if scheduler_enabled and self.priority_enabled is True and service:
            integration = ConfigStore().load_internal(service)
            eligible = (
                integration.get("enabled") == "true"
                and bool(integration.get("url", "").strip())
                and bool(integration.get("api_key", "").strip())
            )

        if not eligible:
            self.remove_item(self.priority)

    async def change_request(self, interaction, action):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "You are not authorized to manage requests.",
                ephemeral=True,
            )
            return

        if self.processing:
            await interaction.response.send_message(
                "This request is already being processed.",
                ephemeral=True,
            )
            return

        self.processing = True
        await interaction.response.defer(ephemeral=True)

        try:
            headers = {"X-Api-Key": SEERR_KEY}
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"{SEERR_URL}/api/v1/request/{self.request_id}"

                async with session.get(url) as response:
                    response.raise_for_status()
                    request = await response.json()

                if request.get("status") != 1:
                    await interaction.followup.send(
                        "Request is no longer pending. No action taken.",
                        ephemeral=True,
                    )
                    return

                async with session.post(f"{url}/{action}") as response:
                    response.raise_for_status()

            for item in self.children:
                item.disabled = True

            await interaction.message.edit(view=self)

            await interaction.followup.send(
                f"Request #{self.request_id} {action}d in Seerr.",
                ephemeral=True,
            )
            logging.info(
                "Request %s: %s by Discord user %s",
                self.request_id,
                action,
                interaction.user.id,
            )

        except aiohttp.ClientError:
            logging.exception("Seerr API request failed")
            await interaction.followup.send(
                "Seerr API error. Check the bot logs and request status.",
                ephemeral=True,
            )
        except Exception:
            logging.exception("Request processing failed")
            await interaction.followup.send(
                "An error occurred. Check the bot logs.",
                ephemeral=True,
            )
        finally:
            self.processing = False

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="nexus_approve",
    )
    async def approve(self, interaction, button):
        await self.change_request(interaction, "approve")

    @discord.ui.button(
        label="Approve & Download Now",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_priority",
        disabled=False,
    )
    async def priority(self, interaction, button):
        await self.change_priority(interaction)

    async def change_priority(self, interaction):
        from movie_priority import (
            MoviePriorityError,
            approve_movie_priority,
            validate_movie_request,
        )
        from tv_priority_execution import (
            TVPriorityError,
            approve_tv_priority,
        )
        from tv_request import validate_tv_request

        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "You are not authorized to manage requests.",
                ephemeral=True,
            )
            return

        if self.priority_enabled is not True:
            await interaction.response.send_message(
                "Priority downloading is not enabled yet.",
                ephemeral=True,
            )
            return

        if self.processing:
            await interaction.response.send_message(
                "This request is already being processed.",
                ephemeral=True,
            )
            return

        self.processing = True

        try:
            await interaction.response.defer(ephemeral=True)
            headers = {"X-Api-Key": SEERR_KEY}

            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"{SEERR_URL}/api/v1/request/{self.request_id}"

                async with session.get(url) as response:
                    response.raise_for_status()
                    request = await response.json()

                media_type = request.get("type")

                if media_type == "movie":
                    validate_movie_request(self.request_id, request)
                    await approve_movie_priority(
                        self.request_id,
                        request,
                        session=session,
                    )
                elif media_type == "tv":
                    validate_tv_request(self.request_id, request)
                    await approve_tv_priority(
                        self.request_id,
                        request,
                        session=session,
                    )
                else:
                    raise ValueError(
                        f"Unsupported Seerr media type: {media_type!r}"
                    )

            # Associate this priority job with its original Discord card.
            # Tracking failures must not undo or misreport Seerr approval.
            try:
                from priority_store import update_job

                update_job(
                    self.request_id,
                    discord_channel_id=interaction.channel_id,
                    discord_message_id=interaction.message.id,
                )
            except Exception:
                logging.exception(
                    "Request %s: Discord card tracking failed",
                    self.request_id,
                )

            for item in self.children:
                item.disabled = True

            # Update the original approval card with persistent status.
            if interaction.message.embeds:
                embed = interaction.message.embeds[0].copy()
                embed.description = "Approved — Waiting for Download"
                embed.color = discord.Color.blue()
                await interaction.message.edit(embed=embed, view=self)
            else:
                await interaction.message.edit(view=self)

            await interaction.followup.send(
                f"Request #{self.request_id}: Seerr approval confirmed "
                "and priority intent recorded. "
                "Torrent start is not yet confirmed.",
                ephemeral=True,
            )

        except (MoviePriorityError, TVPriorityError, ValueError):
            logging.exception(
                "Priority request #%s rejected or approval unconfirmed",
                self.request_id,
            )
            await interaction.followup.send(
                "Priority approval could not be confirmed. "
                "Check the request and priority job before retrying.",
                ephemeral=True,
            )

        except Exception:
            logging.exception(
                "Priority request #%s failed",
                self.request_id,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Priority request failed. Check its status "
                    "and the bot logs before retrying.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Priority request failed. Check the bot logs.",
                    ephemeral=True,
                )

        finally:
            self.processing = False

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_decline",
    )
    async def decline(self, interaction, button):
        await self.change_request(interaction, "decline")


def get_recovery_notifications():
    """Prepare notifications for interrupted priority jobs."""
    from priority_store import find_interrupted_jobs

    interrupted = find_interrupted_jobs()
    notifications = []

    for request_id, job in interrupted.items():
        notifications.append({
            "request_id": str(request_id),
            "media_type": job.get("media_type", "unknown"),
            "media_id": job.get("media_id"),
            "status": job.get("status"),
        })

    return notifications


def build_recovery_embed(notification):
    """Build a Discord embed for an interrupted priority job."""
    request_id = notification["request_id"]
    media_type = notification["media_type"]
    media_id = notification["media_id"]

    embed = discord.Embed(
        title="Interrupted Priority Download",
        description=(
            f"Seerr request #{request_id} was interrupted "
            "while Nexus Requests was processing it.\n\n"
            "An administrator must review this job before "
            "any recovery action occurs."
        ),
        color=discord.Color.orange(),
    )

    embed.add_field(
        name="Media Type",
        value=str(media_type).upper(),
        inline=True,
    )

    embed.add_field(
        name="Media ID",
        value=str(media_id),
        inline=True,
    )

    embed.add_field(
        name="Recovery Options",
        value=(
            "**Continue:** Revalidate the request and exact torrent "
            "before attempting recovery.\n"
            "**Cancel:** Cancel only the priority job. "
            "The original Seerr request remains unchanged."
        ),
        inline=False,
    )

    embed.set_footer(
        text="Nexus Requests | Administrator recovery required"
    )

    return embed


class RecoveryView(discord.ui.View):
    """Administrator recovery controls for interrupted jobs."""

    def __init__(self, request_id):
        super().__init__(timeout=None)
        self.request_id = str(request_id)

    async def interaction_check(self, interaction):
        """Allow only configured Nexus Requests administrators."""
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "Only Nexus Requests administrators can use "
                "these recovery controls.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="Continue",
        style=discord.ButtonStyle.success,
        custom_id="nexus_recovery_continue",
        disabled=True,
    )
    async def continue_job(self, interaction, button):
        from priority_store import validate_recovery_job

        valid, reason = validate_recovery_job(self.request_id)

        if not valid:
            await interaction.response.send_message(
                f"Recovery blocked: {reason}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Recovery job validated. Continue is not enabled yet.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_recovery_cancel",
        disabled=True,
    )
    async def cancel_job(self, interaction, button):
        from priority_store import validate_recovery_job

        valid, reason = validate_recovery_job(self.request_id)

        if not valid:
            await interaction.response.send_message(
                f"Cancellation blocked: {reason}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Recovery job validated. Cancellation is not enabled yet.",
            ephemeral=True,
        )


class PersistentRequestView(discord.ui.View):
    """Restore request-card callbacks using their embedded request IDs."""

    def __init__(self):
        super().__init__(timeout=None)
        self.request_views = {}

    async def dispatch(self, interaction, action):
        message = interaction.message
        bot_user = interaction.client.user

        if (
            interaction.channel_id != CHANNEL_ID
            or message is None
            or bot_user is None
            or message.author.id != bot_user.id
        ):
            await interaction.response.send_message(
                "This is not a valid Nexus request card.",
                ephemeral=True,
            )
            return

        values = [
            str(field.value).strip()
            for embed in message.embeds
            for field in embed.fields
            if field.name == "Request ID"
        ]

        if (
            len(values) != 1
            or not values[0].isascii()
            or not values[0].isdigit()
            or int(values[0]) <= 0
        ):
            await interaction.response.send_message(
                "The request card has an invalid request ID.",
                ephemeral=True,
            )
            return

        request_id = int(values[0])
        view = self.request_views.get(message.id)

        if view is None:
            media_types = [
                str(field.value).strip().lower()
                for embed in message.embeds
                for field in embed.fields
                if field.name == "Media Type"
            ]
            media_type = media_types[0] if len(media_types) == 1 else None
            view = RequestView(request_id, media_type=media_type)
            self.request_views[message.id] = view
        elif view.request_id != request_id:
            await interaction.response.send_message(
                "The request card identity changed. Manual review required.",
                ephemeral=True,
            )
            return

        if action == "priority":
            await view.change_priority(interaction)
        else:
            await view.change_request(interaction, action)

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="nexus_approve",
    )
    async def approve(self, interaction, button):
        await self.dispatch(interaction, "approve")

    @discord.ui.button(
        label="Approve & Download Now",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_priority",
        disabled=True,
    )
    async def priority(self, interaction, button):
        await self.dispatch(interaction, "priority")

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_decline",
    )
    async def decline(self, interaction, button):
        await self.dispatch(interaction, "decline")


class NexusBot(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.monitor_task = None
        self.priority_task = None
        self.posted_file = str(Path(__file__).resolve().parent / "istate" / "posted_requests.json")
        self.posted_ids = set()

        import json

        if os.path.exists(self.posted_file):
            try:
                with open(self.posted_file, "r") as file:
                    self.posted_ids = set(json.load(file))
            except (OSError, ValueError, TypeError):
                logging.exception("Could not load posted request IDs")
                raise

    async def setup_hook(self):
        from priority_worker_rebuild import priority_worker_loop

        self.add_view(PersistentRequestView())

        self.monitor_task = asyncio.create_task(
            self.monitor_requests(),
            name="nexus-request-monitor",
        )
        self.priority_task = asyncio.create_task(
            priority_worker_loop(
                execute=RequestView.priority_enabled,
                discord_client=self,
            ),
            name="nexus-priority-worker",
        )

    async def close(self):
        tasks = [
            task
            for task in (self.monitor_task, self.priority_task)
            if task is not None
        ]

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await super().close()

    async def on_ready(self):
        logging.info("Connected to Discord as %s", self.user)

    async def monitor_requests(self):
        import json

        await self.wait_until_ready()

        while not self.is_closed():
            try:
                headers = {"X-Api-Key": SEERR_KEY}

                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(
                        f"{SEERR_URL}/api/v1/request",
                        params={
                            "filter": "pending",
                            "take": 100,
                            "skip": 0,
                            "sort": "added",
                        },
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()

                requests_list = data.get("results", [])

                for request in requests_list:
                    if request.get("status") != 1:
                        continue

                    request_id = request["id"]

                    if request_id in self.posted_ids:
                        continue

                    await self.post_request(request_id)

                    self.posted_ids.add(request_id)

                    with open(self.posted_file, "w") as file:
                        json.dump(sorted(self.posted_ids), file)

                    logging.info(
                        "New pending request detected: #%s",
                        request_id,
                    )

            except Exception:
                logging.exception("Error monitoring Seerr requests")

            await asyncio.sleep(30)

    async def post_request(self, request_id):
        headers = {"X-Api-Key": SEERR_KEY}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"{SEERR_URL}/api/v1/request/{request_id}"
            ) as response:
                response.raise_for_status()
                request = await response.json()

            if request.get("status") != 1:
                raise RuntimeError("Request is not pending")

            tmdb_id = request["media"]["tmdbId"]
            media_type = request["type"]
            endpoint = "movie" if media_type == "movie" else "tv"

            async with session.get(
                f"{SEERR_URL}/api/v1/{endpoint}/{tmdb_id}"
            ) as response:
                response.raise_for_status()
                media = await response.json()

        embed = discord.Embed(
            title=media.get("title") or media.get("name") or "Unknown",
            description="Pending approval",
            color=discord.Color.orange(),
        )

        embed.add_field(name="Request ID", value=str(request_id))
        embed.add_field(name="Media Type", value=media_type.upper())
        embed.add_field(
            name="Requested By",
            value=(
                request.get("requestedBy", {}).get("displayName")
                or request.get("requestedBy", {}).get("username")
                or "Unknown"
            ),
            inline=False,
        )

        if media.get("posterPath"):
            embed.set_thumbnail(
                url="https://image.tmdb.org/t/p/w500"
                + media["posterPath"]
            )

        channel = await self.fetch_channel(CHANNEL_ID)
        await channel.send(
            embed=embed,
            view=RequestView(request_id, media_type=media_type),
        )

        logging.info("Posted Discord card for request #%s", request_id)


if __name__ == "__main__":
    intents = discord.Intents.default()
    client = NexusBot(intents=intents)
    client.run(TOKEN)
