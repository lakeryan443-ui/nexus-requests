import os

import aiohttp
from dotenv import load_dotenv

load_dotenv("/opt/nexus-requests/.env")


class TorrentNotFoundError(RuntimeError):
    """qBittorrent successfully answered, but the exact torrent is absent."""


async def verify_torrent(torrent_hash, expected_category=None):
    """
    Read-only verification of one qBittorrent torrent.

    Does not modify tags, download state, or settings.
    """

    torrent_hash = str(torrent_hash).strip().lower()

    if len(torrent_hash) not in (40, 64):
        raise ValueError("Invalid torrent hash length")

    if any(c not in "0123456789abcdef" for c in torrent_hash):
        raise ValueError("Invalid torrent hash characters")

    base = os.environ["QBT_URL"].rstrip("/")
    cookie_jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        cookie_jar=cookie_jar
    ) as session:
        async with session.post(
            f"{base}/api/v2/auth/login",
            data={
                "username": os.environ["QBT_USERNAME"],
                "password": os.environ["QBT_PASSWORD"],
            },
        ) as response:
            response.raise_for_status()

            if (await response.text()).strip() != "Ok.":
                raise RuntimeError("qBittorrent authentication failed")

        async with session.get(
            f"{base}/api/v2/torrents/info",
            params={"hashes": torrent_hash},
        ) as response:
            response.raise_for_status()
            torrents = await response.json()

    if not isinstance(torrents, list):
        raise RuntimeError("Invalid qBittorrent torrent response")

    if not torrents:
        raise TorrentNotFoundError(
            f"Torrent {torrent_hash} was not found in qBittorrent"
        )

    if len(torrents) != 1 or not isinstance(torrents[0], dict):
        raise RuntimeError(
            f"Expected exactly one valid torrent, found {len(torrents)}"
        )

    torrent = torrents[0]
    returned_hash = torrent.get("hash")

    if (
        not isinstance(returned_hash, str)
        or returned_hash.lower() != torrent_hash
    ):
        raise RuntimeError("qBittorrent returned an unexpected torrent hash")

    category = torrent.get("category", "")

    if category not in ("radarr", "sonarr"):
        raise RuntimeError(
            f"Torrent has unauthorized category: {category!r}"
        )

    if expected_category and category != expected_category:
        raise RuntimeError(
            f"Expected category {expected_category!r}, "
            f"found {category!r}"
        )

    return {
        "hash": torrent_hash,
        "name": torrent.get("name"),
        "category": category,
        "state": torrent.get("state"),
        "tags": torrent.get("tags"),
        "progress": torrent.get("progress"),
    }
