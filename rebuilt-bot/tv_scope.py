"""Pure, read-only matching of Sonarr queue records to requested seasons."""


def match_tv_downloads(records, series_id, requested_seasons):
    """
    Return unique torrent hashes matching the requested seasons.

    Every queue record sharing a torrent hash must belong to the
    requested series and requested seasons. Ambiguity fails closed.
    """
    if type(series_id) is not int or series_id <= 0:
        raise ValueError("Invalid Sonarr series ID")

    if (
        not isinstance(requested_seasons, (list, tuple, set))
        or not requested_seasons
        or any(
            type(season) is not int or season < 0
            for season in requested_seasons
        )
    ):
        raise ValueError("Invalid requested seasons")

    if not isinstance(records, list):
        raise ValueError("Invalid Sonarr queue records")

    requested = set(requested_seasons)
    grouped = {}

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Malformed Sonarr queue record")

        torrent_hash = record.get("downloadId")

        if not isinstance(torrent_hash, str):
            continue

        torrent_hash = torrent_hash.strip().lower()

        if not torrent_hash:
            continue

        group = grouped.setdefault(
            torrent_hash,
            {"seasons": set(), "valid": True, "target": False},
        )

        if record.get("seriesId") != series_id:
            group["valid"] = False
            continue

        group["target"] = True

        if record.get("protocol") != "torrent":
            group["valid"] = False
            continue

        season = record.get("seasonNumber")

        if type(season) is not int or season < 0:
            group["valid"] = False
            continue

        group["seasons"].add(season)

    matches = []

    for torrent_hash, group in grouped.items():
        if (
            group["target"]
            and group["valid"]
            and group["seasons"]
            and group["seasons"].issubset(requested)
        ):
            matches.append(torrent_hash)

    return sorted(matches)
