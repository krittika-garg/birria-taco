"""Tests for access-token issuance and validation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

import security.tokens as tokens

TEST_SECRET = 'test-only-secret-with-at-least-32-bytes'
OTHER_SECRET = 'another-test-secret-with-at-least-32-bytes'


@pytest.fixture
def access_token():
    return tokens.create_access_token('user-123', TEST_SECRET)


def test_valid_access_token(access_token):
    claims = tokens.decode_access_token(access_token, TEST_SECRET)

    assert claims['sub'] == 'user-123'
    assert claims['type'] == 'access'
    assert claims['exp'] - claims['iat'] == 15 * 60


def test_wrong_signing_key(access_token):
    with pytest.raises(jwt.InvalidSignatureError):
        tokens.decode_access_token(access_token, OTHER_SECRET)


def test_expired_access_token():
    past = datetime.now(timezone.utc) - timedelta(hours=1)

    with patch('security.tokens.datetime') as mock_datetime:
        mock_datetime.now.return_value = past
        token = tokens.create_access_token('user-123', TEST_SECRET)

    with pytest.raises(jwt.ExpiredSignatureError):
        tokens.decode_access_token(token, TEST_SECRET)


def test_modified_payload_is_rejected(access_token):
    header, payload, signature = access_token.split('.')
    replacement = jwt.utils.base64url_encode(
        b'{"sub":"someone-else"}'
    ).decode()
    modified = '.'.join([header, replacement, signature])

    with pytest.raises(jwt.InvalidSignatureError):
        tokens.decode_access_token(modified, TEST_SECRET)


def test_missing_expiration_is_rejected(access_token):
    claims = tokens.decode_access_token(access_token, TEST_SECRET)
    del claims['exp']
    token = jwt.encode(claims, TEST_SECRET, algorithm=tokens.ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        tokens.decode_access_token(token, TEST_SECRET)


def test_wrong_token_type_is_rejected(access_token):
    claims = tokens.decode_access_token(access_token, TEST_SECRET)
    claims['type'] = 'refresh'
    token = jwt.encode(claims, TEST_SECRET, algorithm=tokens.ALGORITHM)

    with pytest.raises(jwt.InvalidTokenError, match='access token'):
        tokens.decode_access_token(token, TEST_SECRET)


@pytest.mark.parametrize('user_id', ['', None, 123])
def test_invalid_user_id(user_id):
    with pytest.raises(ValueError, match='user_id'):
        tokens.create_access_token(user_id, TEST_SECRET)


def test_missing_secret(access_token):
    with pytest.raises(ValueError, match='secret'):
        tokens.create_access_token('user-123', '')

    with pytest.raises(ValueError, match='secret'):
        tokens.decode_access_token(access_token, '')
