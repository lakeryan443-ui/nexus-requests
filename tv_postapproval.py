
"""Read-only lookup of a Sonarr-selected TV download."""

import os

import aiohttp

from tv_series import resolve_sonarr_series
from tv_scope import match_tv_downloads
from tv_priority import fetch_verified_sonarr_queue


class TVPostApprovalError(Exception):
    """A TV priority job could not be matched safely."""


async def verify_approved_tv_job(job):
    """
    Find the torrent Sonarr queued for an approved TV request.

    Return None while no matching download is queued.
    Does not select releases, change jobs, or start torrents.
    """
    if not isinstance(job, dict):
        raise TVPostApprovalError("Invalid TV priority job")

    request_id = job.get("request_id")
    tmdb_id = job.get("media_id")
    tvdb_id = job.get("tvdb_id")
    seasons = job.get("requested_seasons")

    if (
        type(request_id) is not int
        or request_id <= 0
        or job.get("media_type") != "tv"
        or job.get("status") != "waiting"
        or job.get("approval_confirmed") is not True
        or type(tmdb_id) is not int
        or tmdb_id <= 0
        or type(tvdb_id) is not int
        or tvdb_id <= 0
        or not isinstance(seasons, list)
        or not seasons
        or any(type(s) is not int or s < 0 for s in seasons)
        or len(seasons) != len(set(seasons))
    ):
        raise TVPostApprovalError(
            "TV job identity or approval state invalid"
        )

    try:
        base = os.environ["SONARR_URL"].rstrip("/")
        headers = {"X-Api-Key": os.environ["SONARR_API_KEY"]}

        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
        ) as session:
            async with session.get(
                f"{base}/api/v3/series"
            ) as response:
                response.raise_for_status()
                series = await response.json()

        series_id = resolve_sonarr_series(
            series, tmdb_id, tvdb_id
        )

        records = await fetch_verified_sonarr_queue()

        hashes = match_tv_downloads(
            records, series_id, seasons
        )

        if not hashes:
            return None

        if len(hashes) != 1:
            raise TVPostApprovalError(
                "Multiple associated torrents; manual review required"
            )

        return {
            "request_id": request_id,
            "series_id": series_id,
            "torrent_hash": hashes[0],
        }

    except TVPostApprovalError:
        raise
    except Exception as exc:
        raise TVPostApprovalError(
            "TV download lookup failed"
        ) from exc
