"""Fail-closed validation of Seerr TV requests."""


class TVRequestError(Exception):
    """Seerr TV request is not eligible for priority."""


def validate_tv_request(request_id, request):
    """Return TMDB ID, TVDB ID, and requested season numbers."""

    if not isinstance(request, dict):
        raise TVRequestError("Invalid request data")

    if type(request_id) is not int or request_id <= 0:
        raise TVRequestError("Invalid request ID")

    if request.get("id") != request_id:
        raise TVRequestError("Request ID mismatch")

    if request.get("status") != 1:
        raise TVRequestError("Request is not pending")

    if request.get("type") != "tv":
        raise TVRequestError("Request is not television")

    media = request.get("media")
    if not isinstance(media, dict):
        raise TVRequestError("Missing media information")

    tmdb_id = media.get("tmdbId")
    tvdb_id = media.get("tvdbId")

    if type(tmdb_id) is not int or tmdb_id <= 0:
        raise TVRequestError("Invalid TMDB ID")

    if type(tvdb_id) is not int or tvdb_id <= 0:
        raise TVRequestError("Invalid TVDB ID")

    seasons = request.get("seasons")

    if not isinstance(seasons, list) or not seasons:
        raise TVRequestError("No requested seasons")

    numbers = []

    for season in seasons:
        if not isinstance(season, dict):
            raise TVRequestError("Malformed season entry")

        number = season.get("seasonNumber")

        if type(number) is not int or number < 0:
            raise TVRequestError("Invalid season number")

        if number in numbers:
            raise TVRequestError("Duplicate season number")

        numbers.append(number)

    return tmdb_id, tvdb_id, sorted(numbers)
