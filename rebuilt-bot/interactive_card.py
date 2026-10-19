import os
import asyncio

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv(".env")
ADMIN_IDS = {
    int(value.strip())
    for value in os.environ["ADMIN_DISCORD_IDS"].split(",")
    if value.strip()
}


class ApprovalButton(discord.ui.Button):
    def __init__(self, label, style):
        button_ids = {
            "Approve": "nexus_test_approve",
            "Approve & Download Now": "nexus_test_monitor",
            "Decline": "nexus_test_decline",
        }

        super().__init__(
            label=label,
            style=style,
            custom_id=button_ids[label],
            disabled=False,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "You are not authorized to manage requests.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"TEST ONLY: {self.label} clicked. No changes made to Seerr.",
            ephemeral=True,
        )

async def main():
    base = os.environ["SEERR_URL"].rstrip("/")
    headers = {"X-Api-Key": os.environ["SEERR_API_KEY"]}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{base}/api/v1/request/10") as response:
            response.raise_for_status()
            request = await response.json()

        if request.get("status") != 1:
            raise RuntimeError("Test request is no longer pending")

        tmdb_id = request["media"]["tmdbId"]

        async with session.get(f"{base}/api/v1/movie/{tmdb_id}") as response:
            response.raise_for_status()
            movie = await response.json()

    embed = discord.Embed(
        title=movie["title"],
        description="Pending approval",
        color=discord.Color.orange(),
    )

    embed.add_field(
        name="Release Date",
        value=movie.get("releaseDate") or "Unknown",
    )
    embed.add_field(name="Request ID", value=str(request["id"]))
    embed.add_field(
        name="Requested By",
        value=request["requestedBy"].get("displayName")
        or request["requestedBy"].get("username")
        or "Unknown",
        inline=False,
    )

    if movie.get("posterPath"):
        embed.set_thumbnail(
            url="https://image.tmdb.org/t/p/w500"
            + movie["posterPath"]
        )

    view = discord.ui.View(timeout=None)

    view.add_item(ApprovalButton(
        label="Approve",
        style=discord.ButtonStyle.success,
    ))

    view.add_item(ApprovalButton(
        label="Approve & Download Now",
        style=discord.ButtonStyle.primary,
    ))

    view.add_item(ApprovalButton(
        label="Decline",
        style=discord.ButtonStyle.danger,
    ))

    class TestClient(discord.Client):
        async def on_ready(self):
            print("Connected to Discord:", self.user.name)

            channel = await self.fetch_channel(
                int(os.environ["APPROVALS_CHANNEL_ID"])
            )

            message = await channel.send(embed=embed, view=view)

            print("Interactive test card posted successfully")
            print("Message ID:", message.id)
            print("Bot is listening for button clicks. Press Ctrl+C to stop.")

    client = TestClient(intents=discord.Intents.default())
    await client.start(os.environ["DISCORD_TOKEN"])

asyncio.run(main())
