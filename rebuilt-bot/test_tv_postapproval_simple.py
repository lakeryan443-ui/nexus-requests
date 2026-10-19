
import asyncio
from unittest.mock import patch

import tv_postapproval as tv

HASH = "a" * 40

JOB = {
    "request_id": 10,
    "media_id": 123,
    "tvdb_id": 456,
    "media_type": "tv",
    "status": "waiting",
    "approval_confirmed": True,
    "requested_seasons": [1],
}


class FakeResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    async def json(self):
        return []


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, url):
        return FakeResponse()


async def fake_queue():
    return []


async def run():
    with (
        patch.dict("os.environ", {
            "SONARR_URL": "http://localhost",
            "SONARR_API_KEY": "test",
        }),
        patch.object(tv.aiohttp, "ClientSession", return_value=FakeSession()),
        patch.object(tv, "resolve_sonarr_series", return_value=99),
        patch.object(tv, "fetch_verified_sonarr_queue", side_effect=fake_queue),
        patch.object(tv, "match_tv_downloads", return_value=[]),
    ):
        result = await tv.verify_approved_tv_job(JOB)
        print("No torrent queued -> waiting:", "PASS" if result is None else "FAIL")

    with (
        patch.dict("os.environ", {
            "SONARR_URL": "http://localhost",
            "SONARR_API_KEY": "test",
        }),
        patch.object(tv.aiohttp, "ClientSession", return_value=FakeSession()),
        patch.object(tv, "resolve_sonarr_series", return_value=99),
        patch.object(tv, "fetch_verified_sonarr_queue", side_effect=fake_queue),
        patch.object(tv, "match_tv_downloads", return_value=[HASH]),
    ):
        result = await tv.verify_approved_tv_job(JOB)
        ok = result["torrent_hash"] == HASH
        print("Queued torrent identified:", "PASS" if ok else "FAIL")


asyncio.run(run())
