from http.client import BAD_REQUEST, OK, SERVICE_UNAVAILABLE

from unittest.mock import patch

import pytest

from server.endpoints import app
import server.accounts as acc


from security.tokens import decode_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


TEST_CLIENT = app.test_client()


@patch('security.auth.register', return_value=True, autospec=True)
def test_register(mock_reg):
    resp = TEST_CLIENT.post(
        acc.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 201


def test_register_missing_fields():
    resp = TEST_CLIENT.post(acc.REGISTER_EP, json={'username': 'bob'})
    assert resp.status_code == BAD_REQUEST


@patch('security.auth.register', return_value=False, autospec=True)
def test_register_taken(mock_reg):
    resp = TEST_CLIENT.post(
        acc.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 409


@patch('security.auth.login', return_value=True, autospec=True)
def test_login_logout(mock_login):
    client = app.test_client()
    resp = client.post(acc.LOGIN_EP, json={
        'username': 'bob', 'password': 'pw'})
    assert resp.status_code == OK
    body = resp.get_json()
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 900
    claims = decode_access_token(body['access_token'], TEST_JWT_SECRET)
    assert claims['sub'] == 'bob'
    with client.session_transaction() as sess:
        assert 'user' not in sess
    assert client.post(acc.LOGOUT_EP).status_code == OK


@patch('security.auth.login', return_value=False, autospec=True)
def test_login_bad(mock_login):
    resp = TEST_CLIENT.post(
        acc.LOGIN_EP, json={'username': 'bob', 'password': 'x'})
    assert resp.status_code == 401


@patch('security.auth.login', return_value=True, autospec=True)
def test_login_without_jwt_secret(mock_login, monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', None)
    response = app.test_client().post(
        acc.LOGIN_EP, json={'username': 'bob', 'password': 'pw'})
    assert response.status_code == SERVICE_UNAVAILABLE
    assert 'access_token' not in response.get_json()


@pytest.mark.parametrize('payload', [[1], 42, 'hello', True, None])
@pytest.mark.parametrize('endpoint', [acc.LOGIN_EP, acc.REGISTER_EP])
@patch('security.auth.login', autospec=True)
@patch('security.auth.register', autospec=True)
def test_credentials_reject_non_objects(register, login, endpoint, payload):
    response = app.test_client().post(endpoint, json=payload)
    expected = 401 if endpoint == acc.LOGIN_EP else 400
    assert response.status_code == expected
    register.assert_not_called()
    login.assert_not_called()
