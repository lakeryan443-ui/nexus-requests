"""Offline regression tests for TV eligibility."""

from tv_eligibility import (
    TVEligibilityError,
    verify_season_coverage,
)

HASH = "a" * 40


def record(season, series=4, protocol="torrent"):
    return {
        "seriesId": series,
        "seasonNumber": season,
        "protocol": protocol,
        "downloadId": HASH,
    }


def check(name, records, seasons, expected):
    try:
        verify_season_coverage(
            records, 4, seasons, HASH
        )
        accepted = True
    except TVEligibilityError:
        accepted = False

    passed = accepted == expected
    print(
        f"{name:.<44} "
        f"{'PASS' if passed else 'FAIL'}"
    )
    return passed


def main():
    cases = [
        ("Single season", [record(1)], [1], True),
        (
            "Complete multi-season",
            [record(1), record(2)],
            [1, 2], True,
        ),
        (
            "Missing requested season",
            [record(1)], [1, 2], False,
        ),
        (
            "Extra unrequested season",
            [record(1), record(2)],
            [1], False,
        ),
        (
            "Cross-series collision",
            [record(1), record(1, series=9)],
            [1], False,
        ),
        (
            "Invalid protocol",
            [record(1, protocol="usenet")],
            [1], False,
        ),
    ]

    results = [
        check(name, records, seasons, expected)
        for name, records, seasons, expected in cases
    ]

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
    main()
