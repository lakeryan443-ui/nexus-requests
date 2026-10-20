
"""TV priority workflow for Nexus Requests."""

import os

import aiohttp

from priority_store import add_job, update_job
from tv_request import TVRequestError, validate_tv_request


class TVPriorityError(Exception):
    """A TV priority request failed validation or execution."""


def prepare_tv_priority(request_id, request):
    """
    Validate a pending TV request and record priority intent.

    Does not approve Seerr requests or start torrents.
    """
    try:
        tmdb_id, tvdb_id, seasons = validate_tv_request(
            request_id, request
        )

        return add_job(
            request_id,
            "tv",
            tmdb_id,
            tvdb_id=tvdb_id,
            requested_seasons=seasons,
            approval_confirmed=False,
            dry_run_verified=False,
        )

    except (ValueError, TVRequestError) as exc:
        raise TVPriorityError(
            "TV priority preparation failed"
        ) from exc


async def approve_tv_priority(request_id, request, *, session=None):
    """
    Record TV priority intent and request Seerr approval.

    Only a successful approval API response permits the priority
    job to be marked approved.

    Does not tag, prioritize, or start torrents.
    """
    prepared = prepare_tv_priority(request_id, request)

    if (
        prepared.get("request_id") != request_id
        or prepared.get("media_type") != "tv"
        or prepared.get("approval_confirmed") is not False
    ):
        raise TVPriorityError(
            "Prepared TV priority job has invalid identity or state"
        )

    try:
        base = os.environ["SEERR_URL"].rstrip("/")
        headers = {"X-Api-Key": os.environ["SEERR_API_KEY"]}
        request_url = f"{base}/api/v1/request/{request_id}"

        async def send_approval(client):
            async with client.post(f"{request_url}/approve") as response:
                response.raise_for_status()

            async with client.get(request_url) as response:
                response.raise_for_status()
                confirmed = await response.json()

            if not isinstance(confirmed, dict):
                raise TVPriorityError("Invalid approval confirmation")

            media = confirmed.get("media")

            if (
                str(confirmed.get("id")) != str(request_id)
                or confirmed.get("status") != 2
                or confirmed.get("type") != "tv"
                or not isinstance(media, dict)
                or media.get("tmdbId") != prepared["media_id"]
            ):
                raise TVPriorityError(
                    "Seerr did not confirm approval of the intended TV request"
                )

        if session is None:
            async with aiohttp.ClientSession(headers=headers) as client:
                await send_approval(client)
        else:
            await send_approval(session)

    except Exception as exc:
        raise TVPriorityError(
            f"TV priority intent recorded for request #{request_id}, "
            "but Seerr approval was not confirmed. "
            "Manual review required before retrying."
        ) from exc

    try:
        return update_job(
            request_id,
            expected_status="waiting",
            approval_confirmed=True,
        )
    except Exception as exc:
        raise TVPriorityError(
            f"Seerr approval succeeded for request #{request_id}, "
            "but the priority job could not be confirmed. "
            "Manual review required."
        ) from exc

async def execute_tv_priority(request_id, *, enabled=False):
    """
    Prioritize the Sonarr-selected torrent for an approved TV job.

    Returns False when the download has not yet been queued.
    TV execution must be explicitly enabled by its caller.
    """
    if enabled is not True:
        raise TVPriorityError("TV priority execution is disabled")

    from datetime import datetime, timezone

    from priority_store import load_jobs, transition_job
    from priority import prioritize_torrent
    from tv_postapproval import verify_approved_tv_job

    job = load_jobs().get(str(request_id))

    if (
        not isinstance(job, dict)
        or job.get("request_id") != request_id
        or job.get("media_type") != "tv"
        or job.get("status") != "waiting"
        or job.get("approval_confirmed") is not True
    ):
        raise TVPriorityError(
            "TV priority job is missing, unapproved, or not waiting"
        )

    try:
        match = await verify_approved_tv_job(job)
    except Exception as exc:
        raise TVPriorityError(
            "Unable to identify Sonarr's queued TV download"
        ) from exc

    if match is None:
        return False

    torrent_hash = match["torrent_hash"]

    claimed = transition_job(
        request_id,
        "processing",
        execution_hash=torrent_hash,
        priority_started=False,
    )

    try:
        if (
            claimed.get("request_id") != request_id
            or claimed.get("media_type") != "tv"
            or claimed.get("approval_confirmed") is not True
            or claimed.get("execution_hash") != torrent_hash
        ):
            raise TVPriorityError(
                "Claimed TV priority job identity mismatch"
            )

        started = await prioritize_torrent(
            torrent_hash,
            expected_category="sonarr",
        )

        if started is not True:
            raise TVPriorityError(
                "qBittorrent did not confirm priority execution"
            )

        return transition_job(
            request_id,
            "completed",
            priority_started=True,
            priority_started_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

    except Exception as exc:
        transition_job(
            request_id,
            "failed",
            execution_error=str(exc),
            manual_review_required=True,
        )
        raise TVPriorityError(
            f"TV priority execution failed for request #{request_id}"
        ) from exc
