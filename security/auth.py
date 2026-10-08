"""
Minimal username/password auth backed by the `users` collection.
"""
import pymongo.errors as pme
from werkzeug.security import check_password_hash, generate_password_hash

import data.db_connect as dbc

USERS = 'users'
USERNAME = 'username'
PASSWORD_HASH = 'password_hash'


def _users():
    users = dbc.connect_db()[dbc.SE_DB][USERS]
    users.create_index(USERNAME, unique=True)  # no-op once it exists
    return users


def register(username: str, password: str) -> bool:
    """
    Returns False if the username is already taken.
    """
    try:
        _users().insert_one({USERNAME: username,
                             PASSWORD_HASH: generate_password_hash(password)})
    except pme.DuplicateKeyError:
        return False
    return True


def login(username: str, password: str) -> bool:
    """
    Same result for unknown user and wrong password, on purpose.
    """
    user = _users().find_one({USERNAME: username})
    return bool(user) and check_password_hash(user[PASSWORD_HASH], password)
