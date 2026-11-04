"""
Minimal username/password auth backed by the `users` collection.
"""
import pymongo.errors as pme
from werkzeug.security import check_password_hash, generate_password_hash

import data.db_connect as dbc

USERS = 'users'
USERNAME = 'username'
PASSWORD_HASH = 'password_hash'


def _ensure_index():
    dbc.create_index(USERS, USERNAME, unique=True)  # no-op once it exists


def register(username: str, password: str) -> bool:
    """
    Returns False if the username is already taken.
    """
    _ensure_index()
    try:
        dbc.create(USERS, {USERNAME: username,
                           PASSWORD_HASH: generate_password_hash(password)})
    except pme.DuplicateKeyError:
        return False
    return True


def login(username: str, password: str) -> bool:
    """
    Same result for unknown user and wrong password, on purpose.
    """
    user = dbc.read_one(USERS, {USERNAME: username})
    return bool(user) and check_password_hash(user[PASSWORD_HASH], password)
