import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("/opt/nexus-requests/.env")

from priority_store import load_jobs, update_job, transition_job
from priority import find_radarr_download, find_sonarr_download
from qbt_verify import verify_torrent

logger = logging.getLogger("nexus.priority")

FINISHED_STATES = {
    "uploading",
    "stalledUP",
    "queuedUP",
    "pausedUP",
    "stoppedUP",
    "forcedUP",
}


def clear_waiting_verification(request_id):
    """Clear verification only while the job remains waiting."""
    return update_job(
        request_id,
        expected_status="waiting",
        verified_hash=None,
        verified_name=None,
        verified_category=None,
        verified_state=None,
        verified_at=None,
        dry_run_verified=False,
    )


async def check_processing_movie(request_id, job):
    """Observe one started movie torrent without modifying qBittorrent."""
    if job.get("priority_started") is not True:
        logger.warning(
            "Request #%s: interrupted execution needs manual review",
            request_id,
        )
        return

    torrent_hash = job.get("execution_hash")
    torrent = await verify_torrent(
        torrent_hash,
        expected_category="radarr",
    )

    if torrent.get("hash") != torrent_hash:
        raise ValueError("Processing torrent identity mismatch")

    state = torrent.get("state")
    progress = torrent.get("progress")

    if state in {"error", "missingFiles"}:
        update_job(
            request_id,
            expected_status="processing",
            last_state=state,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )
        transition_job(
            request_id,
            "failed",
            execution_error=state,
            manual_review_required=True,
        )
        logger.warning(
            "Request #%s: torrent failed with state %s",
            request_id,
            state,
        )
        return

    if (
        type(progress) not in (int, float)
        or not 0 <= progress <= 1
    ):
        raise ValueError("Invalid torrent progress")

    update_job(
        request_id,
        expected_status="processing",
        last_progress=progress,
        last_state=state,
        last_checked_at=datetime.now(timezone.utc).isoformat(),
    )

    if progress == 1 and state in FINISHED_STATES:
        transition_job(
            request_id,
            "completed",
            download_completed_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "Request #%s: torrent download completed",
            request_id,
        )


async def check_priority_jobs(
    raise_errors=False, *, execute=False, request_ids=None
):
    """
    Verify waiting jobs and observe started movie downloads.

    Tagging and starting require an explicit execute=True.
    Optional request_ids restricts all inspection and execution.
    Does not approve Seerr requests.
    """
    selected_ids = (
        None
        if request_ids is None
        else {str(request_id) for request_id in request_ids}
    )
    jobs = load_jobs()

    for request_id, job in jobs.items():
        if selected_ids is not None and str(request_id) not in selected_ids:
            continue

        status = job.get("status")

        if status not in {"waiting", "processing"}:
            continue

        if job.get("approval_confirmed") is not True:
            logger.info(
                "Request #%s: Seerr approval not confirmed; skipping",
                request_id,
            )
            continue

        media_type = job.get("media_type")
        media_id = job.get("media_id")

        if media_type != "movie":
            logger.warning(
                "Request #%s: only movie priority processing is supported; "
                "TV matching is not yet episode-safe",
                request_id,
            )
            continue

        try:
            if status == "processing":
                await check_processing_movie(request_id, job)
                continue

            matches = await find_radarr_download(media_id)

            if len(matches) != 1:
                clear_waiting_verification(request_id)
                logger.info(
                    "Request #%s: no unique torrent match; "
                    "verification cleared",
                    request_id,
                )
                continue

            torrent_hash = matches[0]
            torrent = await verify_torrent(
                torrent_hash,
                expected_category="radarr",
            )

            update_job(
                request_id,
                expected_status="waiting",
                verified_hash=torrent_hash,
                verified_name=torrent["name"],
                verified_category=torrent["category"],
                verified_state=torrent["state"],
                dry_run_verified=True,
                verified_at=datetime.now(timezone.utc).isoformat(),
            )

            if execute is True:
                from movie_priority import execute_movie_priority

                await execute_movie_priority(
                    request_id,
                    enabled=True,
                )
                continue

            logger.info(
                "DRY RUN — Request #%s: verified torrent %s; "
                "no tag or start action performed",
                request_id,
                torrent_hash,
            )

        except Exception as exc:
            if (
                isinstance(exc, ValueError)
                and str(exc).startswith("Job status changed:")
            ):
                logger.info(
                    "Request #%s: status changed during inspection; "
                    "discarding stale result",
                    request_id,
                )
                if raise_errors:
                    raise
                continue

            if status == "waiting":
                try:
                    clear_waiting_verification(request_id)
                except ValueError:
                    logger.warning(
                        "Request #%s: verification cleanup rejected; "
                        "skipping stale verification update",
                        request_id,
                    )

            logger.exception(
                "Request #%s: priority inspection failed",
                request_id,
            )

            if raise_errors:
                raise


async def priority_worker_loop(
    interval=30, *, execute=False, request_ids=None
):
    """Inspect selected jobs; torrent execution defaults to disabled."""
    while True:
        try:
            await check_priority_jobs(
                execute=execute,
                request_ids=request_ids,
            )
        except Exception:
            logger.exception("Priority worker cycle failed")

        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    asyncio.run(check_priority_jobs())
