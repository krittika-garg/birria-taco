import copy
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

import data.db_connect as dbc
import server.meetup as mt
from server.endpoints import ENDPOINT_EP, app
from server.groups import GROUP_NOT_FOUND, GROUPS_COLLECT
from server.restaurants import (
    DEFAULT_RADIUS_KM, EARTH_RADIUS_KM, RADIUS_ERROR, RESTAURANTS_COLLECT,
)
from server.states import haversine_km

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


@pytest.fixture
def db(monkeypatch):
    """
    In-memory groups collection. read_one matches like Mongo (a scalar
    against an array field means "array contains it") and returns a copy
    with a string _id; update_raw supports the $pull/$push meetup uses.
    """
    docs = []

    def matches(doc, filt):
        return all(v in doc.get(k, []) if isinstance(doc.get(k), list)
                   else doc.get(k) == v for k, v in filt.items())

    def read_one(collection, filt):
        assert collection == GROUPS_COLLECT
        found = [d for d in docs if matches(d, filt)]
        if not found:
            return None
        return {**copy.deepcopy(found[0]), '_id': str(found[0]['_id'])}

    def update_raw(collection, filt, update_doc):
        assert collection == GROUPS_COLLECT
        assert set(filt) == {'_id'}
        for doc in docs:
            if not matches(doc, filt):
                continue
            if '$pull' in update_doc:
                user = update_doc['$pull']['locations']['user']
                doc['locations'] = [e for e in doc.get('locations', [])
                                    if e['user'] != user]
            if '$push' in update_doc:
                doc.setdefault('locations', []).append(
                    update_doc['$push']['locations'])

    monkeypatch.setattr(dbc, 'read_one', read_one)
    monkeypatch.setattr(dbc, 'update_raw', update_raw)
    return docs


def add_group(db, members, locations=(), expired=False):
    """Insert a group doc and return its id as a string."""
    # Mongo returns naive UTC datetimes.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = timedelta(minutes=-1 if expired else 60)
    doc = {
        '_id': ObjectId(),
        'host': members[0],
        'members': list(members),
        'expires_at': now + delta,
        'locations': [
            {'user': user,
             'location': {'type': 'Point', 'coordinates': [lon, lat]}}
            for user, lat, lon in locations],
    }
    db.append(doc)
    return str(doc['_id'])


def max_km(center, points):
    return max(haversine_km(*center, *p) for p in points)


def average(points):
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


# --- fair_midpoint ---------------------------------------------------

def test_one_point_is_itself():
    assert mt.fair_midpoint([(40.7, -74.0)]) == (40.7, -74.0)


def test_duplicate_points_are_one_point():
    assert mt.fair_midpoint([(40.7, -74.0)] * 3) == (40.7, -74.0)


def test_two_points_give_their_midpoint():
    lat, lon = mt.fair_midpoint([(40.70, -74.00), (40.80, -73.90)])
    assert lat == pytest.approx(40.75)
    assert lon == pytest.approx(-73.95)


def test_right_triangle_centers_on_hypotenuse():
    # Right angle at (40.70, -74.00) on the flat plane: one leg runs
    # east, the other north.
    points = [(40.70, -74.00), (40.70, -73.95), (40.75, -74.00)]
    lat, lon = mt.fair_midpoint(points)
    assert lat == pytest.approx(40.725)
    assert lon == pytest.approx(-73.975)


def test_collinear_points_use_the_outer_pair():
    points = [(40.70, -74.00), (40.75, -73.95), (40.80, -73.90)]
    lat, lon = mt.fair_midpoint(points)
    assert lat == pytest.approx(40.75)
    assert lon == pytest.approx(-73.95)


def test_acute_triangle_uses_circumcircle():
    points = [(40.70, -74.00), (40.70, -73.96), (40.73, -73.98)]
    center = mt.fair_midpoint(points)
    distances = [haversine_km(*center, *p) for p in points]
    # Every vertex is on the circle, so all are (nearly) equidistant.
    assert max(distances) - min(distances) < 0.01


