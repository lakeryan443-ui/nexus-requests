"""Shared movie/TV priority worker for Nexus Requests (staging candidate).

No Seerr calls: intake/approval belongs to optional integrations.
Execution is explicitly disabled by default.
"""
import asyncio
import logging
from datetime import datetime, timezone

from priority_store import load_jobs, update_job, transition_job
from priority import find_radarr_download, prioritize_torrent
from tv_postapproval import verify_approved_tv_job
from qbt_verify import verify_torrent

logger = logging.getLogger("nexus.priority")


async def update_discord_priority_status(discord_client, job):
    """Update the original request card without affecting downloads."""
    if discord_client is None:
        return

    channel_id = job.get("discord_channel_id")
    message_id = job.get("discord_message_id")

    if not channel_id or not message_id:
        return

    try:
        import discord

        await discord_client.wait_until_ready()

        channel = await discord_client.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))

        if not message.embeds:
            logger.warning(
                "Request %s: Discord card has no embed",
                job.get("request_id"),
            )
            return

        embed = message.embeds[0].copy()
        embed.description = "Priority Applied — Download Requested"
        embed.color = discord.Color.green()

        await message.edit(embed=embed)

    except Exception:
        logger.exception(
            "Request %s: Discord status update failed",
            job.get("request_id"),
        )


def torrent_category(media_type):
    return {"movie": "radarr", "tv": "sonarr"}.get(media_type)


async def find_job_torrent(job):
    """Return unique queued hash, or None if not yet queued."""
    media_type = job.get("media_type")
    if media_type == "movie":
        hashes = await find_radarr_download(job["media_id"])
        if len(hashes) > 1:
            raise ValueError("Multiple Radarr torrents; manual review required")
        return hashes[0] if hashes else None
    if media_type == "tv":
        match = await verify_approved_tv_job(job)
        return match["torrent_hash"] if match else None
    raise ValueError("Unsupported media type")


async def check_priority_jobs(raise_errors=False, *, execute=False, request_ids=None, discord_client=None):
    """Inspect approved waiting jobs; optionally tag/start an exact torrent.

    Does not approve Seerr requests or monitor completed downloads.
    """
    selected = None if request_ids is None else {str(i) for i in request_ids}
    for key, job in load_jobs().items():
        if selected is not None and key not in selected:
            continue
        if job.get("status") != "waiting" or job.get("approval_confirmed") is not True:
            continue
        category = torrent_category(job.get("media_type"))
        if category is None:
            logger.warning("Job %s: unknown media type", key)
            continue
        try:
            torrent_hash = await find_job_torrent(job)
            if torrent_hash is None:
                continue
            torrent = await verify_torrent(torrent_hash, expected_category=category)
            if torrent.get("hash", "").lower() != torrent_hash.lower():
                raise ValueError("Torrent identity mismatch")
            if not execute:
                logger.info("DRY RUN job %s: verified %s", key, torrent_hash)
                continue
            # Transition atomically before any qBittorrent write.
            claimed = transition_job(int(key), "processing", execution_hash=torrent_hash,
                                     priority_started=False)
            if claimed.get("execution_hash") != torrent_hash:
                raise ValueError("Claimed job hash mismatch")
            try:
                await prioritize_torrent(torrent_hash, expected_category=category)
                updated_job = update_job(
                    int(key),
                    expected_status="processing",
                    priority_started=True,
                    priority_started_at=datetime.now(timezone.utc).isoformat(),
                )
                completed_job = transition_job(
                    int(key),
                    "completed",
                    priority_started=True,
                )
                logger.info("Job %s: priority applied; job completed", key)
            except Exception:
                transition_job(int(key), "failed", manual_review_required=True,
                               execution_error="Priority execution failed; inspect qBittorrent")
                raise

            await update_discord_priority_status(
                discord_client,
                completed_job,
            )
        except Exception:
            logger.exception("Job %s: priority processing failed", key)
            if raise_errors:
                raise


async def priority_worker_loop(interval=30, *, execute=False, request_ids=None, discord_client=None):
    while True:
        await check_priority_jobs(execute=execute, request_ids=request_ids, discord_client=discord_client)
        await asyncio.sleep(interval)
