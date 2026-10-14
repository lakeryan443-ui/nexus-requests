import asyncio

from dotenv import load_dotenv
from tv_priority import fetch_verified_sonarr_queue, queue_fingerprint
from tv_scope import match_tv_downloads

load_dotenv("/opt/nexus-requests/.env")


def check(name, success):
    print(f"{name:.<44} {'PASS' if success else 'FAIL'}")
    return int(success)


async def main():
    passed = 0
    total = 6

    try:
        records = await fetch_verified_sonarr_queue(page_size=3)
    except Exception as exc:
        print(f"{'Live queue retrieval':.<44} FAIL")
        print(f"Error: {type(exc).__name__}: {exc}")
        print("\nRESULT: 0 PASSED | 1 FAILED")
        return

    passed += check("Verified live queue retrieval", isinstance(records, list))
    passed += check(
        "Unique queue record IDs",
        len({r["id"] for r in records}) == len(records),
    )
    passed += check(
        "Reacher Season 1 matching",
        len(match_tv_downloads(records, 4, [1])) == 1,
    )

    original = [{
        "id": 101,
        "seriesId": 4,
        "seasonNumber": 1,
        "episodeId": 61,
        "protocol": "torrent",
        "downloadId": "a" * 40,
    }]

    changed = [dict(original[0])]
    changed[0]["seasonNumber"] = 2

    replaced = [dict(original[0])]
    replaced[0]["downloadId"] = "b" * 40

    progress = [dict(original[0])]
    progress[0]["status"] = "downloading"
    progress[0]["sizeleft"] = 500000000

    passed += check(
        "Season association change detected",
        queue_fingerprint(original) != queue_fingerprint(changed),
    )
    passed += check(
        "Torrent replacement detected",
        queue_fingerprint(original) != queue_fingerprint(replaced),
    )
    passed += check(
        "Progress changes safely ignored",
        queue_fingerprint(original) == queue_fingerprint(progress),
    )

    print(f"\nRESULT: {passed} PASSED | {total - passed} FAILED")


asyncio.run(main())
