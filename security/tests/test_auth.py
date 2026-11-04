from unittest.mock import patch

import pymongo.errors as pme
from werkzeug.security import generate_password_hash

import security.auth as auth


@patch('security.auth.dbc.create_index')
@patch('security.auth.dbc.create')
def test_register(create, create_index):
    assert auth.register('bob', 'pw')
    create_index.assert_called_once_with(
        auth.USERS, auth.USERNAME, unique=True)
    collection, doc = create.call_args.args
    assert collection == auth.USERS
    assert doc[auth.USERNAME] == 'bob'
    assert doc[auth.PASSWORD_HASH] != 'pw'


@patch('security.auth.dbc.create_index')
@patch('security.auth.dbc.create', side_effect=pme.DuplicateKeyError(''))
def test_register_duplicate(create, create_index):
    assert not auth.register('bob', 'pw')


@patch('security.auth.dbc.read_one')
def test_login(read_one):
    read_one.return_value = {auth.PASSWORD_HASH: generate_password_hash('pw')}
    assert auth.login('bob', 'pw')
    read_one.assert_called_with(auth.USERS, {auth.USERNAME: 'bob'})
    assert not auth.login('bob', 'wrong')
    read_one.return_value = None
    assert not auth.login('nobody', 'pw')
