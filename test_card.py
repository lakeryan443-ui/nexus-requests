import os
import asyncio

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv(".env")


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

    view.add_item(discord.ui.Button(
        label="Approve",
        style=discord.ButtonStyle.success,
        disabled=True,
    ))
    view.add_item(discord.ui.Button(
        label="Approve & Monitor",
        style=discord.ButtonStyle.primary,
        disabled=True,
    ))
    view.add_item(discord.ui.Button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        disabled=True,
    ))

    async with discord.Client(intents=discord.Intents.default()) as client:
        await client.login(os.environ["DISCORD_TOKEN"])

        channel = await client.fetch_channel(
            int(os.environ["APPROVALS_CHANNEL_ID"])
        )

        message = await channel.send(embed=embed, view=view)
        print("Test card posted successfully")
        print("Message ID:", message.id)


asyncio.run(main())
