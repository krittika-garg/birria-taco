"""Generate refresh tokens and hash them for database storage."""

import hashlib
import secrets

REFRESH_TOKEN_DAYS = 7


def generate_refresh_token():
    """Return a random refresh token with 256 bits of randomness."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token):
    """Return the token hash; only this hash should be stored."""
    if not isinstance(token, str) or not token:
        raise ValueError('refresh token must be a nonempty string')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
