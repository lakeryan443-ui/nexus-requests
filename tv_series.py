"""Strict, read-only Seerr-to-Sonarr TV series identity matching."""


class TVSeriesError(Exception):
    """TV series identity could not be verified safely."""


def resolve_sonarr_series(series, tmdb_id, tvdb_id):
    """Return the unique Sonarr series ID matching both identifiers."""

    if type(tmdb_id) is not int or tmdb_id <= 0:
        raise TVSeriesError("Invalid TMDB ID")

    if type(tvdb_id) is not int or tvdb_id <= 0:
        raise TVSeriesError("Invalid TVDB ID")

    if not isinstance(series, list):
        raise TVSeriesError("Invalid Sonarr series response")

    matches = []

    for item in series:
        if not isinstance(item, dict):
            raise TVSeriesError("Malformed Sonarr series record")

        if (
            item.get("tmdbId") == tmdb_id
            and item.get("tvdbId") == tvdb_id
        ):
            series_id = item.get("id")

            if type(series_id) is not int or series_id <= 0:
                raise TVSeriesError("Invalid Sonarr series ID")

            matches.append(series_id)

    if len(matches) != 1:
        raise TVSeriesError(
            "Expected exactly one Sonarr series matching both IDs"
        )

    return matches[0]
