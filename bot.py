import asyncio
import os
import logging

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv("/opt/nexus-requests/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

TOKEN = os.environ["DISCORD_TOKEN"]
SEERR_URL = os.environ["SEERR_URL"].rstrip("/")
SEERR_KEY = os.environ["SEERR_API_KEY"]
CHANNEL_ID = int(os.environ["APPROVALS_CHANNEL_ID"])
ADMIN_IDS = {
    int(value.strip())
    for value in os.environ["ADMIN_DISCORD_IDS"].split(",")
    if value.strip()
}


class RequestView(discord.ui.View):
    def __init__(self, request_id):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.processing = False

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

                async with session.post(
                    f"{url}/{action}"
                ) as response:
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
        disabled=True,
    )
    async def priority(self, interaction, button):
        await interaction.response.send_message(
            "Priority downloading is not enabled yet.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_decline",
    )
    async def decline(self, interaction, button):
        await self.change_request(interaction, "decline")



class NexusBot(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.monitor_task = None
        self.posted_file = "/opt/nexus-requests/istate/posted_requests.json"
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
        self.monitor_task = asyncio.create_task(self.monitor_requests())

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
        await channel.send(embed=embed, view=RequestView(request_id))

        logging.info("Posted Discord card for request #%s", request_id)


intents = discord.Intents.default()
client = NexusBot(intents=intents)

# Request posting and persistent button registration
# will be wired up after our first controlled test.

client.run(TOKEN)
