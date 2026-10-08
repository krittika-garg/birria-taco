import os
from uuid import uuid4

import pytest
import pymongo as pm

import data.db_connect as dbc


def _test_uri():
    # Use the cloud cluster when CLOUD_MONGO=1 (e.g. local dev in WSL),
    # otherwise the local Mongo that CI runs in Docker.
    if os.environ.get("CLOUD_MONGO", dbc.LOCAL) == dbc.CLOUD:
        return os.environ["MONGO_URI"]
    return "mongodb://localhost:27017/"


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
