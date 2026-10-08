from unittest.mock import MagicMock, patch

import pymongo.errors as pme
from werkzeug.security import generate_password_hash

import security.auth as auth


@patch('security.auth._users')
def test_register(mock_users):
    assert auth.register('bob', 'pw')
    doc = mock_users.return_value.insert_one.call_args[0][0]
    assert doc[auth.USERNAME] == 'bob'
    assert doc[auth.PASSWORD_HASH] != 'pw'


@patch('security.auth._users')
def test_register_duplicate(mock_users):
    mock_users.return_value.insert_one.side_effect = pme.DuplicateKeyError('')
    assert not auth.register('bob', 'pw')


@patch('security.auth._users')
def test_login(mock_users):
    find = MagicMock(return_value={
        auth.PASSWORD_HASH: generate_password_hash('pw')})
    mock_users.return_value.find_one = find
    assert auth.login('bob', 'pw')
    assert not auth.login('bob', 'wrong')
    find.return_value = None
    assert not auth.login('nobody', 'pw')