def test_cluster_and_outlier_meet_halfway_not_at_average():
    cluster = [(40.700, -74.000), (40.701, -73.999), (40.700, -73.999)]
    far = (40.800, -73.900)
    points = cluster + [far]
    lat, lon = mt.fair_midpoint(points)
    # Halfway between the far point and the cluster point farthest
    # from it, (40.700, -74.000).
    assert lat == pytest.approx(40.75)
    assert lon == pytest.approx(-73.95)
    avg = average(points)
    assert haversine_km(lat, lon, *avg) > 3
    assert max_km((lat, lon), points) < max_km(avg, points) - 3


@pytest.mark.parametrize('points', [
    [(40.70, -74.00), (40.80, -73.90)],
    [(40.70, -74.00), (40.70, -73.95), (40.75, -74.00)],
    [(40.700, -74.000), (40.701, -73.999), (40.700, -73.999),
     (40.800, -73.900)],
    [(40.71, -74.01), (40.73, -73.99), (40.76, -73.98), (40.68, -73.94),
     (40.69, -73.99), (40.71, -73.95)],
    [(34.05, -118.25), (34.06, -118.24), (34.10, -118.33),
     (33.99, -118.47), (34.02, -118.40)],
])
def test_never_worse_than_average(points):
    center = mt.fair_midpoint(points)
    assert max_km(center, points) <= max_km(average(points), points) + 1e-6


# --- PUT /groups/<id>/location ---------------------------------------

def location_url(group_id):
    return f'/groups/{group_id}/location'


def midpoint_url(group_id):
    return f'/groups/{group_id}/midpoint'


def test_put_saves_and_replaces(db):
    group_id = add_group(db, ['bob', ODD_USER])
    me = client_for(ODD_USER)

    response = me.put(location_url(group_id),
                      json={'lat': 40.7, 'lon': -74.0})
    assert response.status_code == 200
    assert response.get_json() == {'location': {'lat': 40.7, 'lon': -74.0}}
    assert db[0]['locations'] == [{
        'user': ODD_USER,
        'location': {'type': 'Point', 'coordinates': [-74.0, 40.7]}}]

    response = me.put(location_url(group_id), json={'lat': 41, 'lon': -73})
    assert response.status_code == 200
    assert db[0]['locations'] == [{
        'user': ODD_USER,
        'location': {'type': 'Point', 'coordinates': [-73, 41]}}]


def test_put_keeps_other_members_locations(db):
    group_id = add_group(db, ['bob', 'alice'],
                         locations=[('bob', 40.7, -74.0)])
    client_for('alice').put(location_url(group_id),
                            json={'lat': 40.8, 'lon': -73.9})
    assert [e['user'] for e in db[0]['locations']] == ['bob', 'alice']


@pytest.mark.parametrize('group_id', ['not-an-id', str(ObjectId())])
def test_put_unknown_group(db, group_id):
    response = client_for('bob').put(location_url(group_id),
                                     json={'lat': 40.7, 'lon': -74.0})
    assert response.status_code == 404
    assert response.get_json() == {mt.MESSAGE: mt.GROUP_NOT_FOUND}


def test_put_non_member(db):
    group_id = add_group(db, ['bob'])
    response = client_for('alice').put(location_url(group_id),
                                       json={'lat': 40.7, 'lon': -74.0})
    assert response.status_code == 404
    assert db[0]['locations'] == []


def test_put_expired_group(db):
    group_id = add_group(db, ['bob'], expired=True)
    response = client_for('bob').put(location_url(group_id),
                                     json={'lat': 40.7, 'lon': -74.0})
    assert response.status_code == 404
    assert db[0]['locations'] == []


