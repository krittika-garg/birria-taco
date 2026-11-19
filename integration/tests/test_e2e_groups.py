"""Groups and meetup midpoints, end to end against real MongoDB."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from server.states import haversine_km

# Usernames are free-form; Mongo-special characters must be safe.
ODD_USER = 'a.b$c'


@pytest.fixture
def group(login):
    """bob hosts a group that alice and ODD_USER joined."""
    bob, alice, odd = login('bob'), login('alice'), login(ODD_USER)
    created = bob.post('/groups')
    assert created.status_code == 201
    info = created.get_json()['group']
    for client in (alice, odd):
        joined = client.post(f"/groups/join/{info['invite_token']}")
        assert joined.status_code == 200
    return info['_id'], bob, alice, odd


def test_create_join_get(group, db):
    group_id, bob, alice, odd = group
    for client in (bob, alice, odd):
        members = client.get(f'/groups/{group_id}').get_json()['group'][
            'members']
        assert members == ['bob', 'alice', ODD_USER]
    stored = db['groups'].find_one({'_id': ObjectId(group_id)})
    assert stored['members'] == ['bob', 'alice', ODD_USER]


def test_joining_twice_keeps_one_entry(group, db):
    group_id, bob, alice, _ = group
    token = bob.get(f'/groups/{group_id}').get_json()['group'][
        'invite_token']
    alice.post(f'/groups/join/{token}')
    stored = db['groups'].find_one({'_id': ObjectId(group_id)})
    assert stored['members'].count('alice') == 1


def test_outsider_and_bad_tokens(group, login):
    group_id, *_ = group
    eve = login('eve')
    assert eve.get(f'/groups/{group_id}').status_code == 404
    assert eve.post('/groups/join/not-a-token').status_code == 404
    assert eve.put(f'/groups/{group_id}/location',
                   json={'lat': 40.7, 'lon': -74.0}).status_code == 404


def test_leave_and_host_rules(group):
    group_id, bob, alice, _ = group
    assert bob.post(f'/groups/{group_id}/leave').status_code == 409
    assert alice.post(f'/groups/{group_id}/leave').status_code == 200
    assert alice.get(f'/groups/{group_id}').status_code == 404
    members = bob.get(f'/groups/{group_id}').get_json()['group']['members']
    assert 'alice' not in members


def test_expired_group(group, db):
    group_id, bob, *_ = group
    db['groups'].update_one(
        {'_id': ObjectId(group_id)},
        {'$set': {'expires_at': datetime.now(timezone.utc)
                  - timedelta(minutes=1)}})
    assert bob.get(f'/groups/{group_id}').status_code == 404
    assert bob.get(f'/groups/{group_id}/midpoint').status_code == 404


def test_location_is_replaced_not_duplicated(group, db):
    group_id, _, _, odd = group
    url = f'/groups/{group_id}/location'
    assert odd.put(url, json={'lat': 40.70, 'lon': -74.00}).status_code == 200
    assert odd.put(url, json={'lat': 40.80, 'lon': -73.90}).status_code == 200

    stored = db['groups'].find_one({'_id': ObjectId(group_id)})
    assert stored['locations'] == [{
        'user': ODD_USER,
        'location': {'type': 'Point', 'coordinates': [-73.90, 40.80]}}]
    # No field is ever named after a username.
    assert set(stored) <= {'_id', 'host', 'members', 'invite_token',
                           'expires_at', 'locations'}


def test_midpoint_flow(group):
    group_id, bob, alice, odd = group
    midpoint_url = f'/groups/{group_id}/midpoint'
    assert bob.get(midpoint_url).status_code == 404

    bob.put(f'/groups/{group_id}/location', json={'lat': 40.70, 'lon': -74.00})
    odd.put(f'/groups/{group_id}/location', json={'lat': 40.80, 'lon': -73.90})
    body = alice.get(midpoint_url).get_json()
    assert body['midpoint'] == {'lat': 40.75, 'lon': -73.95}
    assert body['located'] == 2
    assert body['members'] == 3
    assert body['max_km'] == round(
        haversine_km(40.75, -73.95, 40.70, -74.00), 2)


def test_midpoint_ignores_people_who_left(group):
    group_id, bob, alice, _ = group
    bob.put(f'/groups/{group_id}/location', json={'lat': 40.70, 'lon': -74.00})
    alice.put(f'/groups/{group_id}/location', json={'lat': 41.5, 'lon': -72.0})
    alice.post(f'/groups/{group_id}/leave')
    body = bob.get(f'/groups/{group_id}/midpoint').get_json()
    assert body['midpoint'] == {'lat': 40.70, 'lon': -74.00}
    assert body['located'] == 1
