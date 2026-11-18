import copy
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

import data.db_connect as dbc
import server.votes as vt
from server.endpoints import ENDPOINT_EP, app
from server.groups import GROUP_NOT_FOUND, GROUPS_COLLECT
from server.restaurants import RESTAURANTS_COLLECT

from security.tokens import create_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'
# Usernames are free-form; one with Mongo-special characters on purpose.
ODD_USER = 'a.b$c'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


def client_for(user):
    client = app.test_client()
    token = create_access_token(user, TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


def matches(doc, filt):
    """Mongo-ish match: list fields contain the value, plus $in."""
    for k, v in filt.items():
        got = doc.get(k)
        if isinstance(v, dict) and '$in' in v:
            if got not in v['$in']:
                return False
        elif isinstance(got, list):
            if v not in got:
                return False
        elif got != v:
            return False
    return True


@pytest.fixture
def db(monkeypatch):
    """In-memory groups and restaurants collections."""
    colls = {GROUPS_COLLECT: [], RESTAURANTS_COLLECT: []}

    def with_str_id(doc):
        return {**copy.deepcopy(doc), '_id': str(doc['_id'])}

    def read_one(collection, filt):
        found = [d for d in colls[collection] if matches(d, filt)]
        return with_str_id(found[0]) if found else None

    def read(collection, no_id=True, filt=None, projection=None):
        assert collection == RESTAURANTS_COLLECT and not no_id
        return [with_str_id(d) for d in colls[collection]
                if matches(d, filt or {})]

    def update_raw(collection, filt, update_doc):
        assert collection == GROUPS_COLLECT
        assert set(filt) == {'_id'}
        for doc in colls[collection]:
            if not matches(doc, filt):
                continue
            if '$pull' in update_doc:
                user = update_doc['$pull']['votes']['user']
                doc['votes'] = [v for v in doc.get('votes', [])
                                if v['user'] != user]
            if '$push' in update_doc:
                doc.setdefault('votes', []).append(
                    update_doc['$push']['votes'])

    monkeypatch.setattr(dbc, 'read_one', read_one)
    monkeypatch.setattr(dbc, 'read', read)
    monkeypatch.setattr(dbc, 'update_raw', update_raw)
    return colls


def add_group(db, members, votes=(), expired=False):
    """Insert a group doc and return its id as a string."""
    # Mongo returns naive UTC datetimes.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    doc = {
        '_id': ObjectId(),
        'host': members[0],
        'members': list(members),
        'expires_at': now + timedelta(minutes=-1 if expired else 60),
        'votes': [{'user': u, 'restaurant_id': r} for u, r in votes],
    }
    db[GROUPS_COLLECT].append(doc)
    return str(doc['_id'])


def add_restaurant(db, user, name):
    """Insert a saved restaurant and return its id as a string."""
    doc = {'_id': ObjectId(), 'user': user, 'name': name}
    db[RESTAURANTS_COLLECT].append(doc)
    return str(doc['_id'])


def group_votes(db):
    return db[GROUPS_COLLECT][0]['votes']


def vote_url(group_id):
    return f'/groups/{group_id}/vote'


def votes_url(group_id):
    return f'/groups/{group_id}/votes'


# --- PUT /groups/<id>/vote -------------------------------------------

def test_vote_for_own_restaurant(db):
    resid = add_restaurant(db, 'bob', 'Birria Spot')
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(vote_url(group_id),
                                     json={'restaurant_id': resid})
    assert response.status_code == 200
    assert response.get_json() == {'vote': {'restaurant_id': resid}}
    assert group_votes(db) == [{'user': 'bob', 'restaurant_id': resid}]


def test_vote_for_another_members_restaurant(db):
    resid = add_restaurant(db, ODD_USER, 'Taco Place')
    group_id = add_group(db, ['bob', ODD_USER])
    response = client_for('bob').put(vote_url(group_id),
                                     json={'restaurant_id': resid})
    assert response.status_code == 200


def test_vote_again_replaces_vote(db):
    first = add_restaurant(db, 'bob', 'A')
    second = add_restaurant(db, 'bob', 'B')
    group_id = add_group(db, ['bob', 'alice'], votes=[('alice', first)])
    bob = client_for('bob')
    bob.put(vote_url(group_id), json={'restaurant_id': first})
    bob.put(vote_url(group_id), json={'restaurant_id': second})
    assert group_votes(db) == [
        {'user': 'alice', 'restaurant_id': first},
        {'user': 'bob', 'restaurant_id': second}]


@pytest.mark.parametrize('owner', ['carol', None])
def test_vote_rejects_restaurant_outside_group(db, owner):
    resid = (add_restaurant(db, owner, 'Elsewhere') if owner
             else str(ObjectId()))
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(vote_url(group_id),
                                     json={'restaurant_id': resid})
    assert response.status_code == 404
    assert response.get_json() == {vt.MESSAGE: vt.RESTAURANT_NOT_IN_GROUP}
    assert group_votes(db) == []


@pytest.mark.parametrize('body', [
    {}, {'restaurant_id': ''}, {'restaurant_id': 5},
    {'restaurant_id': None}, ['abc'],
])
def test_vote_bad_body(db, body):
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(vote_url(group_id), json=body)
    assert response.status_code == 400
    assert group_votes(db) == []


