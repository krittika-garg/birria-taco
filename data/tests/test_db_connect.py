from uuid import uuid4

import pytest
import pymongo as pm

import data.db_connect as dbc


@pytest.fixture
def test_collection(monkeypatch):
    client = pm.MongoClient(
        "mongodb://localhost:27017/",
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