@pytest.mark.parametrize('body', [
    {'lon': -74.0},
    {'lat': 40.7},
    {},
    {'lat': 'abc', 'lon': -74.0},
    {'lat': '40.7', 'lon': '-74.0'},
    {'lat': True, 'lon': -74.0},
    {'lat': 40.7, 'lon': False},
    {'lat': None, 'lon': None},
    {'lat': 91, 'lon': -74.0},
    {'lat': 40.7, 'lon': -180.5},
    {'lat': 10 ** 400, 'lon': 0},
    [40.7, -74.0],
])
def test_put_bad_body(db, body):
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(location_url(group_id), json=body)
    assert response.status_code == 400
    assert db[0]['locations'] == []


@pytest.mark.parametrize('raw', [
    '{"lat": NaN, "lon": -74.0}',
    '{"lat": 40.7, "lon": Infinity}',
    'not json',
])
def test_put_non_finite_or_invalid_json(db, raw):
    group_id = add_group(db, ['bob'])
    response = client_for('bob').put(
        location_url(group_id), data=raw, content_type='application/json')
    assert response.status_code == 400
    assert db[0]['locations'] == []


@pytest.mark.parametrize('method, url', [
    ('put', location_url(ObjectId())),
    ('get', midpoint_url(ObjectId())),
])
def test_login_required(method, url):
    assert getattr(app.test_client(), method)(url).status_code == 401


# --- GET /groups/<id>/midpoint ---------------------------------------

def test_midpoint_two_members(db):
    group_id = add_group(db, ['bob', ODD_USER], locations=[
        ('bob', 40.70, -74.00), (ODD_USER, 40.80, -73.90)])
    response = client_for('bob').get(midpoint_url(group_id))
    assert response.status_code == 200
    body = response.get_json()
    assert body['midpoint'] == {'lat': 40.75, 'lon': -73.95}
    assert body['located'] == 2
    assert body['members'] == 2
    expected = haversine_km(40.75, -73.95, 40.70, -74.00)
    assert body['max_km'] == round(expected, 2)
    assert 6.5 < body['max_km'] < 7.5


def test_midpoint_rounds_to_six_decimals(db):
    group_id = add_group(db, ['bob', 'alice'], locations=[
        ('bob', 40.7000001, -74.0000003), ('alice', 40.7123457, -73.9876543)])
    body = client_for('bob').get(midpoint_url(group_id)).get_json()
    for value in body['midpoint'].values():
        assert value == round(value, 6)


def test_midpoint_ignores_people_who_left(db):
    group_id = add_group(db, ['bob', 'alice'], locations=[
        ('bob', 40.70, -74.00), ('carol', 41.50, -72.00),
        ('alice', 40.80, -73.90)])
    body = client_for('alice').get(midpoint_url(group_id)).get_json()
    assert body['midpoint'] == {'lat': 40.75, 'lon': -73.95}
    assert body['located'] == 2
    assert body['members'] == 2


def test_midpoint_counts_members_without_locations(db):
    group_id = add_group(db, ['bob', 'alice', 'dan'],
                         locations=[('bob', 40.70, -74.00)])
    body = client_for('dan').get(midpoint_url(group_id)).get_json()
    assert body == {'midpoint': {'lat': 40.70, 'lon': -74.00},
                    'located': 1, 'members': 3, 'max_km': 0}


def test_midpoint_uses_latest_entry_per_user(db):
    # Two interleaved PUTs could leave two entries; the last one wins.
    group_id = add_group(db, ['bob'], locations=[
        ('bob', 10.0, 10.0), ('bob', 40.7, -74.0)])
    body = client_for('bob').get(midpoint_url(group_id)).get_json()
    assert body['midpoint'] == {'lat': 40.7, 'lon': -74.0}
    assert body['located'] == 1


@pytest.mark.parametrize('locations', [
    [],
    [('carol', 40.7, -74.0)],
])
def test_midpoint_no_locations(db, locations):
    group_id = add_group(db, ['bob', 'alice'], locations=locations)
    response = client_for('bob').get(midpoint_url(group_id))
    assert response.status_code == 404
    assert response.get_json() == {mt.MESSAGE: mt.NO_LOCATIONS}


