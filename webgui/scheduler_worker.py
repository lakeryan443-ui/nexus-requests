"""Nexus Requests qBittorrent download scheduler."""

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import aiohttp

from config_store import ConfigStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("nexus-scheduler")

CATEGORIES = {"radarr", "sonarr"}
PRIORITY_TAG = "nexus-priority"


def in_window(settings, now=None):
    zone = ZoneInfo(settings["timezone"])
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    clock = current.time().replace(tzinfo=None)

    def contains(start_text, end_text):
        start = time.fromisoformat(start_text)
        end = time.fromisoformat(end_text)
        if start == end:
            return False
        if start < end:
            return start <= clock < end
        return clock >= start

    if str(settings.get("advanced_enabled", "false")).lower() != "true":
        start = time.fromisoformat(settings["start_time"])
        end = time.fromisoformat(settings["end_time"])
        if start == end:
            return False
        if start < end:
            return start <= clock < end
        return clock >= start or clock < end

    import json
    from datetime import timedelta

    days = json.loads(settings.get("advanced_days") or "{}")
    if not isinstance(days, dict):
        raise ValueError("Advanced schedule must be an object")

    def get_day(index):
        key = ("monday", "tuesday", "wednesday", "thursday",
               "friday", "saturday", "sunday")[index]
        day = days[key]
        if not isinstance(day, dict) or not isinstance(day.get("enabled"), bool):
            raise ValueError(f"Invalid advanced schedule for {key}")
        if day["enabled"]:
            time.fromisoformat(day["start"])
            time.fromisoformat(day["end"])
        return day

    today = get_day(current.weekday())
    if not today["enabled"]:
        return True

    if contains(today["start"], today["end"]):
        return True

    previous = get_day((current - timedelta(days=1)).weekday())
    if previous["enabled"]:
        start = time.fromisoformat(previous["start"])
        end = time.fromisoformat(previous["end"])
        if start > end and clock < end:
            return True

    return False


async def run_once():
    store = ConfigStore()
    settings = store.load_internal("scheduler")

    if str(settings.get("enabled", "")).lower() != "true":
        log.info("Scheduler disabled; no action")
        return

    config = store.load_internal("qbittorrent")
    base = config["url"].rstrip("/")
    should_run = in_window(settings)

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        timeout=timeout,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    ) as client:
        async with client.post(
            f"{base}/api/v2/auth/login",
            data={
                "username": config["username"],
                "password": config["password"],
            },
        ) as response:
            response.raise_for_status()
            if (await response.text()).strip() != "Ok.":
                raise RuntimeError("qBittorrent authentication failed")

        async with client.get(
            f"{base}/api/v2/torrents/info"
        ) as response:
            response.raise_for_status()
            torrents = await response.json()

        hashes = []
        for torrent in torrents:
            if torrent.get("category") not in CATEGORIES:
                continue

            tags = {
                tag.strip()
                for tag in torrent.get("tags", "").split(",")
            }
            if PRIORITY_TAG in tags:
                continue

            state = torrent.get("state", "")

            if should_run:
                if state in {"pausedDL", "stoppedDL", "pausedUP", "stoppedUP"}:
                    hashes.append(torrent["hash"])
            else:
                if state not in {
                    "pausedDL", "stoppedDL",
                    "pausedUP", "stoppedUP",
                    "error", "missingFiles", "unknown",
                }:
                    hashes.append(torrent["hash"])

        if not hashes:
            log.info("No torrent changes needed")
            return

        action = "start" if should_run else "stop"

        async with client.post(
            f"{base}/api/v2/torrents/{action}",
            data={"hashes": "|".join(hashes)},
        ) as response:
            response.raise_for_status()

        log.info("%s requested for %d torrents", action, len(hashes))


async def main():
    log.info("Nexus Requests scheduler started")
    while True:
        try:
            await run_once()
        except Exception:
            log.exception("Scheduler cycle failed")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
