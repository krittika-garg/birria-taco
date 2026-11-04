"""Issue, redeem and revoke refresh tokens; only hashes are stored."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import data.db_connect as dbc

REFRESH_TOKEN_DAYS = 7


def generate_refresh_token():
    """Return a random refresh token with 256 bits of randomness."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token):
    """Return the token hash; only this hash should be stored."""
    if not isinstance(token, str) or not token:
        raise ValueError('refresh token must be a nonempty string')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


COLLECTION = 'refresh_tokens'


DB = dbc.SE_DB  # read at call time so tests can point it elsewhere


def _ensure_indexes():
    dbc.create_index(COLLECTION, 'token_hash', unique=True, db=DB)
    dbc.create_index(COLLECTION, 'expires_at', expireAfterSeconds=0, db=DB)


def issue_refresh_token(username):
    """Store a token's hash and expiration; return the raw token."""
    if not isinstance(username, str) or not username:
        raise ValueError('username must be a nonempty string')

    token = generate_refresh_token()
    _ensure_indexes()
    dbc.create(COLLECTION, {
        'token_hash': hash_refresh_token(token),
        'username': username,
        'expires_at': (
            datetime.now(timezone.utc)
            + timedelta(days=REFRESH_TOKEN_DAYS)
        ),
    }, db=DB)
    return token


def redeem_refresh_token(token):
    """Consume a live token and return its username, or None if invalid."""
    token_hash = hash_refresh_token(token)
    # Atomic, so a token works once. Expiry is checked here because
    # Mongo's TTL cleanup only runs periodically.
    _ensure_indexes()
    doc = dbc.pop_one(COLLECTION, {
        'token_hash': token_hash,
        'expires_at': {'$gt': datetime.now(timezone.utc)},
    }, db=DB)
    return doc['username'] if doc else None


def revoke_refresh_token(token):
    """Delete a token if it exists."""
    token_hash = hash_refresh_token(token)
    _ensure_indexes()
    dbc.delete(COLLECTION, {'token_hash': token_hash}, db=DB)
