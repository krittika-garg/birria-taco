"""
Guard every route: anything not on the public list must reject requests
without a valid Bearer token. A new endpoint that forgets login_required
fails here until it is protected or deliberately added to PUBLIC_ROUTES.
"""
import re
from unittest.mock import patch

import pytest
from bson import ObjectId

from server.endpoints import app

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'

# Routes anyone may call without logging in.
PUBLIC_ROUTES = {
    '/',
    '/endpoints',
    '/health',
    '/hello',
    '/login',
    '/logout',
    '/refresh',
    '/register',
    '/neighborhoods',
    '/neighborhoods/<string:code>/leaderboard',
    '/neighborhoods/at',
    '/states',
    '/states/<string:abbrev>',
    '/states/nearest',
    '/static/<path:filename>',
    '/swagger.json',
    '/swaggerui/<path:filename>',
}


def _protected_calls():
    """Yield (method, url) for every method of every non-public route."""
    for rule in app.url_map.iter_rules():
        if rule.rule in PUBLIC_ROUTES:
            continue
        # Any well-formed id works: the token check runs before lookup.
        url = re.sub(r'<[^>]+>', str(ObjectId()), rule.rule)
        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            yield pytest.param(method, url, id=f'{method} {rule.rule}')


PROTECTED_CALLS = list(_protected_calls())


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def no_database():
    """Fail loudly if an unauthenticated request reaches the database."""
    with patch('data.db_connect.connect_db',
               side_effect=AssertionError('database touched')):
        yield


def test_public_routes_all_exist():
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert PUBLIC_ROUTES <= rules, PUBLIC_ROUTES - rules


def test_there_are_protected_routes():
    # Guards against a regex or url_map change silently emptying the list.
    assert len(PROTECTED_CALLS) >= 15


@pytest.mark.parametrize('method, url', PROTECTED_CALLS)
@pytest.mark.parametrize('header', [
    None,
    'Bearer',
    'Bearer not-a-jwt',
    'Basic Ym9iOnB3',
    'Bearer a.b.c',
])
def test_protected_route_rejects_missing_or_bad_token(method, url, header):
    client = app.test_client()
    if header is not None:
        client.environ_base['HTTP_AUTHORIZATION'] = header
    response = client.open(url, method=method, json={})
    assert response.status_code == 401


@pytest.mark.parametrize('method, url', PROTECTED_CALLS)
def test_protected_route_rejects_token_signed_with_other_key(method, url):
    from security.tokens import create_access_token

    token = create_access_token('bob', 'some-other-secret-key-32-chars-long!')
    client = app.test_client()
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    assert client.open(url, method=method, json={}).status_code == 401
