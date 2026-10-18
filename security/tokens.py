"""Create and validate short-lived JWT access tokens."""

from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = 'HS256'
ACCESS_TOKEN_MINUTES = 15
ISSUER = 'birria-taco'
AUDIENCE = 'birria-taco-api'


def create_access_token(user_id, secret):
    """Issue an access token identifying one user."""
    if not isinstance(user_id, str) or not user_id:
        raise ValueError('user_id must be a nonempty string')
    if not secret:
        raise ValueError('JWT secret is required')

    now = datetime.now(timezone.utc)
    payload = {
        'sub': user_id,
        'iat': now,
        'exp': now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        'iss': ISSUER,
        'aud': AUDIENCE,
        'type': 'access',
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token, secret):
    """Validate a token and return its claims."""
    if not secret:
        raise ValueError('JWT secret is required')

    claims = jwt.decode(
        token,
        secret,
        algorithms=[ALGORITHM],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={
            'require': ['sub', 'iat', 'exp', 'iss', 'aud', 'type'],
        },
    )
    if claims['type'] != 'access':
        raise jwt.InvalidTokenError('Expected an access token')
    return claims
