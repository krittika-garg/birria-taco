import re

import pytest

from security.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
)

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
