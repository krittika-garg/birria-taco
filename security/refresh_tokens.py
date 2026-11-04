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


def _collection():
    collection = dbc.connect_db()[dbc.SE_DB][COLLECTION]
    collection.create_index('token_hash', unique=True)
    collection.create_index('expires_at', expireAfterSeconds=0)
    return collection


def issue_refresh_token(username):
    """Store a token's hash and expiration; return the raw token."""
    if not isinstance(username, str) or not username:
        raise ValueError('username must be a nonempty string')

    token = generate_refresh_token()
    _collection().insert_one({
        'token_hash': hash_refresh_token(token),
        'username': username,
        'expires_at': (
            datetime.now(timezone.utc)
            + timedelta(days=REFRESH_TOKEN_DAYS)
        ),
    })
    return token


def redeem_refresh_token(token):
    """Consume a live token and return its username, or None if invalid."""
    token_hash = hash_refresh_token(token)
    # Atomic, so a token works once. Expiry is checked here because
    # Mongo's TTL cleanup only runs periodically.
    doc = _collection().find_one_and_delete({
        'token_hash': token_hash,
        'expires_at': {'$gt': datetime.now(timezone.utc)},
    })
    return doc['username'] if doc else None


def revoke_refresh_token(token):
    """Delete a token if it exists."""
    token_hash = hash_refresh_token(token)
    _collection().delete_one({'token_hash': token_hash})
