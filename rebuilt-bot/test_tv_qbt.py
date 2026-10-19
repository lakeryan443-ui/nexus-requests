"""Read-only Sonarr to qBittorrent identity verification."""

import asyncio

from dotenv import load_dotenv
from tv_priority import fetch_verified_sonarr_queue
from tv_scope import match_tv_downloads
from qbt_verify import verify_torrent

load_dotenv("/opt/nexus-requests/.env")


def check(name, success):
    print(f"{name:.<44} {'PASS' if success else 'FAIL'}")
    return int(success)


async def main():
    passed = 0
    total = 4

    try:
        records = await fetch_verified_sonarr_queue(page_size=3)
        hashes = match_tv_downloads(records, 4, [1])

        passed += check(
            "Unique Season 1 torrent",
            len(hashes) == 1,
        )

        if len(hashes) != 1:
            print("\nVerification stopped: no unique torrent")
            return

        torrent = await verify_torrent(
            hashes[0],
            expected_category="sonarr",
        )

        passed += check(
            "Exact torrent hash verified",
            torrent.get("hash", "").lower() == hashes[0],
        )

        passed += check(
            "Sonarr category verified",
            torrent.get("category") == "sonarr",
        )

        passed += check(
            "Torrent state available",
            isinstance(torrent.get("state"), str)
            and bool(torrent["state"]),
        )

        print("\nTorrent state:", torrent.get("state"))
        print(f"\nRESULT: {passed} PASSED | {total - passed} FAILED")

    except Exception as exc:
        print(f"{'Torrent verification':.<44} FAIL")
        print(f"Error: {type(exc).__name__}: {exc}")
        print("\nRESULT: Verification incomplete")


asyncio.run(main())