def test_midpoint_without_locations_field(db):
    group_id = add_group(db, ['bob'])
    del db[0]['locations']
    response = client_for('bob').get(midpoint_url(group_id))
    assert response.status_code == 404


@pytest.mark.parametrize('user, expired', [('alice', False), ('bob', True)])
def test_midpoint_hidden_from_non_members_and_when_expired(db, user,
                                                           expired):
    group_id = add_group(db, ['bob'], locations=[('bob', 40.7, -74.0)],
                         expired=expired)
    response = client_for(user).get(midpoint_url(group_id))
    assert response.status_code == 404
    assert response.get_json() == {mt.MESSAGE: mt.GROUP_NOT_FOUND}


def test_midpoint_bad_id(db):
    response = client_for('bob').get(midpoint_url('not-an-id'))
    assert response.status_code == 404


def test_midpoint_has_no_usernames_or_raw_locations(db):
    group_id = add_group(db, ['bob', ODD_USER], locations=[
        ('bob', 40.70, -74.00), (ODD_USER, 40.80, -73.90)])
    response = client_for('bob').get(midpoint_url(group_id))
    text = response.get_data(as_text=True)
    assert 'bob' not in text
    assert ODD_USER not in text
    assert '40.8' not in text and '40.7,' not in text
    assert set(response.get_json()) == {
        'midpoint', 'located', 'members', 'max_km'}


# --- /endpoints ------------------------------------------------------

def test_routes_listed_in_endpoints():
    listed = app.test_client().get(ENDPOINT_EP).get_json()[
        'Available endpoints']
    assert '/groups/<string:group_id>/location' in listed
    assert '/groups/<string:group_id>/midpoint' in listed


# --- GET /groups/<id>/suggestions ------------------------------------

BOB_AT = ('bob', 40.70, -74.00)
AMY_AT = ('amy', 40.80, -73.90)
MID_LAT, MID_LON = mt.fair_midpoint([BOB_AT[1:], AMY_AT[1:]])
LIMIT_ERROR = 'limit must be an integer from 1 to 50'


def suggestions_url(group_id):
    return f'/groups/{group_id}/suggestions'


class FakeRestaurants(list):
    """In-memory restaurants collection that records each read filter."""

    def __init__(self):
        super().__init__()
        self.reads = []


@pytest.fixture
def restaurants(monkeypatch):
    docs = FakeRestaurants()

    def read(collection, no_id=True, filt=None, **kwargs):
        assert collection == RESTAURANTS_COLLECT
        assert no_id is False
        docs.reads.append(filt)
        return [{**d, '_id': str(d['_id'])} for d in docs]

    monkeypatch.setattr(dbc, 'read', read)
    return docs


def add_rest(restaurants, user, name, rating=None, dlat=0.0, hood=None):
    """Save a restaurant dlat degrees north of the group midpoint."""
    doc = {
        '_id': ObjectId(),
        'user': user,
        'name': name,
        'rating': rating,
        'location': {'type': 'Point',
                     'coordinates': [MID_LON, MID_LAT + dlat]},
        'neighborhood': None if hood is None else {'code': hood},
    }
    restaurants.append(doc)
    return str(doc['_id'])


@pytest.fixture
def group(db):
    return add_group(db, ['bob', 'amy', 'cy'], locations=[BOB_AT, AMY_AT])


def suggest(group_id, user='bob', query=''):
    return client_for(user).get(suggestions_url(group_id) + query)


def names(response):
    return [s['name'] for s in response.get_json()['suggestions']]


def km_from_mid(dlat):
    return round(haversine_km(MID_LAT, MID_LON, MID_LAT + dlat, MID_LON), 2)


