import os
import logging

import discord
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise RuntimeError("DISCORD_TOKEN is missing from .env")

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logging.info("Connected to Discord successfully")
    logging.info("Bot username: %s", client.user.name)


client.run(token)
