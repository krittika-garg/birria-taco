"""
End-to-end fixtures: the real Flask app talking to a real MongoDB.

Unit tests elsewhere fake db_connect, so they can't catch a query or
update that Mongo itself would treat differently. These tests run every
request through the real stack. Each test gets its own throwaway
database, so they never touch seDB data and can run in any order.

They need a reachable MongoDB (CI runs one in Docker; locally use
`make mongo`) and skip otherwise.
"""
import os
from uuid import uuid4

import pymongo as pm
import pytest

import data.db_connect as dbc
from integration.tests.support import PASSWORD, TEST_JWT_SECRET
from server.endpoints import app


def _mongo_uri():
    if os.environ.get('CLOUD_MONGO', dbc.LOCAL) == dbc.CLOUD:
        return os.environ.get('MONGO_URI', '')
    return os.environ.get('MONGO_LOCAL_URI', dbc.LOCAL_URI_DEFAULT)


class _ThrowawayClient:
    """
    A MongoClient whose seDB is really a throwaway database. db_connect
    binds db=SE_DB as a default argument, so renaming at the client is
    the one place every read and write goes through.
    """
    def __init__(self, client, name):
        self._client = client
        self._name = name

    def __getitem__(self, db):
        return self._client[self._name if db == dbc.SE_DB else db]

    def __getattr__(self, attr):
        return getattr(self._client, attr)


def _unavailable(reason):
    # CI sets REQUIRE_MONGO so a broken database fails the build instead
    # of quietly skipping every end-to-end test.
    if os.environ.get('REQUIRE_MONGO') == '1':
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope='session')
def mongo():
    uri = _mongo_uri()
    if not uri:
        _unavailable('MongoDB is not configured')
    client = pm.MongoClient(uri, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command('ping')
    except pm.errors.PyMongoError:
        client.close()
        _unavailable('MongoDB is not reachable')
    yield client
    client.close()


@pytest.fixture
def db(mongo, monkeypatch):
    """A fresh database standing in for seDB, with the app's indexes."""
    name = f'e2e_{uuid4().hex}'
    monkeypatch.setattr(dbc, 'client', _ThrowawayClient(mongo, name))
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)
    dbc.initialize_indexes()
    try:
        yield mongo[name]
    finally:
        mongo.drop_database(name)


@pytest.fixture
def anon(db):
    """A client with no token."""
    return app.test_client()


@pytest.fixture
def login(db):
    """
    Return login(username): registers the user through /register, logs
    in through /login, and returns a client sending that access token.
    """
    def _login(username):
        client = app.test_client()
        creds = {'username': username, 'password': PASSWORD}
        assert client.post('/register', json=creds).status_code == 201
        response = client.post('/login', json=creds)
        assert response.status_code == 200
        tokens = response.get_json()
        client.environ_base['HTTP_AUTHORIZATION'] = \
            f"Bearer {tokens['access_token']}"
        client.refresh_token = tokens['refresh_token']
        return client
    return _login


@pytest.fixture
def neighborhoods(db):
    """Load the real states, cities and NYC neighborhoods into db."""
    import places.load as load

    load.save_places(load.build_places(
        load.read_csv(load.STATES_CSV), load.read_csv(load.CITIES_CSV),
        load.read_neighborhoods()))
    return db
