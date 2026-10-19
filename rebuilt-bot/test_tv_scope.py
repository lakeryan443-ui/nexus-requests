"""Offline tests for Nexus Requests TV season matching."""

from tv_scope import match_tv_downloads


def record(torrent_hash, season, episode, series_id=4):
    return {
        "seriesId": series_id,
        "protocol": "torrent",
        "downloadId": torrent_hash,
        "seasonNumber": season,
        "episodeId": episode,
    }


def check(name, actual, expected):
    assert actual == expected, (
        f"{name}: expected {expected}, got {actual}"
    )
    print(f"PASS: {name}")


A = "a" * 40
B = "b" * 40
C = "c" * 40

# 1. Reacher Season 1: eight episodes, one torrent.
records = [record(A, 1, episode) for episode in range(61, 69)]
check(
    "Season pack deduplication",
    match_tv_downloads(records, 4, [1]),
    [A],
)

# 2. Separate torrents for different seasons.
records = [
    record(A, 1, 61),
    record(B, 2, 69),
]
check(
    "Season 1 only",
    match_tv_downloads(records, 4, [1]),
    [A],
)

# 3. Multiple requested seasons.
check(
    "Multiple requested seasons",
    match_tv_downloads(records, 4, [1, 2]),
    [A, B],
)

# 4. One torrent spanning requested and unrequested seasons.
records = [
    record(A, 1, 61),
    record(A, 2, 69),
]
check(
    "Mixed-season torrent rejected",
    match_tv_downloads(records, 4, [1]),
    [],
)

# 5. Missing season association.
records = [
    record(A, None, 61),
]
check(
    "Missing season rejected",
    match_tv_downloads(records, 4, [1]),
    [],
)

# 6. One ambiguous record invalidates its torrent.
records = [
    record(A, 1, 61),
    record(A, None, 62),
    record(B, 1, 63),
]
check(
    "Ambiguous torrent rejected independently",
    match_tv_downloads(records, 4, [1]),
    [B],
)

# 7. Other series must not match.
records = [
    record(A, 1, 61, series_id=99),
    record(C, 1, 62, series_id=4),
]
check(
    "Series isolation",
    match_tv_downloads(records, 4, [1]),
    [C],
)

print("\nAll 7 TV scope tests passed.")
