"""Read-only Sonarr queue utilities for Nexus Requests TV priority."""

import os

import aiohttp


class TVQueueError(Exception):
    """Sonarr queue could not be retrieved safely."""


def queue_fingerprint(records):
    """Return a stable representation of queue identity and scope."""

    if not isinstance(records, list):
        raise TVQueueError("Invalid queue records")

    fingerprints = []

    for record in records:
        if not isinstance(record, dict):
            raise TVQueueError("Malformed queue record")

        download_id = record.get("downloadId")

        if isinstance(download_id, str):
            download_id = download_id.strip().lower()

        fingerprints.append((
            record.get("id"),
            record.get("seriesId"),
            record.get("seasonNumber"),
            record.get("episodeId"),
            record.get("protocol"),
            download_id,
        ))

    return sorted(fingerprints, key=lambda item: item[0])


async def fetch_sonarr_queue(page_size=100):
    """Retrieve all Sonarr queue records, or fail closed."""

    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise ValueError("Invalid page size")

    base = os.environ["SONARR_URL"].rstrip("/")
    headers = {"X-Api-Key": os.environ["SONARR_API_KEY"]}

    records = []
    seen_ids = set()
    expected_total = None
    page = 1

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=timeout,
    ) as session:

        while True:
            async with session.get(
                f"{base}/api/v3/queue",
                params={
                    "page": page,
                    "pageSize": page_size,
                    "includeEpisode": "true",
                },
            ) as response:
                response.raise_for_status()
                data = await response.json()

            if not isinstance(data, dict):
                raise TVQueueError("Invalid Sonarr queue response")

            batch = data.get("records")
            total = data.get("totalRecords")

            if (
                not isinstance(batch, list)
                or type(total) is not int
                or total < 0
            ):
                raise TVQueueError("Invalid queue pagination data")

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise TVQueueError("Sonarr queue changed during pagination")

            if len(batch) > page_size:
                raise TVQueueError("Queue page exceeds requested size")

            if not batch and len(records) < expected_total:
                raise TVQueueError("Unexpected empty queue page")

            for item in batch:
                if not isinstance(item, dict):
                    raise TVQueueError("Malformed queue record")

                record_id = item.get("id")

                if type(record_id) is not int:
                    raise TVQueueError("Invalid queue record ID")

                if record_id in seen_ids:
                    raise TVQueueError("Duplicate queue record ID")

                seen_ids.add(record_id)
                records.append(item)

            if len(records) == expected_total:
                return records

            if len(records) > expected_total:
                raise TVQueueError("Queue contains excess records")

            page += 1


async def fetch_verified_sonarr_queue(page_size=100):
    """
    Read the complete queue twice and compare identity associations.

    Reject inconsistent snapshots before allowing season matching.
    """

    first = await fetch_sonarr_queue(page_size=page_size)
    second = await fetch_sonarr_queue(page_size=page_size)

    if queue_fingerprint(first) != queue_fingerprint(second):
        raise TVQueueError(
            "Sonarr queue associations changed during verification"
        )

    return second
