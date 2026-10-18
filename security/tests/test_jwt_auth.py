"""Tests for JWT-protected Flask routes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask, g
import pytest

from security.jwt_auth import login_required
from security.tokens import create_access_token

TEST_SECRET = 'test-only-secret-with-at-least-32-bytes'


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY=TEST_SECRET)

    @app.get('/protected')
    @login_required
    def protected():
        return {'user': g.current_user}

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_valid_token(client):
    token = create_access_token('bob', TEST_SECRET)
    response = client.get(
        '/protected', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.get_json() == {'user': 'bob'}


@pytest.mark.parametrize('header', [
    '',
    'Bearer',
    'Basic abc',
    'Bearer abc extra',
    'Bearer not-a-jwt',
])
def test_invalid_authorization(client, header):
    response = client.get(
        '/protected', headers={'Authorization': header})

    assert response.status_code == 401


def test_wrong_signing_key(client):
    token = create_access_token(
        'bob', 'different-test-secret-with-at-least-32-bytes')
    response = client.get(
        '/protected', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 401


def test_expired_token(client):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch('security.tokens.datetime') as mock_datetime:
        mock_datetime.now.return_value = past
        token = create_access_token('bob', TEST_SECRET)

    response = client.get(
        '/protected', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 401


def test_missing_secret(app, client):
    token = create_access_token('bob', TEST_SECRET)
    app.config.pop('JWT_SECRET_KEY')

    response = client.get(
        '/protected', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 503


def test_session_cookie_does_not_authorize(app, client):
    app.config['SECRET_KEY'] = 'test-session-secret'
    with client.session_transaction() as session:
        session['user'] = 'bob'

    assert client.get('/protected').status_code == 401
