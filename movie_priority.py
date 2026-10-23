"""Movie priority workflow for Nexus Requests."""

import os

import aiohttp

from priority_store import add_job, load_jobs, update_job


class MoviePriorityError(Exception):
    """A movie priority request failed validation or execution."""


def validate_movie_request(request_id, request):
    """Validate a pending Seerr movie request without modifying it."""

    if not isinstance(request, dict):
        raise MoviePriorityError("Invalid Seerr request data")

    if str(request.get("id")) != str(request_id):
        raise MoviePriorityError("Seerr request ID mismatch")

    if request.get("status") != 1:
        raise MoviePriorityError("Request is not pending")

    if request.get("type") != "movie":
        raise MoviePriorityError(
            "Priority workflow currently supports movies only"
        )

    media = request.get("media")

    if not isinstance(media, dict):
        raise MoviePriorityError("Missing movie information")

    tmdb_id = media.get("tmdbId")

    if not isinstance(tmdb_id, int) or tmdb_id <= 0:
        raise MoviePriorityError("Invalid TMDB movie ID")

    return tmdb_id


def prepare_movie_priority(request_id, request):
    """
    Validate and record priority intent.

    Does not approve Seerr requests or contact qBittorrent.
    """

    tmdb_id = validate_movie_request(request_id, request)

    if str(request_id) in load_jobs():
        raise MoviePriorityError(
            f"Request #{request_id} already has a priority job"
        )

    try:
        return add_job(
            request_id,
            "movie",
            tmdb_id,
            approval_confirmed=False,
            dry_run_verified=False,
        )
    except ValueError as exc:
        raise MoviePriorityError(str(exc)) from exc


async def approve_movie_priority(request_id, request, *, session=None):
    """
    Record priority intent, approve, and read back the exact Seerr request.

    Does not tag or start torrents.
    """

    prepared = prepare_movie_priority(request_id, request)
    expected_tmdb_id = prepared["media_id"]

    from seerr_config_adapter import load_seerr_config

    seerr = load_seerr_config()
    base = seerr["url"]
    headers = {"X-Api-Key": seerr["api_key"]}

    async def send_approval(client):
        request_url = f"{base}/api/v1/request/{request_id}"

        async with client.post(f"{request_url}/approve") as response:
            response.raise_for_status()

        async with client.get(request_url) as response:
            response.raise_for_status()
            confirmed = await response.json()

        if not isinstance(confirmed, dict):
            raise MoviePriorityError("Invalid approval confirmation")

        media = confirmed.get("media")

        if (
            str(confirmed.get("id")) != str(request_id)
            or confirmed.get("status") != 2
            or confirmed.get("type") != "movie"
            or not isinstance(media, dict)
            or media.get("tmdbId") != expected_tmdb_id
        ):
            raise MoviePriorityError(
                "Seerr did not confirm approval of the intended movie"
            )

    try:
        if session is None:
            async with aiohttp.ClientSession(headers=headers) as client:
                await send_approval(client)
        else:
            await send_approval(session)

    except Exception as exc:
        raise MoviePriorityError(
            f"Priority intent recorded for request #{request_id}, "
            "but Seerr approval was not confirmed. "
            "Manual review required before retrying."
        ) from exc

    return update_job(
        request_id,
        expected_status="waiting",
        approval_confirmed=True,
    )


async def execute_movie_priority(request_id, *, enabled=False):
    """Claim and start an approved movie job when explicitly enabled."""
    from datetime import datetime, timezone

    from priority import find_radarr_download, prioritize_torrent
    from priority_store import transition_job

    if enabled is not True:
        raise MoviePriorityError("Movie priority execution is disabled")

    def validate_job(job):
        if not isinstance(job, dict):
            raise MoviePriorityError("Priority job not found")

        if job.get("media_type") != "movie":
            raise MoviePriorityError("Only movie jobs can execute")

        if job.get("approval_confirmed") is not True:
            raise MoviePriorityError("Seerr approval is not confirmed")

        media_id = job.get("media_id")

        if type(media_id) is not int or media_id <= 0:
            raise MoviePriorityError("Invalid movie ID")

        return media_id

    key = str(request_id)
    job = load_jobs().get(key)
    media_id = validate_job(job)

    if job.get("status") != "waiting":
        raise MoviePriorityError("Priority job is not waiting")

    matches = await find_radarr_download(media_id)

    if not matches:
        return None

    if len(matches) != 1:
        raise MoviePriorityError("Movie torrent match is ambiguous")

    torrent_hash = matches[0]

    if (
        not isinstance(torrent_hash, str)
        or len(torrent_hash) not in (40, 64)
        or any(c not in "0123456789abcdef" for c in torrent_hash.lower())
    ):
        raise MoviePriorityError("Invalid movie torrent hash")

    torrent_hash = torrent_hash.lower()

    try:
        claimed = transition_job(
            request_id,
            "processing",
            execution_hash=torrent_hash,
            priority_started=False,
        )
    except ValueError as exc:
        raise MoviePriorityError(
            "Priority job could not be claimed"
        ) from exc

    try:
        claimed_media_id = validate_job(claimed)

        if claimed_media_id != media_id:
            raise MoviePriorityError("Movie identity changed during claim")

        current_matches = await find_radarr_download(media_id)

        if (
            len(current_matches) != 1
            or not isinstance(current_matches[0], str)
            or current_matches[0].lower() != torrent_hash
        ):
            raise MoviePriorityError("Movie torrent changed after claim")

        started = await prioritize_torrent(
            torrent_hash,
            expected_category="radarr",
        )

        if started is not True:
            raise MoviePriorityError("Torrent start was not confirmed")

        return update_job(
            request_id,
            expected_status="processing",
            priority_started=True,
            priority_started_at=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as exc:
        transition_job(
            request_id,
            "failed",
            execution_error=type(exc).__name__,
            manual_review_required=True,
        )
        raise MoviePriorityError(
            "Movie priority execution failed; manual review required "
            "before retrying"
        ) from exc
