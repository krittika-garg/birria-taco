from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

import data.db_connect as dbc
import server.rankings as rk
from server.endpoints import app
from server.restaurants import RESTAURANTS_COLLECT

from security.tokens import create_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


@pytest.fixture
def client():
    client = app.test_client()
    token = create_access_token('bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def db(monkeypatch):
    """
    Swap db_connect for an in-memory store of {collection: [docs]} that
    matches filters on plain equality. update_raw is a MagicMock so tests
    can check the $push sent to rankings.
    """
    store = {}

    def find(collection, filt):
        return [doc for doc in store.get(collection, [])
                if all(doc.get(k) == v for k, v in filt.items())]

    def read_one(collection, filt):
        docs = find(collection, filt)
        return {**docs[0], '_id': str(docs[0]['_id'])} if docs else None

    def create(collection, doc):
        doc.setdefault('_id', ObjectId())
        store.setdefault(collection, []).append(dict(doc))
        return MagicMock(inserted_id=doc['_id'])

    def update(collection, filt, fields):
        docs = find(collection, filt)
        for doc in docs:
            doc.update(fields)
        return MagicMock(matched_count=len(docs))

    def delete(collection, filt):
        docs = find(collection, filt)
        for doc in docs:
            store[collection].remove(doc)
        return len(docs)

    monkeypatch.setattr(dbc, 'connect_db', lambda: None)
    monkeypatch.setattr(dbc, 'read_one', read_one)
    monkeypatch.setattr(dbc, 'create', create)
    monkeypatch.setattr(dbc, 'update', update)
    monkeypatch.setattr(dbc, 'delete', delete)
    monkeypatch.setattr(dbc, 'update_raw', MagicMock())
    return store


def add_restaurant(db, name, user='bob'):
    """Save a restaurant for user and return its string id."""
    obj_id = ObjectId()
    db.setdefault(RESTAURANTS_COLLECT, []).append(
        {'_id': obj_id, 'name': name, 'user': user})
    return str(obj_id)


def set_ranking(db, entries, user='bob'):
    """entries is a list of (restaurant_id, bucket), best first."""
    db[rk.RANKINGS_COLLECT] = [{'_id': user, 'version': 1, 'ordered': [
        {'restaurant_id': resid, 'bucket': bucket}
        for resid, bucket in entries]}]


def pushed(db):
    """Return (entry, position) from the single $push into rankings."""
    dbc.update_raw.assert_called_once()
    collection, filt, update_doc = dbc.update_raw.call_args.args
    assert (collection, filt) == (rk.RANKINGS_COLLECT, {'_id': 'bob'})
    push = update_doc['$push']['ordered']
    return push['$each'][0], push['$position']


@pytest.mark.parametrize('n', range(9))
def test_narrow_finds_every_slot_in_log_steps(n):
    # Answer as if the new place belongs at target; it must land there.
    for target in range(n + 1):
        lo, hi, asked = 0, n, 0
        while lo < hi:
            mid = (lo + hi) // 2
            answer = rk.BETTER if target <= mid else rk.WORSE
            lo, hi = rk.narrow(lo, hi, answer)
            asked += 1
        assert lo == target
        assert asked <= n.bit_length()


def test_narrow_same_inserts_above_mid():
    assert rk.narrow(0, 4, rk.SAME) == (2, 2)


def test_bucket_bounds():
    ordered = [{'bucket': b} for b in ('liked', 'liked', 'fine', 'disliked')]
    assert rk.bucket_bounds(ordered, 'liked') == (0, 2)
    assert rk.bucket_bounds(ordered, 'fine') == (2, 3)
    assert rk.bucket_bounds(ordered, 'disliked') == (3, 4)
    assert rk.bucket_bounds(ordered[:2], 'fine') == (2, 2)


@pytest.mark.parametrize('url', [
    rk.RANK_SESSIONS_EP, rk.RANK_SESSIONS_EP + f'/{ObjectId()}/answer'])
def test_login_required(url):
    assert app.test_client().post(url, json={}).status_code == 401


@pytest.mark.parametrize('payload', [
    None, [], {}, {'bucket': 'great'}, {'bucket': ['liked']}])
def test_start_rejects_bad_bucket(client, db, payload):
    response = client.post(rk.RANK_SESSIONS_EP, json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize('resid', [None, 'not-an-id', str(ObjectId())])
def test_start_unknown_restaurant(client, db, resid):
    response = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': resid, 'bucket': 'liked'})
    assert response.status_code == 404


def test_start_someone_elses_restaurant(client, db):
    theirs = add_restaurant(db, 'Tacos', user='alice')
    response = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': theirs, 'bucket': 'liked'})
    assert response.status_code == 404


def test_start_already_ranked(client, db):
    tacos = add_restaurant(db, 'Tacos')
    set_ranking(db, [(tacos, 'liked')])
    response = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': tacos, 'bucket': 'fine'})
    assert response.status_code == 409


def test_start_empty_bucket_saves_right_away(client, db):
    liked = add_restaurant(db, 'Liked')
    tacos = add_restaurant(db, 'Tacos')
    set_ranking(db, [(liked, 'liked')])
    response = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': tacos, 'bucket': 'fine'})
    assert response.status_code == 201
    assert response.get_json() == {'done': True, 'position': 1}
    entry, position = pushed(db)
    assert (entry['restaurant_id'], entry['bucket'], position) == (
        tacos, 'fine', 1)
    assert rk.RANK_SESSIONS_COLLECT not in db


def test_full_ranking_flow(client, db):
    a, b, c = (add_restaurant(db, name) for name in 'ABC')
    new = add_restaurant(db, 'New')
    set_ranking(db, [(a, 'liked'), (b, 'liked'), (c, 'liked')])

    response = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': new, 'bucket': 'liked'})
    assert response.status_code == 201
    body = response.get_json()
    assert body['done'] is False
    assert body['compare']['_id'] == b
    answer_url = rk.RANK_SESSIONS_EP + f"/{body['session_id']}/answer"

    body = client.post(answer_url, json={'answer': 'worse'}).get_json()
    assert body['compare']['_id'] == c

    body = client.post(answer_url, json={'answer': 'better'}).get_json()
    assert body == {'done': True, 'position': 2}
    entry, position = pushed(db)
    assert (entry['restaurant_id'], position) == (new, 2)
    assert [(c['winner_id'], c['loser_id'])
            for c in db[rk.COMPARISONS_COLLECT]] == [(b, new), (new, c)]
    assert db[rk.RANK_SESSIONS_COLLECT] == []
    # The session is gone once saved.
    assert client.post(
        answer_url, json={'answer': 'better'}).status_code == 404


def test_same_answer_records_no_comparison(client, db):
    a, b = add_restaurant(db, 'A'), add_restaurant(db, 'B')
    new = add_restaurant(db, 'New')
    set_ranking(db, [(a, 'liked'), (b, 'liked')])
    session_id = client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': new, 'bucket': 'liked'}).get_json()['session_id']
    body = client.post(rk.RANK_SESSIONS_EP + f'/{session_id}/answer',
                       json={'answer': 'same'}).get_json()
    assert body == {'done': True, 'position': 1}
    assert rk.COMPARISONS_COLLECT not in db


@pytest.mark.parametrize('payload', [None, {}, {'answer': 'meh'}])
def test_answer_rejects_bad_answer(client, db, payload):
    url = rk.RANK_SESSIONS_EP + f'/{ObjectId()}/answer'
    assert client.post(url, json=payload).status_code == 400


def start_session(client, db):
    a = add_restaurant(db, 'A')
    new = add_restaurant(db, 'New')
    set_ranking(db, [(a, 'liked')])
    return client.post(rk.RANK_SESSIONS_EP, json={
        'restaurant_id': new, 'bucket': 'liked'}).get_json()['session_id']


@pytest.mark.parametrize('session_id', ['not-an-id', str(ObjectId())])
def test_answer_unknown_session(client, db, session_id):
    url = rk.RANK_SESSIONS_EP + f'/{session_id}/answer'
    assert client.post(url, json={'answer': 'better'}).status_code == 404


def test_answer_someone_elses_session(client, db):
    session_id = start_session(client, db)
    db[rk.RANK_SESSIONS_COLLECT][0]['user'] = 'alice'
    url = rk.RANK_SESSIONS_EP + f'/{session_id}/answer'
    assert client.post(url, json={'answer': 'better'}).status_code == 404


def test_answer_expired_session(client, db):
    session_id = start_session(client, db)
    # Mongo returns naive UTC datetimes.
    db[rk.RANK_SESSIONS_COLLECT][0]['expires_at'] = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=1))
    url = rk.RANK_SESSIONS_EP + f'/{session_id}/answer'
    assert client.post(url, json={'answer': 'better'}).status_code == 404
    dbc.update_raw.assert_not_called()
