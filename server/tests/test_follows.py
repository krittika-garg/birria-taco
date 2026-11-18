from datetime import datetime, timezone

import pytest

import data.db_connect as dbc
import server.follows as fl
from security.auth import USERNAME, USERS
from security.tokens import create_access_token
from server.endpoints import app

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'
FOLLOW_URL = '/users/{}/follow'
FOLLOWERS_URL = '/users/{}/followers'
FOLLOWING_URL = '/users/{}/following'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


def client_for(user):
    client = app.test_client()
    token = create_access_token(user, TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def follows(monkeypatch):
    """In-memory follows collection, with alice, bob and cara registered."""
    docs = []
    users = {'alice', 'bob', 'cara'}

    def matches(doc, filt):
        return all(doc.get(k) == v for k, v in filt.items())

    def read_one(collection, filt):
        assert collection == USERS
        name = filt[USERNAME]
        return {USERNAME: name} if name in users else None

    def update_raw(collection, filt, update_doc, upsert=False):
        assert collection == fl.FOLLOWS_COLLECT and upsert
        if not any(matches(doc, filt) for doc in docs):
            docs.append({**filt, **update_doc['$setOnInsert']})

    def delete(collection, filt):
        assert collection == fl.FOLLOWS_COLLECT
        for doc in docs:
            if matches(doc, filt):
                docs.remove(doc)
                return 1
        return 0

    def read(collection, filt=None, projection=None):
        assert collection == fl.FOLLOWS_COLLECT
        return [{k: doc[k] for k in projection}
                for doc in docs if matches(doc, filt)]

    monkeypatch.setattr(dbc, 'read', read)
    monkeypatch.setattr(dbc, 'read_one', read_one)
    monkeypatch.setattr(dbc, 'update_raw', update_raw)
    monkeypatch.setattr(dbc, 'delete', delete)
    return docs


def pairs(docs):
    return [(doc[fl.FOLLOWER], doc[fl.FOLLOWEE]) for doc in docs]


@pytest.mark.parametrize('method', ['post', 'delete'])
def test_follow_requires_login(method):
    client = app.test_client()
    response = getattr(client, method)(FOLLOW_URL.format('bob'))
    assert response.status_code == 401


def test_follow(follows):
    response = client_for('alice').post(FOLLOW_URL.format('bob'))
    assert response.status_code == 200
    assert pairs(follows) == [('alice', 'bob')]
    assert follows[0][fl.CREATED_AT].tzinfo == timezone.utc


def test_follow_twice_keeps_one_follow_and_its_timestamp(follows):
    alice = client_for('alice')
    alice.post(FOLLOW_URL.format('bob'))
    first_followed = follows[0][fl.CREATED_AT]
    assert isinstance(first_followed, datetime)

    response = alice.post(FOLLOW_URL.format('bob'))

    assert response.status_code == 200
    assert pairs(follows) == [('alice', 'bob')]
    assert follows[0][fl.CREATED_AT] == first_followed


def test_follow_is_one_way(follows):
    client_for('alice').post(FOLLOW_URL.format('bob'))
    client_for('bob').delete(FOLLOW_URL.format('alice'))
    assert pairs(follows) == [('alice', 'bob')]


def test_cannot_follow_yourself(follows):
    response = client_for('alice').post(FOLLOW_URL.format('alice'))
    assert response.status_code == 400
    assert follows == []


def test_cannot_follow_unknown_user(follows):
    response = client_for('alice').post(FOLLOW_URL.format('nobody'))
    assert response.status_code == 404
    assert follows == []


def test_unfollow(follows):
    alice = client_for('alice')
    alice.post(FOLLOW_URL.format('bob'))
    alice.post(FOLLOW_URL.format('cara'))

    response = alice.delete(FOLLOW_URL.format('bob'))

    assert response.status_code == 200
    assert pairs(follows) == [('alice', 'cara')]


def test_unfollow_when_not_following_is_fine(follows):
    response = client_for('alice').delete(FOLLOW_URL.format('bob'))
    assert response.status_code == 200
    assert follows == []


@pytest.mark.parametrize('url', [FOLLOWERS_URL, FOLLOWING_URL])
def test_lists_require_login(url):
    assert app.test_client().get(url.format('bob')).status_code == 401


@pytest.mark.parametrize('url', [FOLLOWERS_URL, FOLLOWING_URL])
def test_lists_404_for_unknown_user(follows, url):
    response = client_for('alice').get(url.format('nobody'))
    assert response.status_code == 404


def test_lists_are_empty_without_follows(follows):
    alice = client_for('alice')
    assert alice.get(FOLLOWERS_URL.format('bob')).get_json() == {
        'followers': []}
    assert alice.get(FOLLOWING_URL.format('bob')).get_json() == {
        'following': []}


def test_followers_are_sorted(follows):
    client_for('cara').post(FOLLOW_URL.format('bob'))
    client_for('alice').post(FOLLOW_URL.format('bob'))

    response = client_for('bob').get(FOLLOWERS_URL.format('bob'))

    assert response.status_code == 200
    assert response.get_json() == {'followers': ['alice', 'cara']}


def test_following_is_sorted(follows):
    alice = client_for('alice')
    alice.post(FOLLOW_URL.format('cara'))
    alice.post(FOLLOW_URL.format('bob'))

    response = client_for('bob').get(FOLLOWING_URL.format('alice'))

    assert response.status_code == 200
    assert response.get_json() == {'following': ['bob', 'cara']}


def test_unfollow_updates_both_lists(follows):
    alice = client_for('alice')
    alice.post(FOLLOW_URL.format('bob'))
    alice.delete(FOLLOW_URL.format('bob'))

    assert alice.get(FOLLOWERS_URL.format('bob')).get_json() == {
        'followers': []}
    assert alice.get(FOLLOWING_URL.format('alice')).get_json() == {
        'following': []}
