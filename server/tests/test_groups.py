from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

import data.db_connect as dbc
import server.groups as gr
from server.endpoints import app

from security.tokens import create_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


def client_for(user):
    client = app.test_client()
    token = create_access_token(user, TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def db(monkeypatch):
    """
    In-memory groups collection. Filters match like Mongo's: a scalar
    against an array field means "array contains it".
    """
    docs = []

    def matches(doc, filt):
        return all(v in doc.get(k, []) if isinstance(doc.get(k), list)
                   else doc.get(k) == v for k, v in filt.items())

    def read_one(collection, filt):
        found = [d for d in docs if matches(d, filt)]
        return {**found[0], '_id': str(found[0]['_id']),
                'members': list(found[0]['members'])} if found else None

    def create(collection, doc):
        doc = {**doc, '_id': ObjectId()}
        docs.append(doc)
        return MagicMock(inserted_id=doc['_id'])

    def update_raw(collection, filt, update_doc):
        for doc in docs:
            if matches(doc, filt):
                member = update_doc['$addToSet']['members']
                if member not in doc['members']:
                    doc['members'].append(member)

    monkeypatch.setattr(dbc, 'read_one', read_one)
    monkeypatch.setattr(dbc, 'create', create)
    monkeypatch.setattr(dbc, 'update_raw', update_raw)
    return docs


def start_group(db):
    response = client_for('bob').post(gr.GROUPS_EP)
    assert response.status_code == 201
    return response.get_json()['group']


@pytest.mark.parametrize('method, url', [
    ('post', gr.GROUPS_EP),
    ('get', f'{gr.GROUPS_EP}/{ObjectId()}'),
    ('post', f'{gr.GROUPS_EP}/join/abc'),
])
def test_login_required(method, url):
    assert getattr(app.test_client(), method)(url).status_code == 401


def test_create(db):
    group = start_group(db)
    assert group['host'] == 'bob'
    assert group['members'] == ['bob']
    assert len(group['invite_token']) >= 16
    expires = datetime.fromisoformat(group['expires_at'])
    left = expires - datetime.now(timezone.utc)
    assert timedelta(hours=1, minutes=59) < left <= timedelta(hours=2)


def test_invite_tokens_differ(db):
    assert start_group(db)['invite_token'] != start_group(db)['invite_token']


def test_join_then_get(db):
    group = start_group(db)
    alice = client_for('alice')
    join_url = f"{gr.GROUPS_EP}/join/{group['invite_token']}"

    response = alice.post(join_url)
    assert response.status_code == 200
    assert response.get_json()['group']['members'] == ['bob', 'alice']

    # Joining twice doesn't add a second copy.
    response = alice.post(join_url)
    assert response.get_json()['group']['members'] == ['bob', 'alice']
    assert db[0]['members'] == ['bob', 'alice']

    response = alice.get(f"{gr.GROUPS_EP}/{group['_id']}")
    assert response.status_code == 200
    assert response.get_json()['group']['members'] == ['bob', 'alice']


def test_join_bad_token(db):
    start_group(db)
    response = client_for('alice').post(f'{gr.GROUPS_EP}/join/nope')
    assert response.status_code == 404


def test_expired_group(db):
    group = start_group(db)
    # Mongo returns naive UTC datetimes.
    db[0]['expires_at'] = (datetime.now(timezone.utc).replace(tzinfo=None)
                           - timedelta(minutes=1))
    alice = client_for('alice')
    assert alice.post(
        f"{gr.GROUPS_EP}/join/{group['invite_token']}").status_code == 404
    assert db[0]['members'] == ['bob']
    assert client_for('bob').get(
        f"{gr.GROUPS_EP}/{group['_id']}").status_code == 404


@pytest.mark.parametrize('group_id', ['not-an-id', str(ObjectId())])
def test_get_unknown_group(db, group_id):
    response = client_for('bob').get(f'{gr.GROUPS_EP}/{group_id}')
    assert response.status_code == 404


def test_non_member_cannot_get(db):
    group = start_group(db)
    response = client_for('alice').get(f"{gr.GROUPS_EP}/{group['_id']}")
    assert response.status_code == 404


def test_leave_group(db, monkeypatch):
    group = start_group(db)
    alice = client_for('alice')
    alice.post(f"/groups/join/{group['invite_token']}")

    def pull_member(collection, filt, update):
        assert collection == gr.GROUPS_COLLECT
        assert filt == {'_id': ObjectId(group['_id'])}
        assert update == {'$pull': {'members': 'alice'}}
        db[0]['members'].remove('alice')

    monkeypatch.setattr(dbc, 'update_raw', pull_member)
    url = f"/groups/{group['_id']}"
    assert alice.post(url + '/leave').status_code == 200
    assert db[0]['members'] == ['bob']
    assert alice.get(url).status_code == 404


@pytest.mark.parametrize('user, expected', [('bob', 409), ('alice', 404)])
def test_leave_rejected(db, user, expected):
    group = start_group(db)
    response = client_for(user).post(f"/groups/{group['_id']}/leave")
    assert response.status_code == expected
    assert db[0]['members'] == ['bob']


def test_leave_requires_login():
    response = app.test_client().post(f'/groups/{ObjectId()}/leave')
    assert response.status_code == 401