def test_vote_bad_restaurant_id(db):
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(vote_url(group_id),
                                     json={'restaurant_id': 'not-an-id'})
    assert response.status_code == 404
    assert group_votes(db) == []


@pytest.mark.parametrize('user, expired', [('alice', False), ('bob', True)])
def test_vote_hidden_from_non_members_and_when_expired(db, user, expired):
    resid = add_restaurant(db, 'bob', 'A')
    group_id = add_group(db, ['bob'], expired=expired)
    response = client_for(user).put(vote_url(group_id),
                                    json={'restaurant_id': resid})
    assert response.status_code == 404
    assert response.get_json() == {vt.MESSAGE: GROUP_NOT_FOUND}
    assert group_votes(db) == []


# --- GET /groups/<id>/votes ------------------------------------------

def test_tally_most_votes_first(db):
    a = add_restaurant(db, 'bob', 'Alpha')
    b = add_restaurant(db, 'alice', 'Beta')
    group_id = add_group(db, ['bob', 'alice', 'dan'], votes=[
        ('bob', a), ('alice', b), ('dan', b)])
    response = client_for('bob').get(votes_url(group_id))
    assert response.status_code == 200
    assert response.get_json() == {
        'tally': [{'restaurant_id': b, 'name': 'Beta', 'votes': 2},
                  {'restaurant_id': a, 'name': 'Alpha', 'votes': 1}],
        'my_vote': a, 'voted': 3, 'members': 3}


def test_tally_ties_sorted_by_name(db):
    z = add_restaurant(db, 'bob', 'Zeta')
    a = add_restaurant(db, 'bob', 'Alpha')
    group_id = add_group(db, ['bob', 'alice'], votes=[
        ('bob', z), ('alice', a)])
    tally = client_for('bob').get(votes_url(group_id)).get_json()['tally']
    assert [t['name'] for t in tally] == ['Alpha', 'Zeta']


def test_tally_empty(db):
    group_id = add_group(db, ['bob', 'alice'])
    assert client_for('alice').get(votes_url(group_id)).get_json() == {
        'tally': [], 'my_vote': None, 'voted': 0, 'members': 2}


def test_tally_ignores_people_who_left(db):
    a = add_restaurant(db, 'bob', 'Alpha')
    group_id = add_group(db, ['bob'], votes=[('bob', a), ('carol', a)])
    body = client_for('bob').get(votes_url(group_id)).get_json()
    assert body['tally'][0]['votes'] == 1
    assert body['voted'] == 1


def test_tally_uses_latest_vote_per_user(db):
    # Two interleaved PUTs could leave two entries; the last one wins.
    a = add_restaurant(db, 'bob', 'Alpha')
    b = add_restaurant(db, 'bob', 'Beta')
    group_id = add_group(db, ['bob'], votes=[('bob', a), ('bob', b)])
    body = client_for('bob').get(votes_url(group_id)).get_json()
    assert body['tally'] == [{'restaurant_id': b, 'name': 'Beta',
                              'votes': 1}]
    assert body['my_vote'] == b


def test_tally_drops_deleted_restaurants(db):
    a = add_restaurant(db, 'bob', 'Alpha')
    gone = str(ObjectId())
    group_id = add_group(db, ['bob', 'alice'], votes=[
        ('bob', gone), ('alice', a)])
    body = client_for('bob').get(votes_url(group_id)).get_json()
    assert [t['restaurant_id'] for t in body['tally']] == [a]
    assert body['my_vote'] is None
    assert body['voted'] == 1


def test_tally_without_votes_field(db):
    group_id = add_group(db, ['bob'])
    del db[GROUPS_COLLECT][0]['votes']
    body = client_for('bob').get(votes_url(group_id)).get_json()
    assert body['tally'] == []


def test_tally_hides_who_voted(db):
    a = add_restaurant(db, 'bob', 'Alpha')
    group_id = add_group(db, ['bob', ODD_USER], votes=[(ODD_USER, a)])
    text = client_for('bob').get(votes_url(group_id)).get_data(as_text=True)
    assert ODD_USER not in text


@pytest.mark.parametrize('user, expired', [('alice', False), ('bob', True)])
def test_tally_hidden_from_non_members_and_when_expired(db, user, expired):
    group_id = add_group(db, ['bob'], expired=expired)
    response = client_for(user).get(votes_url(group_id))
    assert response.status_code == 404
    assert response.get_json() == {vt.MESSAGE: GROUP_NOT_FOUND}


def test_tally_bad_group_id(db):
    assert client_for('bob').get(votes_url('not-an-id')).status_code == 404


# --- shared ----------------------------------------------------------

@pytest.mark.parametrize('method, url', [
    ('put', vote_url(ObjectId())),
    ('get', votes_url(ObjectId())),
])
def test_login_required(method, url):
    assert getattr(app.test_client(), method)(url).status_code == 401


def test_routes_listed_in_endpoints():
    listed = app.test_client().get(ENDPOINT_EP).get_json()[
        'Available endpoints']
    assert vt.VOTE_EP in listed
    assert vt.VOTES_EP in listed
