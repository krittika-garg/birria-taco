import re

import pytest

from security.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
)

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pymongo as pm

import security.refresh_tokens as refresh


def test_generated_tokens_are_distinct_and_url_safe():
    first = generate_refresh_token()
    second = generate_refresh_token()
    assert first != second
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', first)
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', second)


def test_hash_is_repeatable_and_not_the_original_token():
    token = generate_refresh_token()
    hashed = hash_refresh_token(token)
    assert hashed == hash_refresh_token(token)
    assert hashed != token
    assert re.fullmatch(r'[0-9a-f]{64}', hashed)


def test_different_tokens_have_different_hashes():
    assert hash_refresh_token('first') != hash_refresh_token('second')


@pytest.mark.parametrize('token', ['', None, 42, True, [], {}])
def test_hash_rejects_invalid_input(token):
    with pytest.raises(ValueError):
        hash_refresh_token(token)


@patch('security.refresh_tokens.dbc.connect_db')
def test_refresh_collection_indexes(connect):
    collection = connect.return_value[dbc_name()][refresh.COLLECTION]

    assert refresh._collection() is collection
    collection.create_index.assert_any_call('token_hash', unique=True)
    collection.create_index.assert_any_call(
        'expires_at', expireAfterSeconds=0)


def dbc_name():
    return refresh.dbc.SE_DB


@patch('security.refresh_tokens._collection')
def test_issue_refresh_token(collection):
    before = datetime.now(timezone.utc)
    token = refresh.issue_refresh_token('bob')
    after = datetime.now(timezone.utc)

    stored = collection.return_value.insert_one.call_args.args[0]
    assert stored['username'] == 'bob'
    assert stored['token_hash'] == refresh.hash_refresh_token(token)
    assert stored['token_hash'] != token
    lifetime = timedelta(days=refresh.REFRESH_TOKEN_DAYS)
    assert before + lifetime <= stored['expires_at'] <= after + lifetime


@pytest.mark.parametrize('username', ['', None, 42, True])
@patch('security.refresh_tokens._collection')
def test_issue_rejects_invalid_username(collection, username):
    with pytest.raises(ValueError, match='username'):
        refresh.issue_refresh_token(username)
    collection.assert_not_called()


@pytest.mark.parametrize('token', ['', None, 42, {'$ne': None}])
@patch('security.refresh_tokens._collection')
def test_redeem_and_revoke_reject_invalid_input(collection, token):
    with pytest.raises(ValueError):
        refresh.redeem_refresh_token(token)
    with pytest.raises(ValueError):
        refresh.revoke_refresh_token(token)
    collection.assert_not_called()


@pytest.fixture
def live_tokens():
    """Point the module at a throwaway collection on a real local Mongo."""
    client = pm.MongoClient('mongodb://localhost:27017/',
                            serverSelectionTimeoutMS=500)
    try:
        client.admin.command('ping')
    except pm.errors.PyMongoError:
        client.close()
        pytest.skip('MongoDB is not reachable')
    database = f'test_{uuid4().hex}'
    collection = client[database][refresh.COLLECTION]
    try:
        with patch('security.refresh_tokens._collection',
                   return_value=collection):
            yield collection
    finally:
        client.drop_database(database)
        client.close()


def test_redeem_works_only_once(live_tokens):
    token = refresh.issue_refresh_token('bob')
    assert refresh.redeem_refresh_token(token) == 'bob'
    assert refresh.redeem_refresh_token(token) is None


def test_redeem_unknown_token(live_tokens):
    assert refresh.redeem_refresh_token('never-issued') is None


def test_redeem_rejects_expired_token(live_tokens):
    token = refresh.issue_refresh_token('bob')
    live_tokens.update_one(
        {'token_hash': refresh.hash_refresh_token(token)},
        {'$set': {'expires_at': datetime.now(timezone.utc)
                  - timedelta(seconds=1)}},
    )
    assert refresh.redeem_refresh_token(token) is None


def test_concurrent_redeems_have_one_winner(live_tokens):
    token = refresh.issue_refresh_token('bob')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(refresh.redeem_refresh_token, [token] * 8))
    assert results.count('bob') == 1
    assert results.count(None) == 7


def test_revoke_stops_redemption(live_tokens):
    token = refresh.issue_refresh_token('bob')
    refresh.revoke_refresh_token(token)
    assert refresh.redeem_refresh_token(token) is None
    refresh.revoke_refresh_token(token)
