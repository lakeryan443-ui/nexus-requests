"""Read-only TV request eligibility checks."""

import os

import aiohttp

from tv_request import validate_tv_request
from tv_series import resolve_sonarr_series
from tv_scope import match_tv_downloads
from tv_priority import fetch_verified_sonarr_queue


class TVEligibilityError(Exception):
    """TV request cannot safely qualify for priority."""


async def check_tv_eligibility(request_id, request):
    """Return verified series, seasons, and torrent hashes."""

    try:
        tmdb_id, tvdb_id, seasons = validate_tv_request(
            request_id, request
        )

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
            raise TVEligibilityError(
                "No verified torrent for requested seasons"
            )

        if len(hashes) != 1:
            raise TVEligibilityError(
                "Expected exactly one matching torrent"
            )

        return {
            "series_id": series_id,
            "seasons": seasons,
            "torrent_hashes": hashes,
        }

    except TVEligibilityError:
        raise
    except Exception as exc:
        raise TVEligibilityError(
            "TV eligibility verification failed"
        ) from exc
