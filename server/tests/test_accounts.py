from http.client import BAD_REQUEST, OK, SERVICE_UNAVAILABLE, UNAUTHORIZED

from unittest.mock import patch

import pytest

from server.endpoints import app
import server.accounts as acc


from security.tokens import create_access_token, decode_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


TEST_CLIENT = app.test_client()


@patch('security.refresh_tokens.issue_refresh_token', return_value='new-rt',
       autospec=True)
@patch('security.auth.register', return_value=True, autospec=True)
def test_register(mock_reg, mock_issue):
    resp = TEST_CLIENT.post(
        acc.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['refresh_token'] == 'new-rt'
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 900
    claims = decode_access_token(body['access_token'], TEST_JWT_SECRET)
    assert claims['sub'] == 'bob'
    mock_issue.assert_called_once_with('bob')


def test_register_missing_fields():
    resp = TEST_CLIENT.post(acc.REGISTER_EP, json={'username': 'bob'})
    assert resp.status_code == BAD_REQUEST


@patch('security.refresh_tokens.issue_refresh_token', autospec=True)
@patch('security.auth.register', return_value=False, autospec=True)
def test_register_taken(mock_reg, mock_issue):
    resp = TEST_CLIENT.post(
        acc.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 409
    assert 'access_token' not in resp.get_json()
    mock_issue.assert_not_called()


@patch('security.auth.register', autospec=True)
def test_register_without_secret_creates_nothing(mock_reg, monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', None)
    resp = TEST_CLIENT.post(
        acc.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == SERVICE_UNAVAILABLE
    mock_reg.assert_not_called()


@patch('security.refresh_tokens.issue_refresh_token', return_value='new-rt',
       autospec=True)
@patch('security.auth.login', return_value=True, autospec=True)
def test_login_logout(mock_login, mock_issue):
    client = app.test_client()
    resp = client.post(acc.LOGIN_EP, json={
        'username': 'bob', 'password': 'pw'})
    assert resp.status_code == OK
    body = resp.get_json()
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 900
    claims = decode_access_token(body['access_token'], TEST_JWT_SECRET)
    assert claims['sub'] == 'bob'
    assert body['refresh_token'] == 'new-rt'
    mock_issue.assert_called_once_with('bob')
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


@patch('security.refresh_tokens.issue_refresh_token', return_value='new-rt',
       autospec=True)
@patch('security.refresh_tokens.redeem_refresh_token', return_value='bob',
       autospec=True)
def test_refresh(mock_redeem, mock_issue):
    resp = TEST_CLIENT.post(acc.REFRESH_EP, json={'refresh_token': 'old-rt'})
    assert resp.status_code == OK
    body = resp.get_json()
    mock_redeem.assert_called_once_with('old-rt')
    mock_issue.assert_called_once_with('bob')
    assert body['refresh_token'] == 'new-rt'
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 900
    claims = decode_access_token(body['access_token'], TEST_JWT_SECRET)
    assert claims['sub'] == 'bob'


@patch('security.refresh_tokens.issue_refresh_token', autospec=True)
@patch('security.refresh_tokens.redeem_refresh_token', return_value=None,
       autospec=True)
def test_refresh_rejects_invalid_token(mock_redeem, mock_issue):
    resp = TEST_CLIENT.post(acc.REFRESH_EP, json={'refresh_token': 'bad'})
    assert resp.status_code == UNAUTHORIZED
    assert 'access_token' not in resp.get_json()
    mock_issue.assert_not_called()


@pytest.mark.parametrize('payload', [
    None, [1], 'x', {}, {'refresh_token': ''}, {'refresh_token': 42},
    {'refresh_token': {'$ne': None}},
])
@patch('security.refresh_tokens.redeem_refresh_token', autospec=True)
def test_refresh_rejects_malformed_body(mock_redeem, payload):
    resp = TEST_CLIENT.post(acc.REFRESH_EP, json=payload)
    assert resp.status_code == UNAUTHORIZED
    mock_redeem.assert_not_called()


@patch('security.refresh_tokens.redeem_refresh_token', autospec=True)
def test_refresh_without_secret_keeps_token(mock_redeem, monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', None)
    resp = TEST_CLIENT.post(acc.REFRESH_EP, json={'refresh_token': 'rt'})
    assert resp.status_code == SERVICE_UNAVAILABLE
    mock_redeem.assert_not_called()


@patch('security.refresh_tokens.revoke_refresh_token', autospec=True)
def test_logout_revokes_refresh_token(mock_revoke):
    resp = TEST_CLIENT.post(acc.LOGOUT_EP, json={'refresh_token': 'rt'})
    assert resp.status_code == OK
    mock_revoke.assert_called_once_with('rt')


@patch('security.refresh_tokens.revoke_refresh_token', autospec=True)
def test_logout_without_token_still_succeeds(mock_revoke):
    assert TEST_CLIENT.post(acc.LOGOUT_EP).status_code == OK
    mock_revoke.assert_not_called()


@patch('security.refresh_tokens.revoke_all_refresh_tokens', return_value=2,
       autospec=True)
def test_logout_all_revokes_the_callers_tokens(mock_revoke_all):
    token = create_access_token('bob', TEST_JWT_SECRET)
    resp = TEST_CLIENT.post(acc.LOGOUT_ALL_EP,
                            headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == OK
    assert resp.get_json()['sessions_ended'] == 2
    mock_revoke_all.assert_called_once_with('bob')


@patch('security.refresh_tokens.revoke_all_refresh_tokens', autospec=True)
def test_logout_all_needs_access_token(mock_revoke_all):
    # The user to log out comes only from the token, never the body.
    resp = TEST_CLIENT.post(acc.LOGOUT_ALL_EP, json={'username': 'bob'})
    assert resp.status_code == UNAUTHORIZED
    mock_revoke_all.assert_not_called()


@pytest.mark.parametrize('endpoint', [
    acc.REGISTER_EP, acc.LOGIN_EP, acc.REFRESH_EP, acc.LOGOUT_EP,
])
def test_swagger_documents_request_body(endpoint):
    spec = TEST_CLIENT.get('/swagger.json').get_json()
    params = spec['paths'][endpoint]['post']['parameters']
    assert [param['in'] for param in params] == ['body']
    assert 'Bearer' in spec['securityDefinitions']
