import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pymongo as pm
from bson import ObjectId

import data.db_connect as dbc

CLOUD_URI = 'mongodb+srv://user:secret@example.mongodb.net/'


def _test_uri():
    # Use the cloud cluster when CLOUD_MONGO=1 (e.g. local dev in WSL),
    # otherwise the local Mongo that CI runs in Docker.
    if os.environ.get("CLOUD_MONGO", dbc.LOCAL) == dbc.CLOUD:
        return os.environ.get("MONGO_URI", "")
    return "mongodb://localhost:27017/"


def _mongo_reachable():
    uri = _test_uri()
    if not uri:
        return False
    client = pm.MongoClient(uri, serverSelectionTimeoutMS=500)
    try:
        client.admin.command("ping")
        return True
    except pm.errors.PyMongoError:
        return False
    finally:
        client.close()


# The integration tests below need a real database. CI runs one in Docker;
# on a laptop without one they skip instead of erroring after a timeout.
requires_mongo = pytest.mark.skipif(not _mongo_reachable(),
                                    reason="MongoDB is not reachable")


@pytest.fixture
def fresh_connection(monkeypatch):
    """
    Start each test disconnected and with no Mongo settings, so
    connect_db() decides from scratch; monkeypatch restores both after.
    """
    monkeypatch.setattr(dbc, "client", None)
    monkeypatch.delenv("CLOUD_MONGO", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)


@pytest.fixture
def fake_collection(monkeypatch):
    """
    Swap the real client for a MagicMock and hand back the collection
    object that client[db][collection] returns, for the CRUD helpers.
    """
    client = MagicMock()
    monkeypatch.setattr(dbc, "client", client)
    return client.__getitem__.return_value.__getitem__.return_value


@patch("data.db_connect.pm.MongoClient")
def test_connect_db_local(mock_client, fresh_connection):
    client = dbc.connect_db()
    mock_client.assert_called_once_with()
    assert client is mock_client.return_value
    assert dbc.client is client


@patch("data.db_connect.pm.MongoClient")
def test_connect_db_reuses_client(mock_client, fresh_connection):
    first = dbc.connect_db()
    second = dbc.connect_db()
    assert first is second
    mock_client.assert_called_once()


@patch("data.db_connect.pm.MongoClient")
def test_connect_db_cloud_uses_uri(mock_client, fresh_connection,
                                   monkeypatch):
    monkeypatch.setenv("CLOUD_MONGO", dbc.CLOUD)
    monkeypatch.setenv("MONGO_URI", CLOUD_URI)
    dbc.connect_db()
    mock_client.assert_called_once_with(CLOUD_URI)


def test_connect_db_cloud_without_uri_raises(fresh_connection, monkeypatch):
    monkeypatch.setenv("CLOUD_MONGO", dbc.CLOUD)
    with patch("data.db_connect.pm.MongoClient") as mock_client:
        with pytest.raises(ValueError, match="Mongo in the cloud"):
            dbc.connect_db()
    mock_client.assert_not_called()
    assert dbc.client is None


def test_read_drops_ids_by_default(fake_collection):
    fake_collection.find.return_value = [
        {dbc.MONGO_ID: ObjectId(), "name": "Los Tacos No. 1"}]
    assert dbc.read("restaurants") == [{"name": "Los Tacos No. 1"}]
    fake_collection.find.assert_called_once_with({})


def test_read_keeps_ids_as_strings(fake_collection):
    oid = ObjectId()
    fake_collection.find.return_value = [{dbc.MONGO_ID: oid, "name": "x"}]
    docs = dbc.read("restaurants", no_id=False, filt={"name": "x"})
    assert docs == [{dbc.MONGO_ID: str(oid), "name": "x"}]
    fake_collection.find.assert_called_once_with({"name": "x"})


def test_read_one_returns_none_when_missing(fake_collection):
    fake_collection.find.return_value = []
    assert dbc.read_one("restaurants", {"name": "nowhere"}) is None


def test_read_dict_keys_by_field(fake_collection):
    fake_collection.find.return_value = [
        {dbc.MONGO_ID: ObjectId(), "Abbrev": "NY"},
        {dbc.MONGO_ID: ObjectId(), "Abbrev": "CA"}]
    assert dbc.read_dict("states", "Abbrev") == {
        "NY": {"Abbrev": "NY"}, "CA": {"Abbrev": "CA"}}


def test_upsert_sets_fields_and_inserts_if_missing(fake_collection):
    dbc.upsert("states", {"Abbrev": "NY"}, {"State": "New York"})
    fake_collection.update_one.assert_called_once_with(
        {"Abbrev": "NY"}, {"$set": {"State": "New York"}}, upsert=True)


def test_update_raw_passes_operators_through(fake_collection):
    update_doc = {"$push": {"ordered": "x"}, "$inc": {"version": 1}}
    dbc.update_raw("rankings", {"_id": "bob"}, update_doc, upsert=True)
    fake_collection.update_one.assert_called_once_with(
        {"_id": "bob"}, update_doc, upsert=True)


def test_delete_returns_count(fake_collection):
    fake_collection.delete_one.return_value.deleted_count = 1
    assert dbc.delete("restaurants", {"name": "x"}) == 1
    fake_collection.delete_one.assert_called_once_with({"name": "x"})


@pytest.fixture
def test_collection(monkeypatch):
    client = pm.MongoClient(
        _test_uri(),
        serverSelectionTimeoutMS=5000,
    )
    monkeypatch.setattr(dbc, "client", client)

    database = "birria_taco_test"
    collection = f"test_{uuid4().hex}"

    try:
        client.admin.command("ping")
        try:
            yield database, collection
        finally:
            client[database].drop_collection(collection)
    finally:
        client.close()


@requires_mongo
def test_create_and_read_one(test_collection):
    database, collection = test_collection
    document = {"name": "test_player", "score": 10}

    result = dbc.create(collection, document, db=database)
    saved = dbc.read_one(
        collection,
        {"_id": result.inserted_id},
        db=database,
    )

    assert saved is not None
    assert saved["name"] == "test_player"
    assert saved["score"] == 10
    assert saved["_id"] == str(result.inserted_id)


@requires_mongo
def test_read_filters_by_owner(test_collection):
    database, collection = test_collection
    for username in ('bob', 'alice'):
        dbc.create(collection, {'user': username, 'name': username},
                   db=database)

    saved = dbc.read(collection, db=database, no_id=False,
                     filt={'user': 'bob'})
    assert len(saved) == 1
    assert saved[0]['user'] == 'bob'
    assert isinstance(saved[0]['_id'], str)
    assert len(dbc.read(collection, db=database)) == 2
    assert dbc.read(collection, db=database, filt={'user': 'nobody'}) == []
