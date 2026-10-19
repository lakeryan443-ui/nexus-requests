"""Read-only TV request eligibility checks."""

import os

import aiohttp

from tv_request import validate_tv_request
from tv_series import resolve_sonarr_series
from tv_scope import match_tv_downloads
from tv_priority import fetch_verified_sonarr_queue
from qbt_verify import verify_torrent


class TVEligibilityError(Exception):
    """TV request cannot safely qualify for priority."""


def verify_season_coverage(
    records, series_id, seasons, torrent_hash
):
    """Require exact requested-season coverage."""
    if not isinstance(records, list):
        raise TVEligibilityError("Invalid queue records")

    if not isinstance(torrent_hash, str):
        raise TVEligibilityError("Invalid torrent hash")

    torrent_hash = torrent_hash.strip().lower()
    if not torrent_hash:
        raise TVEligibilityError("Empty torrent hash")

    expected = set(seasons)
    covered = set()

    for record in records:
        if not isinstance(record, dict):
            raise TVEligibilityError(
                "Malformed queue record"
            )

        download_id = record.get("downloadId")
        if not isinstance(download_id, str):
            continue

        if download_id.strip().lower() != torrent_hash:
            continue

        if record.get("seriesId") != series_id:
            raise TVEligibilityError(
                "Torrent belongs to another series"
            )

        if record.get("protocol") != "torrent":
            raise TVEligibilityError(
                "Invalid download protocol"
            )

        season = record.get("seasonNumber")
        if type(season) is not int or season < 0:
            raise TVEligibilityError(
                "Invalid season association"
            )

        covered.add(season)

    if covered != expected:
        raise TVEligibilityError(
            "Torrent does not cover requested seasons"
        )


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

        verify_season_coverage(
            records, series_id, seasons, hashes[0]
        )

        verified = await verify_torrent(
            hashes[0],
            expected_category="sonarr",
        )

        if (
            not isinstance(verified, dict)
            or verified.get("hash") != hashes[0]
            or verified.get("category") != "sonarr"
        ):
            raise TVEligibilityError(
                "qBittorrent verification mismatch"
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
