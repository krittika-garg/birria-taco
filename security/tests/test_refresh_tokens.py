import re

import pytest

from security.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
)


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
