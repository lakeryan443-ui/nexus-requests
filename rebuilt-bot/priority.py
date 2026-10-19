import os

import aiohttp


PRIORITY_TAG = "nexus-priority"


class PriorityError(Exception):
    pass


async def prioritize_torrent(
    torrent_hash, *, expected_category=None, session=None
):
    """Verify, tag, and start one explicitly identified torrent."""

    if not isinstance(torrent_hash, str):
        raise PriorityError("Invalid torrent hash")

    torrent_hash = torrent_hash.strip().lower()

    if (
        len(torrent_hash) not in (40, 64)
        or any(c not in "0123456789abcdef" for c in torrent_hash)
    ):
        raise PriorityError("Invalid torrent hash")

    if expected_category not in (None, "radarr", "sonarr"):
        raise PriorityError("Invalid expected category")

    base = os.environ["QBT_URL"].rstrip("/")

    async def execute(client):
        async with client.post(
            f"{base}/api/v2/auth/login",
            data={
                "username": os.environ["QBT_USERNAME"],
                "password": os.environ["QBT_PASSWORD"],
            },
        ) as response:
            response.raise_for_status()
            if (await response.text()).strip() != "Ok.":
                raise PriorityError("qBittorrent authentication failed")

        async def exact_torrent():
            async with client.get(
                f"{base}/api/v2/torrents/info",
                params={"hashes": torrent_hash},
            ) as response:
                response.raise_for_status()
                torrents = await response.json()

            if not isinstance(torrents, list) or len(torrents) != 1:
                raise PriorityError(
                    "Expected exactly one torrent in qBittorrent"
                )

            torrent = torrents[0]

            if (
                not isinstance(torrent, dict)
                or not isinstance(torrent.get("hash"), str)
                or torrent["hash"].lower() != torrent_hash
            ):
                raise PriorityError("Exact torrent hash mismatch")

            category = torrent.get("category")

            if category not in ("radarr", "sonarr"):
                raise PriorityError("Torrent has an unexpected category")

            if expected_category and category != expected_category:
                raise PriorityError("Torrent category mismatch")

            return torrent

        await exact_torrent()

        async with client.post(
            f"{base}/api/v2/torrents/addTags",
            data={"hashes": torrent_hash, "tags": PRIORITY_TAG},
        ) as response:
            response.raise_for_status()

        updated = await exact_torrent()

        if PRIORITY_TAG not in {
            tag.strip() for tag in updated.get("tags", "").split(",")
        }:
            raise PriorityError("Priority tag could not be verified")

        async with client.post(
            f"{base}/api/v2/torrents/start",
            data={"hashes": torrent_hash},
        ) as response:
            response.raise_for_status()

        return True

    if session is not None:
        return await execute(session)

    timeout = aiohttp.ClientTimeout(total=20)
    cookie_jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        timeout=timeout,
        cookie_jar=cookie_jar,
    ) as client:
        return await execute(client)

    return True
async def find_radarr_download(tmdb_id):
    """Find torrent hashes for a movie using its TMDB ID."""
    base = os.environ["RADARR_URL"].rstrip("/")
    headers = {"X-Api-Key": os.environ["RADARR_API_KEY"]}
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        headers=headers, timeout=timeout
    ) as session:
        async with session.get(f"{base}/api/v3/movie") as response:
            response.raise_for_status()
            movies = await response.json()

        movie_ids = {
            movie["id"] for movie in movies
            if movie.get("tmdbId") == int(tmdb_id)
        }

        if not movie_ids:
            return []

        async with session.get(
            f"{base}/api/v3/queue",
            params={"page": 1, "pageSize": 100},
        ) as response:
            response.raise_for_status()
            queue = await response.json()

    return list({
        record["downloadId"].lower()
        for record in queue.get("records", [])
        if record.get("movieId") in movie_ids
        and record.get("protocol") == "torrent"
        and record.get("downloadId")
    })


async def find_sonarr_download(tvdb_id):
    """Find torrent hashes associated with a Sonarr series."""
    base = os.environ["SONARR_URL"].rstrip("/")
    headers = {"X-Api-Key": os.environ["SONARR_API_KEY"]}
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        headers=headers, timeout=timeout
    ) as session:
        async with session.get(f"{base}/api/v3/series") as response:
            response.raise_for_status()
            series = await response.json()

        series_ids = {
            item["id"] for item in series
            if item.get("tvdbId") == int(tvdb_id)
        }

        if not series_ids:
            return []

        async with session.get(
            f"{base}/api/v3/queue",
            params={"page": 1, "pageSize": 100},
        ) as response:
            response.raise_for_status()
            queue = await response.json()

    return list({
        record["downloadId"].lower()
        for record in queue.get("records", [])
        if record.get("seriesId") in series_ids
        and record.get("protocol") == "torrent"
        and record.get("downloadId")
    })
