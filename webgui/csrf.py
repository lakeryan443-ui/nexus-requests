import secrets

from itsdangerous import BadSignature, SignatureExpired

from auth import get_serializer


CSRF_MAX_AGE = 3600


def create_csrf_token():
    """Create a signed CSRF token valid for one hour."""
    nonce = secrets.token_urlsafe(32)

    return get_serializer().dumps(
        {"nonce": nonce},
        salt="csrf-token",
    )


def verify_csrf_token(token):
    """Verify the token signature and expiration."""
    if not isinstance(token, str) or not token:
        return False

    try:
        data = get_serializer().loads(
            token,
            salt="csrf-token",
            max_age=CSRF_MAX_AGE,
        )

        return (
            isinstance(data, dict)
            and isinstance(data.get("nonce"), str)
            and len(data["nonce"]) >= 32
        )

    except (BadSignature, SignatureExpired):
        return False