def test_suggestions_exact_read_filter(group, restaurants):
    response = suggest(group, query='?radius_km=3')
    assert response.status_code == 200
    assert restaurants.reads == [{
        'user': {'$in': ['bob', 'amy', 'cy']},
        'location': {'$geoWithin': {'$centerSphere': [
            [MID_LON, MID_LAT], 3 / EARTH_RADIUS_KM]}},
    }]


def test_suggestions_defaults_and_shape(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=8, dlat=0.01)
    body = suggest(group).get_json()
    assert body['radius_km'] == 2 == DEFAULT_RADIUS_KM
    assert body['midpoint'] == {
        'lat': round(MID_LAT, 6), 'lon': round(MID_LON, 6)}
    centre = restaurants.reads[0]['location']['$geoWithin']['$centerSphere']
    assert centre[1] == DEFAULT_RADIUS_KM / EARTH_RADIUS_KM
    [only] = body['suggestions']
    assert set(only) == {'restaurant_id', 'name', 'rating', 'saved_by',
                         'distance_km'}
    assert only['rating'] == 8 and only['saved_by'] == 1
    assert only['distance_km'] == km_from_mid(0.01)


def test_suggestions_empty_is_ok(group, restaurants):
    response = suggest(group)
    assert response.status_code == 200
    assert response.get_json()['suggestions'] == []


def test_same_place_from_two_members_is_one_suggestion(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=9)
    add_rest(restaurants, 'amy', 'Taco Spot', rating=6)
    [only] = suggest(group).get_json()['suggestions']
    assert only['rating'] == 7.5
    assert only['saved_by'] == 2


def test_average_ignores_unrated_and_rounds(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=8)
    add_rest(restaurants, 'amy', 'Taco Spot', rating=7)
    add_rest(restaurants, 'cy', 'Taco Spot', rating=7)
    add_rest(restaurants, 'cy', 'Taco Spot')
    [only] = suggest(group).get_json()['suggestions']
    assert only['rating'] == 7.33
    assert only['saved_by'] == 3


def test_saved_by_counts_distinct_members(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=8)
    add_rest(restaurants, 'bob', 'Taco Spot', rating=6)
    [only] = suggest(group).get_json()['suggestions']
    assert only['saved_by'] == 1
    assert only['rating'] == 7


