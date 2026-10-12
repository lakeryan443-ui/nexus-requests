import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("/opt/nexus-requests/.env")

from priority_store import load_jobs, update_job
from priority import find_radarr_download, find_sonarr_download
from qbt_verify import verify_torrent

logger = logging.getLogger("nexus.priority")


async def check_priority_jobs(raise_errors=False):
    """
    Read-only inspection of waiting priority jobs.

    Does not approve requests, tag torrents,
    or start downloads.
    """

    jobs = load_jobs()

    for request_id, job in jobs.items():

        if job.get("status") != "waiting":
            continue

        media_type = job.get("media_type")
        media_id = job.get("media_id")

        logger.info(
            "Checking priority request #%s (%s, ID %s)",
            request_id,
            media_type,
            media_id,
        )

        try:
            if media_type == "movie":
                matches = await find_radarr_download(media_id)

            elif media_type == "tv":
                # TV jobs must contain a verified TVDB ID.
                tvdb_id = job.get("tvdb_id")

                if not tvdb_id:
                    logger.warning(
                        "Request #%s: TVDB ID missing; skipping",
                        request_id,
                    )
                    continue

                # Episode/season matching is not implemented yet.
                logger.warning(
                    "Request #%s: TV priority matching is not yet "
                    "episode-safe; skipping",
                    request_id,
                )
                continue

            else:
                logger.warning(
                    "Request #%s: unsupported media type %s",
                    request_id,
                    media_type,
                )
                continue

            if matches:
                if len(matches) != 1:
                    logger.warning(
                        "Request #%s: found %d torrents; "
                        "skipping ambiguous priority action",
                        request_id,
                        len(matches),
                    )
                    continue

                torrent_hash = matches[0]
                torrent = await verify_torrent(
                    torrent_hash,
                    expected_category="radarr",
                )
                # Persist verified information without changing
                # the job's waiting status or touching qBittorrent.
                update_job(
                    request_id,
                    verified_hash=torrent_hash,
                    verified_name=torrent["name"],
                    verified_category=torrent["category"],
                    verified_state=torrent["state"],
                    dry_run_verified=True,
                    verified_at=datetime.now(timezone.utc).isoformat(),
 )

                logger.info(
                    "  qBittorrent verification: PASS"
                )
                logger.info(
                    "  Torrent name: %s",
                    torrent["name"],
                )
                logger.info(
                    "  Category: %s",
                    torrent["category"],
                )
                logger.info(
                    "  Current state: %s",
                    torrent["state"],
                )
                logger.info(
                    "DRY RUN — Request #%s",
                    request_id,
                )
                logger.info(
                    "  Media type: %s",
                    media_type,
                )
                logger.info(
                    "  Media ID: %s",
                    media_id,
                )
                logger.info(
                    "  Torrent hash: %s",
                    torrent_hash,
                )
                logger.info(
                    "  Intended action: add nexus-priority tag "
                    "and start this torrent only"
                )
            else:
                update_job(
                    request_id,
                    verified_hash=None,
                    verified_name=None,
                    verified_category=None,
                    verified_state=None,
                    verified_at=None,
                    dry_run_verified=False,
                )
                logger.info(
                    "Request #%s: no matching torrent yet; previous verification cleared",
                    request_id,
                )

        except Exception:
            update_job(
                request_id,
                verified_hash=None,
                verified_name=None,
                verified_category=None,
                verified_state=None,
                verified_at=None,
                dry_run_verified=False,
            )
            logger.exception(
                "Request #%s: priority lookup failed; verification cleared",
                request_id,
            )
            if raise_errors:
                raise
async def priority_worker_loop(interval=30):
    """
    Periodically inspect priority jobs.

    Read-only until active processing is implemented.
    """

    while True:
        try:
            await check_priority_jobs()
        except Exception:
            logger.exception("Priority worker cycle failed")

        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    asyncio.run(check_priority_jobs())
