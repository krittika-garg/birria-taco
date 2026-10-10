from http.client import (
    BAD_REQUEST,
    FORBIDDEN,
    NOT_ACCEPTABLE,
    NOT_FOUND,
    OK,
    SERVICE_UNAVAILABLE,
)

from unittest.mock import patch

import pytest

import server.endpoints as ep

TEST_CLIENT = ep.app.test_client()


def test_hello():
    resp = TEST_CLIENT.get(ep.HELLO_EP)
    resp_json = resp.get_json()
    assert ep.HELLO_RESP in resp_json


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[{'Abbrev': 'NY'}], autospec=True)
def test_states(mock_read, mock_connect):
    resp = TEST_CLIENT.get(ep.STATES_EP)
    assert resp.status_code == OK
    assert resp.get_json() == {ep.STATES_RESP: [{'Abbrev': 'NY'}]}
    mock_read.assert_called_once_with(ep.STATES_COLLECT)


@patch('security.auth.register', return_value=True, autospec=True)
def test_register(mock_reg):
    resp = TEST_CLIENT.post(
        ep.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 201


def test_register_missing_fields():
    resp = TEST_CLIENT.post(ep.REGISTER_EP, json={'username': 'bob'})
    assert resp.status_code == BAD_REQUEST


@patch('security.auth.register', return_value=False, autospec=True)
def test_register_taken(mock_reg):
    resp = TEST_CLIENT.post(
        ep.REGISTER_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 409


@patch('security.auth.login', return_value=True, autospec=True)
def test_login_logout(mock_login):
    client = ep.app.test_client()
    resp = client.post(ep.LOGIN_EP, json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == OK
    with client.session_transaction() as sess:
        assert sess['user'] == 'bob'
    client.post(ep.LOGOUT_EP)
    with client.session_transaction() as sess:
        assert 'user' not in sess


@patch('security.auth.login', return_value=False, autospec=True)
def test_login_bad(mock_login):
    resp = TEST_CLIENT.post(
        ep.LOGIN_EP, json={'username': 'bob', 'password': 'x'})
    assert resp.status_code == 401
