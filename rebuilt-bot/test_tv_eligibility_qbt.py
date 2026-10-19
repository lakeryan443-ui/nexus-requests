"""Offline qBittorrent integration tests for TV eligibility."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import tv_eligibility as tv


HASH = "a" * 40

REQUEST = {
    "id": 10,
    "status": 1,
    "type": "tv",
    "media": {
        "tmdbId": 108978,
        "tvdbId": 366924,
    },
    "seasons": [{"seasonNumber": 1}],
}

RECORDS = [{
    "id": 101,
    "seriesId": 4,
    "seasonNumber": 1,
    "protocol": "torrent",
    "downloadId": HASH,
}]


def fake_http_session():
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=[])

    get_context = MagicMock()
    get_context.__aenter__ = AsyncMock(
        return_value=response
    )
    get_context.__aexit__ = AsyncMock(
        return_value=None
    )

    session = MagicMock()
    session.get = MagicMock(
        return_value=get_context
    )

    context = MagicMock()
    context.__aenter__ = AsyncMock(
        return_value=session
    )
    context.__aexit__ = AsyncMock(
        return_value=None
    )
    return context


async def run_case(name, result, error, expected):
    verifier = AsyncMock()

    if error is not None:
        verifier.side_effect = error
    else:
        verifier.return_value = result

    with (
        patch.object(
            tv.aiohttp,
            "ClientSession",
            return_value=fake_http_session(),
        ),
        patch.object(
            tv,
            "validate_tv_request",
            return_value=(108978, 366924, [1]),
        ),
        patch.object(
            tv,
            "resolve_sonarr_series",
            return_value=4,
        ),
        patch.object(
            tv,
            "fetch_verified_sonarr_queue",
            new_callable=AsyncMock,
            return_value=RECORDS,
        ),
        patch.object(
            tv,
            "verify_torrent",
            verifier,
        ),
    ):
        accepted = False

        try:
            await tv.check_tv_eligibility(10, REQUEST)
            accepted = True
        except tv.TVEligibilityError:
            pass

        called = (
            verifier.await_count == 1
            and verifier.await_args.args == (HASH,)
            and verifier.await_args.kwargs
            == {"expected_category": "sonarr"}
        )

    passed = accepted == expected and called

    print(
        f"{name:.<44} "
        f"{'PASS' if passed else 'FAIL'}"
    )
    return passed


async def main():
    cases = [
        (
            "Valid torrent accepted",
            {"hash": HASH, "category": "sonarr"},
            None,
            True,
        ),
        (
            "Wrong category rejected",
            {"hash": HASH, "category": "radarr"},
            None,
            False,
        ),
        (
            "Wrong hash rejected",
            {"hash": "b" * 40, "category": "sonarr"},
            None,
            False,
        ),
        (
            "Missing torrent rejected",
            None,
            RuntimeError("Torrent missing"),
            False,
        ),
        (
            "Authentication failure rejected",
            None,
            RuntimeError("Authentication failed"),
            False,
        ),
    ]

    results = []

    for name, result, error, expected in cases:
        results.append(
            await run_case(
                name, result, error, expected
            )
        )

    passed = sum(results)
    failed = len(results) - passed

    print()
    print(
        f"RESULT: {passed} PASSED | "
        f"{failed} FAILED"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
