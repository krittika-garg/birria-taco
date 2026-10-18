"""JWT authentication for protected Flask routes."""

from functools import wraps

import jwt
from flask import current_app, g, request

from security.tokens import decode_access_token


def login_required(fn):
    """Require a valid Bearer access token."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get('Authorization', '').split()
        if len(header) != 2 or header[0].lower() != 'bearer':
            return {'Message': 'Login required'}, 401

        secret = current_app.config.get('JWT_SECRET_KEY')
        if not secret:
            current_app.logger.error('JWT_SECRET_KEY is not configured')
            return {'Message': 'Authentication unavailable'}, 503

        try:
            claims = decode_access_token(header[1], secret)
        except jwt.InvalidTokenError:
            return {'Message': 'Invalid or expired access token'}, 401

        username = claims['sub']
        if not isinstance(username, str) or not username:
            return {'Message': 'Invalid access token'}, 401

        g.current_user = username
        return fn(*args, **kwargs)

    return wrapper