def test_names_differing_by_case_and_spacing_merge(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco   Spot', rating=8)
    add_rest(restaurants, 'amy', ' taco spot ', rating=6)
    [only] = suggest(group).get_json()['suggestions']
    assert only['saved_by'] == 2
    # name_order picks the display name: collapsed spacing, then its order.
    assert only['name'] == 'taco spot'


def test_same_name_in_different_neighborhoods_stays_apart(group,
                                                          restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=8, hood='MN01')
    add_rest(restaurants, 'amy', 'Taco Spot', rating=8, hood='BK02')
    add_rest(restaurants, 'cy', 'Taco Spot', rating=8)
    suggestions = suggest(group).get_json()['suggestions']
    assert len(suggestions) == 3
    assert all(s['saved_by'] == 1 for s in suggestions)


def test_full_sort_order(group, restaurants):
    # Added in scrambled order; expected order is listed top to bottom.
    add_rest(restaurants, 'bob', 'U-far', dlat=0.03)
    add_rest(restaurants, 'bob', 'U-two')
    add_rest(restaurants, 'amy', 'U-two')
    add_rest(restaurants, 'bob', 'U-near', dlat=0.01)
    add_rest(restaurants, 'bob', 'R8-far', rating=8, dlat=0.03)
    add_rest(restaurants, 'bob', 'beta', rating=8, dlat=0.01)
    add_rest(restaurants, 'bob', 'Alpha', rating=8, dlat=0.01)
    add_rest(restaurants, 'bob', 'R8-near', rating=8, dlat=0.005)
    add_rest(restaurants, 'bob', 'R8-two', rating=8, dlat=0.04)
    add_rest(restaurants, 'amy', 'R8-two', rating=8, dlat=0.04)
    add_rest(restaurants, 'bob', 'R9', rating=9, dlat=0.04)
    assert names(suggest(group)) == [
        'R9', 'R8-two', 'R8-near', 'Alpha', 'beta', 'R8-far',
        'U-two', 'U-near', 'U-far']


def test_zero_rating_still_beats_unrated(group, restaurants):
    add_rest(restaurants, 'bob', 'Unrated')
    add_rest(restaurants, 'bob', 'Zero', rating=0, dlat=0.03)
    assert names(suggest(group)) == ['Zero', 'Unrated']


def test_restaurant_id_is_from_highest_rated_entry(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=5)
    best = add_rest(restaurants, 'amy', 'Taco Spot', rating=9)
    add_rest(restaurants, 'cy', 'Taco Spot')
    [only] = suggest(group).get_json()['suggestions']
    assert only['restaurant_id'] == best


def test_restaurant_id_when_none_rated_is_one_of_the_entries(group,
                                                             restaurants):
    ids = {add_rest(restaurants, 'bob', 'Taco Spot'),
           add_rest(restaurants, 'amy', 'Taco Spot')}
    [only] = suggest(group).get_json()['suggestions']
    assert only['rating'] is None
    assert only['restaurant_id'] in ids


def test_distance_uses_closest_entry(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', dlat=0.05)
    add_rest(restaurants, 'amy', 'Taco Spot', dlat=0.01)
    [only] = suggest(group).get_json()['suggestions']
    assert only['distance_km'] == km_from_mid(0.01)


def test_default_limit_is_ten_and_limit_applies(group, restaurants):
    for i in range(12):
        add_rest(restaurants, 'bob', f'Place {i:02}', rating=5)
    assert len(names(suggest(group))) == 10
    assert len(names(suggest(group, query='?limit=3'))) == 3
    assert len(names(suggest(group, query='?limit=50'))) == 12


@pytest.mark.parametrize('query', [
    '?radius_km=0', '?radius_km=-1', '?radius_km=abc', '?radius_km=nan',
    '?radius_km=1e9'])
def test_suggestions_bad_radius(group, restaurants, query):
    response = suggest(group, query=query)
    assert response.status_code == 400
    assert response.get_json()['Message'] == RADIUS_ERROR
    assert restaurants.reads == []


@pytest.mark.parametrize('query', [
    '?limit=0', '?limit=51', '?limit=-2', '?limit=x', '?limit=1.5'])
def test_suggestions_bad_limit(group, restaurants, query):
    response = suggest(group, query=query)
    assert response.status_code == 400
    assert response.get_json()['Message'] == LIMIT_ERROR
    assert restaurants.reads == []


def test_suggestions_no_locations(db, restaurants):
    group_id = add_group(db, ['bob', 'amy'])
    response = suggest(group_id)
    assert response.status_code == 404
    assert response.get_json()['Message'] == mt.NO_LOCATIONS


def test_suggestions_hidden_from_non_members(group, restaurants):
    response = suggest(group, user='zed')
    assert response.status_code == 404
    assert response.get_json()['Message'] == GROUP_NOT_FOUND


def test_suggestions_bad_id(db, restaurants):
    assert suggest('not-an-id').status_code == 404


def test_suggestions_login_required():
    response = app.test_client().get(suggestions_url(ObjectId()))
    assert response.status_code == 401


def test_suggestions_have_no_usernames(group, restaurants):
    add_rest(restaurants, 'bob', 'Taco Spot', rating=8)
    add_rest(restaurants, 'amy', 'Taco Spot', rating=6)
    text = suggest(group).get_data(as_text=True)
    for user in ('bob', 'amy', 'cy'):
        assert user not in text


def test_suggestions_route_listed_in_endpoints():
    listed = app.test_client().get(ENDPOINT_EP).get_json()[
        'Available endpoints']
    assert '/groups/<string:group_id>/suggestions' in listed
